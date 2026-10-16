from analyzer import analyze_python, analyze_code


def test_syntax_error_is_reported():
    findings, syntax_error = analyze_python("def broken(:\n pass")
    assert syntax_error is True
    assert findings[0]["rule_id"] == "PY-SYNTAX"


def test_camel_case_function_name_is_reported():
    findings, syntax_error = analyze_python("def calculateTotal(items):\n    return sum(items)\n")
    assert syntax_error is False
    assert any(item["rule_id"] == "PY-NAME-001" for item in findings)


def test_mutable_default_is_reported():
    findings, syntax_error = analyze_python("def add_item(item, items=[]):\n    items.append(item)\n    return items\n")
    assert syntax_error is False
    assert any(item["rule_id"] == "PY-DEFAULT-001" for item in findings)


def test_safe_code_returns_findings_list():
    findings, syntax_error = analyze_python("def add(a, b):\n    return a + b\n")
    assert syntax_error is False
    assert isinstance(findings, list)


def test_javascript_detects_var_and_loose_equality():
    findings, syntax_error = analyze_code("var count = 1; if (count == 1) { console.log(count); }", "javascript")
    assert syntax_error is False
    assert any(item["rule_id"] == "JS-VAR-001" for item in findings)
    assert any(item["rule_id"] == "JS-EQ-001" for item in findings)


def test_java_unclosed_brace_is_reported():
    findings, syntax_error = analyze_code("public class Main { public static void main(String[] args) {", "java")
    assert syntax_error is True
    assert any("DELIM" in item["rule_id"] for item in findings)


def test_c_detects_unsafe_gets():
    findings, _ = analyze_code("#include <stdio.h>\nint main(void) { gets(buffer); return 0; }", "c")
    assert any(item["rule_id"] == "C-GETS-001" for item in findings)


def test_cpp_detects_global_using_namespace():
    findings, _ = analyze_code("using namespace std; int main() { return 0; }", "cpp")
    assert any(item["rule_id"] == "CPP-NAMESPACE-001" for item in findings)


def test_unsupported_language_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        analyze_code("code", "ruby")
