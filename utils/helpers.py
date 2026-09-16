"""Algemene helper functies voor defensieve parameter parsing en validatie."""
from datetime import date, datetime
from typing import Any, Optional


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Parseer een waarde veilig naar int, geef default terug bij fout."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_date(val: Any, default: Optional[date] = None) -> Optional[date]:
    """Parseer een ISO-datumstring (YYYY-MM-DD) veilig naar date object."""
    if not val:
        return default
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return date.fromisoformat(str(val).strip())
    except (ValueError, TypeError):
        return default


def safe_str(val: Any, default: str = '') -> str:
    """Trim en strip een string veilig."""
    if val is None:
        return default
    return str(val).strip()
