"""Market detection and display helpers (A-share vs US)."""

MARKET_CN = "CN"
MARKET_US = "US"

_CN_SUFFIXES = (".SS", ".SZ", ".BJ")


def detect_market(code: str) -> str:
    """Return MARKET_CN for yfinance A-share codes, else MARKET_US."""
    normalized = (code or "").strip().upper()
    if any(normalized.endswith(suffix) for suffix in _CN_SUFFIXES):
        return MARKET_CN
    return MARKET_US


def normalize_us_ticker(code: str) -> str:
    """Normalize US ticker (uppercase, strip whitespace)."""
    return (code or "").strip().upper()


def currency_symbol(market: str | None = None, code: str | None = None) -> str:
    """Return display currency symbol for a market or stock code."""
    if market is None and code is not None:
        market = detect_market(code)
    return "$" if market == MARKET_US else "¥"


def market_label(market: str) -> str:
    return "美股" if market == MARKET_US else "A股"


def is_cn_market(code: str) -> bool:
    return detect_market(code) == MARKET_CN


def is_us_market(code: str) -> bool:
    return detect_market(code) == MARKET_US
