"""Small helpers shared by the C3 modules."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def as_utc(dt: datetime | None) -> datetime | None:
    """Datetimes read back from SQLite are naive; treat them as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value)  # type: ignore[return-value]
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))  # type: ignore[return-value]


def parse_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else as_utc(dt).isoformat().replace("+00:00", "Z")


def numbers_in(text: str) -> list[float]:
    """All numbers written with digits: '11,000' -> 11000.0."""
    out = []
    for m in _NUM.finditer(text or ""):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def to_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    nums = numbers_in(str(value))
    return nums[0] if len(nums) == 1 else None


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:16]


def norm_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def fmt_value(value, unit: str | None) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    else:
        v = str(value)
    return f"{unit} {v}" if unit else v
