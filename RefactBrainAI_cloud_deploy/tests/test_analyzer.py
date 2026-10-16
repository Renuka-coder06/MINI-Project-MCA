from analyzer import analyze_python


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
