"""Value kinds — `schemas/values/{kind}.yaml` (§4.5): declared typed-value shapes.

A value kind is instance-declared data, like schemas and invariants, composed
from a small **closed** primitive-constraint vocabulary the checker
interprets — never instance code. A typed claim value is the kind's object
shape: `required` fields present, every present field parsing under its
constraint, undeclared fields inadmissible. Mis-shape is a §13.1 error,
exactly as a `values` violation is; a **missing** typed field stays frontier
under the ordinary owed-ness rules (§4.4, §14).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import available_timezones

import yaml

KIND_KEYS = {"kind", "description", "shape", "required"}
SHAPE_ENTRY_KEYS = {"constraint", "values", "pattern", "min", "max", "description"}

# The primitive-constraint vocabulary is closed (§4.5) — grown by amendment,
# never minted per instance.
PRIMITIVES = {
    "string", "number", "integer", "boolean", "decimal", "enum", "pattern", "range",
    "iso-instant", "iso-date", "iana-zone", "iso-4217", "latitude", "longitude",
}

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Current ISO 4217 active alphabetic codes (~180) — the closed part is
# mechanical (recognizing a code), never ontological; embedded here so the
# checker never phones out. Includes the fund codes (XAU/XAG/XPD/XPT), the
# IMF's XDR, the no-currency XXX, and the testing code XTS alongside ordinary
# national currencies.
ISO_4217_CODES = frozenset("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN
BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD
CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK
DJF DKK DOP DZD
EGP ERN ETB EUR
FJD FKP
GBP GEL GHS GIP GMD GNF GTQ GYD
HKD HNL HTG HUF
IDR ILS INR IQD IRR ISK
JMD JOD JPY
KES KGS KHR KMF KPW KRW KWD KYD KZT
LAK LBP LKR LRD LSL LYD
MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN
NAD NGN NIO NOK NPR NZD
OMR
PAB PEN PGK PHP PKR PLN PYG
QAR
RON RSD RUB RWF
SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL
THB TJS TMT TND TOP TRY TTD TWD TZS
UAH UGX USD USN UYI UYU UYW UZS
VED VES VND VUV
WST
XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA XXX
YER
ZAR ZMW ZWG
""".split())

_TZ_CACHE: frozenset[str] | None = None


def _timezones() -> frozenset[str]:
    global _TZ_CACHE
    if _TZ_CACHE is None:
        _TZ_CACHE = frozenset(available_timezones())
    return _TZ_CACHE


