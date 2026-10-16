import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, render_template, request

from analyzer import analyze_python

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024  # 200 KB request cap


def database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def get_connection():
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    # Supabase Postgres connections must use TLS.
    return psycopg.connect(url, sslmode="require", connect_timeout=8, row_factory=dict_row)


def init_db():
    """Create the two project tables if the cloud database is configured."""
    if not database_url():
        return False
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                language TEXT NOT NULL DEFAULT 'python',
                source_chars INTEGER NOT NULL,
                source_lines INTEGER NOT NULL,
                issue_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                line_number INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                suggestion TEXT NOT NULL
            )
        """)
    return True


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "RefactBrainAI"}), 200


@app.get("/api/status")
def api_status():
    configured = bool(database_url())
    db_ok = False
    if configured:
        try:
            with get_connection() as conn:
                conn.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
    return jsonify({
        "app": "RefactBrainAI",
        "analysis_engine": "python-ast-rules",
        "database_configured": configured,
        "database_connected": db_ok,
    })


@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    source = payload.get("code", "")
    if not isinstance(source, str):
        return jsonify({"error": "The 'code' field must be text."}), 400
    if not source.strip():
        return jsonify({"error": "Please enter Python code before analyzing."}), 400
    if len(source) > 100_000:
        return jsonify({"error": "Code is too long. Limit the snippet to 100,000 characters."}), 413

    findings, syntax_error = analyze_python(source)
    lines = len(source.splitlines()) or 1
    persisted = False
    run_id = None

    if database_url():
        try:
            with get_connection() as conn:
                run = conn.execute("""
                    INSERT INTO analysis_runs (language, source_chars, source_lines, issue_count, status)
                    VALUES ('python', %s, %s, %s, %s)
                    RETURNING id
                """, (len(source), lines, len(findings), "syntax_error" if syntax_error else "completed")).fetchone()
                run_id = run["id"]
                if findings:
                    conn.executemany("""
                        INSERT INTO findings
                        (run_id, rule_id, severity, line_number, title, message, suggestion)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, [
                        (run_id, f["rule_id"], f["severity"], f.get("line"), f["title"], f["message"], f["suggestion"])
                        for f in findings
                    ])
            persisted = True
        except Exception:
            # Analysis remains usable if cloud storage is temporarily unavailable.
            app.logger.exception("Could not save analysis to the cloud database")

    return jsonify({
        "run_id": run_id,
        "persisted": persisted,
        "syntax_error": syntax_error,
        "line_count": lines,
        "character_count": len(source),
        "issue_count": len(findings),
        "findings": findings,
        "engine": "Python AST + deterministic rules",
        "note": "Rule-based analysis, not an AI model. Review suggestions and run tests before changing production code.",
    })


@app.get("/api/history")
def api_history():
    if not database_url():
        return jsonify({"error": "Cloud history is not configured yet. Add DATABASE_URL in the hosting environment."}), 503
    try:
        with get_connection() as conn:
            runs = conn.execute("""
                SELECT id, created_at, language, source_chars, source_lines, issue_count, status
                FROM analysis_runs ORDER BY created_at DESC LIMIT 20
            """).fetchall()
        for run in runs:
            if isinstance(run["created_at"], datetime):
                run["created_at"] = run["created_at"].astimezone(timezone.utc).isoformat()
        return jsonify({"runs": runs})
    except Exception:
        app.logger.exception("Could not load analysis history")
        return jsonify({"error": "Unable to load history. Check the cloud database connection."}), 503


@app.get("/api/history/<int:run_id>")
def api_history_detail(run_id):
    if not database_url():
        return jsonify({"error": "Cloud history is not configured."}), 503
    try:
        with get_connection() as conn:
            run = conn.execute("""
                SELECT id, created_at, language, source_chars, source_lines, issue_count, status
                FROM analysis_runs WHERE id = %s
            """, (run_id,)).fetchone()
            if not run:
                return jsonify({"error": "Analysis run not found."}), 404
            findings = conn.execute("""
                SELECT rule_id, severity, line_number AS line, title, message, suggestion
                FROM findings WHERE run_id = %s ORDER BY id
            """, (run_id,)).fetchall()
        if isinstance(run["created_at"], datetime):
            run["created_at"] = run["created_at"].astimezone(timezone.utc).isoformat()
        return jsonify({"run": run, "findings": findings})
    except Exception:
        app.logger.exception("Could not load analysis detail")
        return jsonify({"error": "Unable to load analysis details."}), 503


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request is too large. Please submit a smaller code snippet."}), 413


if __name__ == "__main__":
    # Convenience for local development only. Render runs Gunicorn via its start command.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
