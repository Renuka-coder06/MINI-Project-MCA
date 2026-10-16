import ast
import keyword
import re


def _finding(rule_id, severity, line, title, message, suggestion):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "line": line,
        "title": title,
        "message": message,
        "suggestion": suggestion,
    }


def analyze_python(source):
    """Analyze Python source without executing it. Returns (findings, syntax_error)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        line = exc.lineno or 1
        msg = exc.msg or "Invalid Python syntax."
        return ([_finding(
            "PY-SYNTAX", "error", line, "Syntax error",
            f"Python could not parse this code: {msg}",
            "Check the indicated line for missing colons, unmatched brackets, indentation, or spelling mistakes."
        )], True)

    findings = []
    imported_names = {}
    used_names = set()
    function_nodes = []

    class NameUseVisitor(ast.NodeVisitor):
        def visit_Name(self, node):
            used_names.add(node.id)

    NameUseVisitor().visit(tree)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                imported_names[local_name] = getattr(node, "lineno", 1)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_nodes.append(node)
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", node.name) or keyword.iskeyword(node.name):
                findings.append(_finding(
                    "PY-NAME-001", "warning", node.lineno, "Function name style",
                    f"'{node.name}' does not follow the usual Python snake_case naming style.",
                    "Consider a lowercase name with words separated by underscores, such as calculate_total."
                ))
            end_line = getattr(node, "end_lineno", node.lineno)
            if end_line - node.lineno + 1 > 30:
                findings.append(_finding(
                    "PY-FUNC-001", "warning", node.lineno, "Long function",
                    f"'{node.name}' spans {end_line - node.lineno + 1} lines, which can make it harder to understand.",
                    "Consider extracting cohesive steps into smaller helper functions while preserving behavior."
                ))
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(_finding(
                        "PY-DEFAULT-001", "error", getattr(default, "lineno", node.lineno),
                        "Mutable default argument",
                        f"Function '{node.name}' uses a mutable object as a default argument.",
                        "Use None as the default and create a fresh list/dictionary/set inside the function."
                    ))
                    break
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(_finding(
                "PY-EXCEPT-001", "warning", node.lineno, "Bare except clause",
                "A bare except can catch unexpected exceptions and make failures difficult to diagnose.",
                "Catch the specific exception types you expect, and handle them intentionally."
            ))
        elif isinstance(node, ast.Compare):
            # Avoid fragile advice for complex comparisons; this rule only flags literal `== True/False`.
            if any(isinstance(c, ast.Constant) and isinstance(c.value, bool) for c in node.comparators):
                findings.append(_finding(
                    "PY-BOOL-001", "info", node.lineno, "Boolean comparison",
                    "Comparing a value directly to True or False is often unnecessary.",
                    "For booleans, consider `if condition:` or `if not condition:` when that matches the intended logic."
                ))

    for name, line in imported_names.items():
        if name not in used_names and name != "*":
            findings.append(_finding(
                "PY-IMPORT-001", "info", line, "Possibly unused import",
                f"Imported name '{name}' does not appear to be used in this snippet.",
                "Remove the import if it is genuinely unused. This check is approximate for aliases and dynamic usage."
            ))

    # Stable ordering makes results easy to read and test.
    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (item.get("line") or 0, severity_order.get(item["severity"], 9), item["rule_id"]))
    return findings, False
