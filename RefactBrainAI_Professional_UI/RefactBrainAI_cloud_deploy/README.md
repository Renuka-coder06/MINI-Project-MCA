# RefactBrainAI — cloud-deployable prototype

RefactBrainAI is a student-project prototype for multi-language code-quality analysis and refactoring guidance for Python, Java, JavaScript, C, and C++. Python uses deterministic AST-based rules; Java, JavaScript, C, and C++ use lightweight language-aware static heuristics. **It is not yet an external AI model**, and its findings are limited to the rules implemented in `analyzer.py`.

## Architecture

- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python 3.12+, Flask, Gunicorn
- Business layer: Python `ast` rules plus lightweight Java/JavaScript/C/C++ heuristics; submitted code is never executed
- Database: Supabase-hosted PostgreSQL via Psycopg
- Hosting: Render web service
- Source control: GitHub

## Deploy globally

### 1. Create a Supabase project
1. Sign in to Supabase and create a project.
2. Open **Connect** in the project dashboard.
3. Copy a PostgreSQL connection string. For a persistent Render web service, use the direct connection if network support fits your setup; if you need IPv4 compatibility, use the **Session pooler** connection string. Do not guess the pooler host.
4. Keep the database password private. URL-encode reserved characters in the password if necessary.
5. The application creates `analysis_runs` and `findings` tables when `DATABASE_URL` is set and the app can connect.

### 2. Push this project to GitHub
1. Download/extract this project ZIP.
2. Create a new GitHub repository, e.g. `RefactBrainAI`.
3. Upload the contents of this folder to the repository root (not the outer ZIP folder).
4. Confirm `app.py`, `requirements.txt`, `render.yaml`, `analyzer.py`, `templates/`, and `static/` appear at repository root.

You can use GitHub's web interface to upload files, or use Git from a terminal.

### 3. Deploy on Render
1. Create a Render account and connect GitHub.
2. In Render choose **New + → Blueprint** if available for your account, or **New + → Web Service** and select the repository.
3. If using the Web Service form, set:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Health check path: `/health`
4. In the service's Environment settings add `DATABASE_URL` with the connection string copied from Supabase. Do not commit it to GitHub.
5. Deploy and wait for the build to finish. Open the `onrender.com` URL shown by Render.

### 4. Verify the live app
- Open `/health`; expected JSON includes `"status":"ok"`.
- Open `/api/status`; confirm `"database_connected": true`.
- On the home page, click **Load sample**, then **Analyze code**.
- Confirm findings are displayed and the **Saved** metric says `Yes`.
- Open **Analysis history** and verify that the run appears.

## Environment variables
- `DATABASE_URL` — required for cloud persistence/history. If absent, analysis still runs but history will not persist.

Do not put database passwords or API keys in frontend JavaScript, commit them to Git, or paste them into screenshots. If a database password was exposed, rotate it.

## Implemented endpoints
- `GET /` — frontend
- `GET /health` — deployment health check
- `GET /api/status` — backend/database status
- `POST /api/analyze` — analyze submitted Python source
- `GET /api/history` — recent saved run summaries
- `GET /api/history/<id>` — saved finding detail

## Current analysis rules
- Python syntax errors
- Non-snake_case function names
- Functions longer than 30 lines
- Mutable list/dict/set default arguments
- Bare `except` clauses
- Direct comparisons to boolean literals
- Possibly unused imports (approximate heuristic)

For Java, JavaScript, C, and C++, delimiter checks and code-quality rules are heuristic and are not complete parsers or compiler diagnostics. Use javac, Node.js/ESLint, gcc/clang, or another language-specific tool for full syntax/build checks. This is a learning prototype, not a security scanner or a replacement for a full linter. Do not submit secrets or confidential code. The server never executes submitted code; however, it stores code statistics and findings, not the raw source. History is not user-authenticated in this prototype, so only use it for non-confidential demonstration snippets.

## Tests
Run `pytest` to exercise the analysis rules. Render uses Gunicorn; `app.py`'s development server is only a local convenience and is not the production server.