def load_kinds(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """All declared value kinds → ({kind: declaration}, shape errors).

    Tolerant of a bad file (dropped, error string emitted) but strict about
    what's kept — `schemas/values/*.yaml`, kind == filename stem.
    """
    out: dict[str, dict] = {}
    errors: list[str] = []
    base = ledger_root / "schemas" / "values"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        where = f"schemas/values/{f.name}"
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            errors.append(f"{where}: invalid YAML — {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{where}: top level must be a mapping")
            continue
        if data.get("kind") != f.stem:
            errors.append(f"{where}: kind {data.get('kind')!r} != filename stem {f.stem!r}")
            continue
        unknown = set(data) - KIND_KEYS
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        shape = data.get("shape")
        if not isinstance(shape, dict):
            errors.append(f"{where}: shape must be a mapping of field-name to entry dict")
            shape = {}
        for fname, entry in shape.items():
            ew = f"{where}: shape field {fname!r}"
            if not isinstance(entry, dict):
                errors.append(f"{ew} must be a mapping")
                continue
            bad = set(entry) - SHAPE_ENTRY_KEYS
            if bad:
                errors.append(f"{ew} unknown keys {sorted(bad)}")
            constraint = entry.get("constraint")
            if constraint not in PRIMITIVES:
                errors.append(f"{ew} constraint {constraint!r} is not a known primitive "
                              f"(allowed: {sorted(PRIMITIVES)})")
            values = entry.get("values")
            if constraint == "enum":
                if not (isinstance(values, list) and values
                        and all(isinstance(v, str) for v in values)):
                    errors.append(f"{ew} enum constraint requires values: a non-empty "
                                  "list of strings")
            elif values is not None:
                errors.append(f"{ew} values is only admissible on an enum constraint")
            pattern = entry.get("pattern")
            if constraint == "pattern":
                if not isinstance(pattern, str):
                    errors.append(f"{ew} pattern constraint requires pattern: a regex string")
                else:
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        errors.append(f"{ew} pattern {pattern!r} is not a valid regex — {e}")
            elif pattern is not None:
                errors.append(f"{ew} pattern is only admissible on a pattern constraint")
            minv, maxv = entry.get("min"), entry.get("max")
            if constraint == "range":
                for bound_name, bound in (("min", minv), ("max", maxv)):
                    if bound is not None and (isinstance(bound, bool)
                                              or not isinstance(bound, (int, float))):
                        errors.append(f"{ew} {bound_name} must be a number")
            elif minv is not None or maxv is not None:
                errors.append(f"{ew} min/max is only admissible on a range constraint")
        required = data.get("required")
        if required is not None:
            if not (isinstance(required, list) and all(isinstance(r, str) for r in required)):
                errors.append(f"{where}: required must be a list of strings")
            else:
                for r in required:
                    if r not in shape:
                        errors.append(f"{where}: required names undeclared shape field {r!r}")
        out[f.stem] = data
    return out, errors


def _check_field(entry: dict, value: object) -> str | None:
    """One shape entry's constraint against a present field value → issue text, or None."""
    constraint = entry.get("constraint")
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if constraint == "string":
        if not isinstance(value, str):
            return "must be a string"
    elif constraint == "boolean":
        if not isinstance(value, bool):
            return "must be a boolean"
    elif constraint == "number":
        if not is_number:
            return "must be a number"
    elif constraint == "integer":
        if not (isinstance(value, int) and not isinstance(value, bool)):
            return "must be an integer"
    elif constraint == "decimal":
        if not (isinstance(value, str) and _DECIMAL_RE.match(value)):
            return "must be a decimal string (never a JSON float)"
    elif constraint == "enum":
        values = entry.get("values") or []
        if value not in values:
            return f"{value!r} not among declared values {values}"
    elif constraint == "pattern":
        if not isinstance(value, str):
            return "must be a string"
        pattern = entry.get("pattern")
        if not (isinstance(pattern, str) and re.fullmatch(pattern, value)):
            return f"{value!r} does not match pattern {pattern!r}"
    elif constraint == "range":
        if not is_number:
            return "must be a number"
        minv, maxv = entry.get("min"), entry.get("max")
        if minv is not None and value < minv:
            return f"{value!r} is below min {minv!r}"
        if maxv is not None and value > maxv:
            return f"{value!r} is above max {maxv!r}"
    elif constraint == "iso-date":
        if not isinstance(value, str):
            return "must be an ISO date string"
        try:
            date.fromisoformat(value)
        except ValueError:
            return f"{value!r} is not a valid ISO date"
    elif constraint == "iso-instant":
        if not (isinstance(value, str) and "T" in value):
            return "must be an ISO instant string (date alone is not an instant)"
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return f"{value!r} is not a valid ISO instant"
    elif constraint == "iana-zone":
        if not (isinstance(value, str) and value in _timezones()):
            return f"{value!r} is not a known IANA timezone"
    elif constraint == "iso-4217":
        if not (isinstance(value, str) and value in ISO_4217_CODES):
            return f"{value!r} is not a known ISO 4217 currency code"
    elif constraint == "latitude":
        if not (is_number and -90 <= value <= 90):
            return "must be a number in [-90, 90]"
    elif constraint == "longitude" and not (is_number and -180 <= value <= 180):
        return "must be a number in [-180, 180]"
    return None


def validate_value(kind_decl: dict, value: object) -> list[str]:
    """A claim `value` against a declared kind's object shape (§4.5) → issue
    strings, empty when it conforms."""
    kind = kind_decl.get("kind", "?")
    if not isinstance(value, dict):
        return [f"value kind {kind!r}: value must be an object, got "
                f"{type(value).__name__}"]
    shape = kind_decl.get("shape") if isinstance(kind_decl.get("shape"), dict) else {}
    required = kind_decl.get("required") if isinstance(kind_decl.get("required"), list) else []
    issues: list[str] = []
    for rname in required:
        if rname not in value:
            issues.append(f"value kind {kind!r}: missing required field {rname!r}")
    for fname in value:
        if fname not in shape:
            issues.append(f"value kind {kind!r}: undeclared field {fname!r}")
    for fname, entry in shape.items():
        if fname not in value or not isinstance(entry, dict):
            continue
        issue = _check_field(entry, value[fname])
        if issue:
            issues.append(f"value kind {kind!r}: field {fname!r} {issue}")
    return issues


def validate_array_value(kind_decl: dict, value: object) -> list[str]:
    """`validate_value` applied per element of a structured-array field/element
    declaring a kind (§4.5, §5.1: one object per declared element)."""
    if not isinstance(value, list):
        kind = kind_decl.get("kind", "?")
        return [f"value kind {kind!r}: value must be an array of objects, got "
                f"{type(value).__name__}"]
    issues: list[str] = []
    for i, el in enumerate(value):
        issues.extend(f"[{i}] {issue}" for issue in validate_value(kind_decl, el))
    return issues
