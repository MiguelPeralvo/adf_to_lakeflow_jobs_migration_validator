"""Output comparator for ADF-vs-Databricks parallel testing."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Per-activity comparison between ADF and Databricks outputs."""

    activity_name: str
    adf_output: str | None
    databricks_output: str | None
    match: bool
    diff: str | None


@dataclass(frozen=True, slots=True)
class OutputComparator:
    """Compare output maps and compute an equivalence score."""

    float_tolerance: float = 1e-6

    def compare(self, adf_outputs: dict[str, str], databricks_outputs: dict[str, str]) -> list[ComparisonResult]:
        names = sorted(set(adf_outputs) | set(databricks_outputs))
        results: list[ComparisonResult] = []

        for name in names:
            adf_raw = adf_outputs.get(name)
            db_raw = databricks_outputs.get(name)
            if adf_raw is None and db_raw is None:
                results.append(
                    ComparisonResult(
                        activity_name=name,
                        adf_output=None,
                        databricks_output=None,
                        match=True,
                        diff=None,
                    )
                )
                continue
            if adf_raw is None:
                results.append(
                    ComparisonResult(
                        activity_name=name,
                        adf_output=None,
                        databricks_output=db_raw,
                        match=False,
                        diff="missing in adf outputs",
                    )
                )
                continue
            if db_raw is None:
                results.append(
                    ComparisonResult(
                        activity_name=name,
                        adf_output=adf_raw,
                        databricks_output=None,
                        match=False,
                        diff="missing in databricks outputs",
                    )
                )
                continue

            match = outputs_equivalent(adf_raw, db_raw, tolerance=self.float_tolerance)
            results.append(
                ComparisonResult(
                    activity_name=name,
                    adf_output=adf_raw,
                    databricks_output=db_raw,
                    match=match,
                    diff=None if match else "normalized outputs differ",
                )
            )

        return results

    def score(self, results: list[ComparisonResult]) -> float:
        if not results:
            return 1.0
        matched = sum(1 for item in results if item.match)
        return matched / len(results)


def outputs_equivalent(a: str, b: str, *, tolerance: float = 1e-6) -> bool:
    """Compare two output values using tolerant typed normalization."""
    return _equivalent(_normalize_scalar_or_json(a), _normalize_scalar_or_json(b), tolerance=tolerance)


def _normalize_scalar_or_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ""

        parsed_json = _try_json(stripped)
        if parsed_json is not _UNPARSEABLE:
            return _normalize_recursive(parsed_json)

        parsed_dt = _try_parse_datetime(stripped)
        if parsed_dt is not None:
            return parsed_dt

        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered in {"null", "none"}:
            return None

        parsed_num = _try_parse_number(stripped)
        if parsed_num is not None:
            return parsed_num

        return stripped

    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, dict)):
        return _normalize_recursive(value)
    return str(value)


def _normalize_recursive(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_recursive(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_recursive(item) for item in value]
    if isinstance(value, str):
        parsed_dt = _try_parse_datetime(value.strip())
        if parsed_dt is not None:
            return parsed_dt
        parsed_num = _try_parse_number(value.strip())
        if parsed_num is not None:
            return parsed_num
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered in {"null", "none"}:
            return None
        return value.strip()
    return value


def _equivalent(a: Any, b: Any, *, tolerance: float) -> bool:
    if isinstance(a, datetime) and isinstance(b, datetime):
        return a == b

    if isinstance(a, bool) or isinstance(b, bool):
        return a is b

    if _is_number(a) and _is_number(b):
        a_num = float(a)
        b_num = float(b)
        if math.isnan(a_num) and math.isnan(b_num):
            return True
        if a_num == b_num:
            return True
        return abs(a_num - b_num) <= tolerance

    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(_equivalent(a[key], b[key], tolerance=tolerance) for key in a)

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_equivalent(left, right, tolerance=tolerance) for left, right in zip(a, b, strict=True))

    return a == b


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _try_parse_number(value: str) -> int | float | None:
    lowered = value.lower()
    if lowered in ("nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"):
        return float(lowered.replace("infinity", "inf"))
    try:
        if any(ch in value for ch in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return None


def _try_parse_datetime(value: str) -> datetime | None:
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_UNPARSEABLE = object()


def _try_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return _UNPARSEABLE
