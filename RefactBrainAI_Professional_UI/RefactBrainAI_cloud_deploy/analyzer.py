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


SUPPORTED_LANGUAGES = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "c": "C",
    "cpp": "C++",
}


def _mask_comments_and_strings(source, language):
    """Replace comments/string contents with spaces while preserving newlines.

    This is a lightweight heuristic helper, not a complete language lexer.
    """
    out = list(source)
    i = 0
    n = len(source)
    state = "code"
    quote = ""
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == '/' and nxt == '/':
                out[i] = out[i + 1] = ' '
                i += 2
                state = "line_comment"
                continue
            if language in ("c", "cpp", "java") and ch == '/' and nxt == '*':
                out[i] = out[i + 1] = ' '
                i += 2
                state = "block_comment"
                continue
            if language == "python" and ch == '#':
                out[i] = ' '
                i += 1
                state = "line_comment"
                continue
            if language in ("javascript", "java", "c", "cpp") and ch in ('"', "'"):
                quote = ch
                out[i] = ' '
                i += 1
                state = "string"
                continue
            if language == "javascript" and source.startswith('`', i):
                quote = '`'
                out[i] = ' '
                i += 1
                state = "string"
                continue
        elif state == "line_comment":
            if ch == '\n':
                state = "code"
            else:
                out[i] = ' '
        elif state == "block_comment":
            if ch == '*' and nxt == '/':
                out[i] = out[i + 1] = ' '
                i += 2
                state = "code"
                continue
            if ch != '\n':
                out[i] = ' '
        elif state == "string":
            if ch == '\\':
                if ch != '\n': out[i] = ' '
                if i + 1 < n and source[i + 1] != '\n': out[i + 1] = ' '
                i += 2
                continue
            if ch == quote:
                out[i] = ' '
                state = "code"
            elif ch != '\n':
                out[i] = ' '
        i += 1
    return ''.join(out)


def _analyze_brace_language(source, language):
    """Conservative lexical/static checks for Java, JS, C and C++.

    This intentionally does not claim compiler-grade syntax validation.
    """
    name = SUPPORTED_LANGUAGES[language]
    masked = _mask_comments_and_strings(source, language)
    findings = []
    pairs = {')': '(', ']': '[', '}': '{'}
    stack = []
    mismatch = None
    for index, ch in enumerate(masked):
        if ch in '([{':
            stack.append((ch, masked.count('\n', 0, index) + 1))
        elif ch in ')]}':
            if not stack or stack[-1][0] != pairs[ch]:
                mismatch = (masked.count('\n', 0, index) + 1, ch)
                break
            stack.pop()
    if mismatch:
        line, token = mismatch
        findings.append(_finding(f"{language.upper()}-DELIM-001", "error", line,
            "Unmatched closing delimiter", f"Found '{token}' without a matching opening delimiter.",
            "Check parentheses, brackets, and braces around this line."))
    elif stack:
        token, line = stack[-1]
        findings.append(_finding(f"{language.upper()}-DELIM-002", "error", line,
            "Unclosed delimiter", f"Opening '{token}' does not have a matching closing delimiter.",
            "Add the matching closing delimiter and review nested blocks."))

    lines = source.splitlines()
    if language in ("java", "c", "cpp"):
        for line_no, original in enumerate(lines, 1):
            line = masked.splitlines()[line_no - 1] if line_no <= len(masked.splitlines()) else original
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
            # A conservative heuristic for common missing semicolons; avoid block/control lines.
            if (re.match(r"^(?:return\b|break\b|continue\b|throw\b|\w+(?:\s*\[\])?\s+\w+\s*=|\w+\s*\([^;{}]*\))", stripped)
                and not stripped.endswith((';', '{', '}', ':', ','))
                and not re.match(r"^(?:if|for|while|switch|catch|class|interface|enum|public|private|protected|static|void)\b", stripped)):
                findings.append(_finding(f"{language.upper()}-STYLE-001", "warning", line_no,
                    "Possible missing semicolon", "This line may need a semicolon at the end.",
                    "Check the language grammar and add a semicolon if this is a statement."))
                break

    if language == "java":
        if "public static void main" not in source and re.search(r"\bclass\s+\w+", masked):
            findings.append(_finding("JAVA-ENTRY-001", "info", None, "Main method not detected",
                "No standard public static void main(String[] args) entry point was detected.",
                "This is fine for library classes; add a main method only if this should be a runnable application."))
        if re.search(r"\bSystem\.out\.print(?:ln)?\s*\(", masked):
            findings.append(_finding("JAVA-PRINT-001", "info", None, "Console output detected",
                "System.out output is present in the snippet.",
                "For production applications, consider a logging framework when appropriate."))
    elif language == "javascript":
        if re.search(r"\bvar\s+", masked):
            findings.append(_finding("JS-VAR-001", "warning", None, "Legacy var declaration",
                "The snippet uses var, whose function-scoped behavior can cause accidental reassignment issues.",
                "Prefer const by default and let when reassignment is required."))
        if re.search(r"\beval\s*\(", masked):
            findings.append(_finding("JS-EVAL-001", "warning", None, "eval() usage",
                "eval() evaluates a string as code and can introduce security and maintenance risks.",
                "Avoid eval where possible; use explicit parsing or direct function calls."))
        if re.search(r"(?<![=])==(?!=)", masked):
            findings.append(_finding("JS-EQ-001", "info", None, "Loose equality operator",
                "The code uses ==, which performs type coercion.",
                "Consider === when strict equality is intended."))
    elif language in ("c", "cpp"):
        if re.search(r"\bgets\s*\(", masked):
            findings.append(_finding(f"{language.upper()}-GETS-001", "error", None, "Unsafe gets() call",
                "gets() cannot limit input length and can cause buffer overflows.",
                "Use a bounded input function such as fgets and validate input length."))
        if re.search(r"\bstrcpy\s*\(", masked):
            findings.append(_finding(f"{language.upper()}-STRCPY-001", "warning", None, "Unbounded string copy",
                "strcpy() does not check the destination buffer capacity.",
                "Check buffer sizes carefully and prefer a safer bounded approach where appropriate."))
        if language == "cpp" and re.search(r"\busing\s+namespace\s+std\s*;", masked):
            findings.append(_finding("CPP-NAMESPACE-001", "info", None, "Global using-directive",
                "using namespace std; introduces names into the global namespace.",
                "Prefer qualified std:: names, especially in headers, to avoid name collisions."))

    if not findings:
        findings.append(_finding(f"{language.upper()}-BASE-001", "info", None, "No heuristic issues detected",
            f"The basic {name} checks did not detect a problem in this snippet.",
            "This is not a full compiler or linter. Run the official compiler/runtime and a language-specific linter for stronger validation."))
    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (item.get("line") or 0, severity_order.get(item["severity"], 9), item["rule_id"]))
    # The lexical heuristics are not comprehensive enough to claim complete syntax validation.
    syntax_error = any(item["severity"] == "error" and "DELIM" in item["rule_id"] for item in findings)
    return findings, syntax_error


def analyze_code(source, language="python"):
    """Dispatch to the supported language analyzer without executing submitted code."""
    language = (language or "python").lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language. Choose one of: {', '.join(SUPPORTED_LANGUAGES)}")
    if language == "python":
        return analyze_python(source)
    return _analyze_brace_language(source, language)
