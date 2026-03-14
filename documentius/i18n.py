import locale as _locale

try:
    _loc = _locale.getlocale()[0] or ""
except (ValueError, TypeError):
    _loc = ""

_IT: bool = _loc.startswith("it")


def _t(it: str, en: str) -> str:
    return it if _IT else en
