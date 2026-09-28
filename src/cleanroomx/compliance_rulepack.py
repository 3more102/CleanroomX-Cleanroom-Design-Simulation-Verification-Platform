from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import html
import json
import math
from typing import Any


RULE_PACK_SCHEMA = "cleanroomx.compliance-rule-pack"
RULE_PACK_SCHEMA_VERSION = 1

_OPERATORS = {"exists", "equals", "min", "max", "range", "one_of"}
_PACK_KEYS = {"schema", "schema_version", "id", "version", "title", "source", "rules"}
_RULE_KEYS = {
    "id",
    "title",
    "evidence_path",
    "operator",
    "expected",
    "unit",
    "tolerance",
    "source",
    "reference",
}
_INPUT_KEYS = {"name", "rule_pack", "evidence"}
_MISSING = object()


def _reject_unknown_keys(value: dict, allowed: set[str], context: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError(f"{context} contains unknown field(s): {', '.join(extra)}")


def _nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite JSON number")
    return result


def _validate_json_value(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return copy.deepcopy(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field_name} must be a finite JSON number")
        return copy.deepcopy(value)
    if isinstance(value, list):
        return [
            _validate_json_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} object keys must be strings")
            normalized[key] = _validate_json_value(item, f"{field_name}.{key}")
        return normalized
    raise ValueError(f"{field_name} must contain only JSON-compatible values")


def _decode_pointer_token(token: str, field_name: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(token):
        char = token[index]
        if char != "~":
            output.append(char)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise ValueError(f"{field_name} contains an invalid JSON Pointer escape")
        output.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(output)


def _pointer_tokens(pointer: str, field_name: str = "evidence_path") -> tuple[str, ...]:
    _nonempty_string(pointer, field_name)
    if not pointer.startswith("/"):
        raise ValueError(f"{field_name} must be an RFC 6901 JSON Pointer starting with '/'")
    return tuple(
        _decode_pointer_token(token, field_name)
        for token in pointer.split("/")[1:]
    )


def _resolve_pointer(document: Any, pointer: str) -> Any:
    current = document
    for token in _pointer_tokens(pointer):
        if isinstance(current, dict):
            if token not in current:
                return _MISSING
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                return _MISSING
            index = int(token)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _canonical_sha256(value: dict) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ComplianceRule:
    id: str
    title: str
    evidence_path: str
    operator: str
    expected: Any
    unit: str | None
    tolerance: float
    source: str | None
    reference: str | None


@dataclass(frozen=True)
class ComplianceRulePack:
    id: str
    version: str
    title: str
    source: str
    rules: tuple[ComplianceRule, ...]

    def to_dict(self) -> dict:
        rules = []
        for rule in self.rules:
            item = {
                "id": rule.id,
                "title": rule.title,
                "evidence_path": rule.evidence_path,
                "operator": rule.operator,
                "unit": rule.unit,
                "tolerance": rule.tolerance,
                "source": rule.source,
                "reference": rule.reference,
            }
            if rule.operator != "exists":
                item["expected"] = copy.deepcopy(rule.expected)
            rules.append(item)
        return {
            "schema": RULE_PACK_SCHEMA,
            "schema_version": RULE_PACK_SCHEMA_VERSION,
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "source": self.source,
            "rules": rules,
        }


@dataclass(frozen=True)
class ComplianceCheck:
    name: str
    rule_pack: ComplianceRulePack
    evidence: dict


def _parse_expected(operator: str, rule: dict, field_name: str) -> Any:
    has_expected = "expected" in rule
    if operator == "exists":
        if has_expected:
            raise ValueError(f"{field_name}.expected is not allowed for operator 'exists'")
        return None
    if not has_expected:
        raise ValueError(f"{field_name}.expected is required for operator {operator!r}")

    expected = _validate_json_value(rule["expected"], f"{field_name}.expected")
    if operator in {"min", "max"}:
        return _finite_number(expected, f"{field_name}.expected")
    if operator == "range":
        if not isinstance(expected, dict) or set(expected) != {"min", "max"}:
            raise ValueError(
                f"{field_name}.expected must contain exactly min and max for operator 'range'"
            )
        minimum = _finite_number(expected["min"], f"{field_name}.expected.min")
        maximum = _finite_number(expected["max"], f"{field_name}.expected.max")
        if minimum > maximum:
            raise ValueError(f"{field_name}.expected.min must be <= expected.max")
        return {"min": minimum, "max": maximum}
    if operator == "one_of":
        if not isinstance(expected, list) or not expected:
            raise ValueError(
                f"{field_name}.expected must be a non-empty array for operator 'one_of'"
            )
        return expected
    return expected


def rule_pack_from_dict(data: dict) -> ComplianceRulePack:
    if not isinstance(data, dict):
        raise ValueError("rule_pack must be an object")
    _reject_unknown_keys(data, _PACK_KEYS, "rule_pack")
    if data.get("schema") != RULE_PACK_SCHEMA:
        raise ValueError(f"rule_pack.schema must be {RULE_PACK_SCHEMA!r}")
    if data.get("schema_version") != RULE_PACK_SCHEMA_VERSION:
        raise ValueError(
            f"rule_pack.schema_version must be {RULE_PACK_SCHEMA_VERSION}"
        )

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("rule_pack.rules must be a non-empty array")

    rules: list[ComplianceRule] = []
    ids: set[str] = set()
    for index, item in enumerate(raw_rules):
        field_name = f"rule_pack.rules[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown_keys(item, _RULE_KEYS, field_name)
        rule_id = _nonempty_string(item.get("id"), f"{field_name}.id")
        if rule_id in ids:
            raise ValueError(f"duplicate compliance rule id: {rule_id!r}")
        ids.add(rule_id)
        operator = _nonempty_string(item.get("operator"), f"{field_name}.operator")
        if operator not in _OPERATORS:
            raise ValueError(
                f"{field_name}.operator must be one of {', '.join(sorted(_OPERATORS))}"
            )
        evidence_path = _nonempty_string(
            item.get("evidence_path"), f"{field_name}.evidence_path"
        )
        _pointer_tokens(evidence_path, f"{field_name}.evidence_path")
        tolerance = _finite_number(
            item.get("tolerance", 0.0), f"{field_name}.tolerance"
        )
        if tolerance < 0:
            raise ValueError(f"{field_name}.tolerance must be >= 0")
        unit = item.get("unit")
        if unit is not None:
            unit = _nonempty_string(unit, f"{field_name}.unit")
        source = item.get("source")
        if source is not None:
            source = _nonempty_string(source, f"{field_name}.source")
        reference = item.get("reference")
        if reference is not None:
            reference = _nonempty_string(reference, f"{field_name}.reference")
        expected = _parse_expected(operator, item, field_name)
        if operator in {"min", "max", "range"} and tolerance < 0:
            raise ValueError(f"{field_name}.tolerance must be >= 0")
        if operator in {"equals"} and tolerance and (
            isinstance(expected, bool) or not isinstance(expected, (int, float))
        ):
            raise ValueError(
                f"{field_name}.tolerance requires numeric expected value for operator 'equals'"
            )
        rules.append(
            ComplianceRule(
                id=rule_id,
                title=_nonempty_string(item.get("title"), f"{field_name}.title"),
                evidence_path=evidence_path,
                operator=operator,
                expected=expected,
                unit=unit,
                tolerance=tolerance,
                source=source,
                reference=reference,
            )
        )

    return ComplianceRulePack(
        id=_nonempty_string(data.get("id"), "rule_pack.id"),
        version=_nonempty_string(data.get("version"), "rule_pack.version"),
        title=_nonempty_string(data.get("title"), "rule_pack.title"),
        source=_nonempty_string(data.get("source"), "rule_pack.source"),
        rules=tuple(rules),
    )


def compliance_check_from_dict(data: dict) -> ComplianceCheck:
    if not isinstance(data, dict):
        raise ValueError("compliance check input must be an object")
    _reject_unknown_keys(data, _INPUT_KEYS, "compliance check input")
    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    return ComplianceCheck(
        name=_nonempty_string(data.get("name"), "name"),
        rule_pack=rule_pack_from_dict(data.get("rule_pack")),
        evidence=_validate_json_value(evidence, "evidence"),
    )


def _actual_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return result


def _evaluate_rule(rule: ComplianceRule, actual: Any) -> tuple[bool, float | None]:
    if rule.operator == "exists":
        return True, None
    if rule.operator == "equals":
        if (
            not isinstance(rule.expected, bool)
            and isinstance(rule.expected, (int, float))
        ):
            number = _actual_number(actual)
            if number is None:
                return False, None
            expected = float(rule.expected)
            return abs(number - expected) <= rule.tolerance, number - expected
        return actual == rule.expected, None
    if rule.operator == "one_of":
        return actual in rule.expected, None

    number = _actual_number(actual)
    if number is None:
        return False, None
    if rule.operator == "min":
        expected = float(rule.expected)
        return number + rule.tolerance >= expected, number - expected
    if rule.operator == "max":
        expected = float(rule.expected)
        return number - rule.tolerance <= expected, number - expected
    if rule.operator == "range":
        minimum = float(rule.expected["min"])
        maximum = float(rule.expected["max"])
        passed = number >= minimum - rule.tolerance and number <= maximum + rule.tolerance
        if number < minimum:
            delta = number - minimum
        elif number > maximum:
            delta = number - maximum
        else:
            delta = 0.0
        return passed, delta
    raise AssertionError(f"unhandled operator: {rule.operator}")


def analyze_compliance_check(check: ComplianceCheck) -> dict:
    pack_document = check.rule_pack.to_dict()
    evidence_sha256 = _canonical_sha256(check.evidence)
    findings: list[dict] = []

    for rule in check.rule_pack.rules:
        actual = _resolve_pointer(check.evidence, rule.evidence_path)
        source = rule.source or check.rule_pack.source
        if actual is _MISSING:
            findings.append(
                {
                    "id": rule.id,
                    "title": rule.title,
                    "status": "not_checked",
                    "evidence_path": rule.evidence_path,
                    "evidence_present": False,
                    "operator": rule.operator,
                    "expected": copy.deepcopy(rule.expected),
                    "actual": None,
                    "delta": None,
                    "unit": rule.unit,
                    "tolerance": rule.tolerance,
                    "source": source,
                    "reference": rule.reference,
                    "note": "Required evidence path is not present in the supplied evidence document.",
                }
            )
            continue

        passed, delta = _evaluate_rule(rule, actual)
        findings.append(
            {
                "id": rule.id,
                "title": rule.title,
                "status": "pass" if passed else "fail",
                "evidence_path": rule.evidence_path,
                "evidence_present": True,
                "operator": rule.operator,
                "expected": copy.deepcopy(rule.expected),
                "actual": copy.deepcopy(actual),
                "delta": delta,
                "unit": rule.unit,
                "tolerance": rule.tolerance,
                "source": source,
                "reference": rule.reference,
                "note": None,
            }
        )

    pass_count = sum(item["status"] == "pass" for item in findings)
    fail_count = sum(item["status"] == "fail" for item in findings)
    not_checked_count = sum(item["status"] == "not_checked" for item in findings)
    if fail_count:
        status = "fail"
    elif not_checked_count == len(findings):
        status = "not_checked"
    elif not_checked_count:
        status = "pass_with_unchecked"
    else:
        status = "pass"

    return {
        "name": check.name,
        "status": status,
        "complete": not_checked_count == 0,
        "passed": fail_count == 0,
        "rule_pack": {
            "schema": RULE_PACK_SCHEMA,
            "schema_version": RULE_PACK_SCHEMA_VERSION,
            "id": check.rule_pack.id,
            "version": check.rule_pack.version,
            "title": check.rule_pack.title,
            "source": check.rule_pack.source,
            "sha256": _canonical_sha256(pack_document),
        },
        "evidence_sha256": evidence_sha256,
        "summary": {
            "rule_count": len(findings),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "not_checked_count": not_checked_count,
        },
        "findings": findings,
        "engineering_note": (
            "This result evaluates only the supplied evidence against the supplied rule pack. "
            "It is not a regulatory approval, cleanroom certification, commissioning "
            "acceptance, or statement that the rule pack completely represents an external standard."
        ),
    }


def _md(value: Any) -> str:
    if value is None:
        text = "—"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return html.escape(text).replace("|", "\\|").replace("\n", " ")


def markdown_compliance_report(result: dict) -> str:
    pack = result["rule_pack"]
    lines = [
        "# CleanroomX Compliance Rule-Pack Check",
        "",
        f"- Study: {_md(result['name'])}",
        f"- Status: **{_md(result['status'])}**",
        f"- Complete: **{_md(result['complete'])}**",
        f"- Rule pack: {_md(pack['title'])} ({_md(pack['id'])} v{_md(pack['version'])})",
        f"- Rule-pack SHA-256: `{_md(pack['sha256'])}`",
        f"- Declared source: {_md(pack['source'])}",
        "",
        "| Rule | Status | Evidence path | Operator | Expected | Actual | Unit | Source | Reference |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for finding in result["findings"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(finding["title"]),
                    _md(finding["status"]),
                    _md(finding["evidence_path"]),
                    _md(finding["operator"]),
                    _md(finding["expected"]),
                    _md(finding["actual"]),
                    _md(finding["unit"]),
                    _md(finding["source"]),
                    _md(finding["reference"]),
                ]
            )
            + " |"
        )
    lines.extend(["", _md(result["engineering_note"])])
    return "\n".join(lines) + "\n"
