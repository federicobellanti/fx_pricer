from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Placeholder holiday calendars
# Each currency maps to a function that returns True if the date is a holiday.
# Replace the body of each function with real holiday rules when available.
# ---------------------------------------------------------------------------

def _is_holiday_USD(d: date) -> bool:
    return False

def _is_holiday_EUR(d: date) -> bool:
    return False

def _is_holiday_GBP(d: date) -> bool:
    return False

def _is_holiday_JPY(d: date) -> bool:
    return False

def _is_holiday_CHF(d: date) -> bool:
    return False

def _is_holiday_CAD(d: date) -> bool:
    return False

def _is_holiday_AUD(d: date) -> bool:
    return False

def _is_holiday_NZD(d: date) -> bool:
    return False

def _is_holiday_SEK(d: date) -> bool:
    return False

def _is_holiday_NOK(d: date) -> bool:
    return False

def _is_holiday_DKK(d: date) -> bool:
    return False

def _is_holiday_SGD(d: date) -> bool:
    return False

def _is_holiday_HKD(d: date) -> bool:
    return False

def _is_holiday_MXN(d: date) -> bool:
    return False

def _is_holiday_ZAR(d: date) -> bool:
    return False

def _is_holiday_TRY(d: date) -> bool:
    return False

def _is_holiday_PLN(d: date) -> bool:
    return False

def _is_holiday_THB(d: date) -> bool:
    return False

def _is_holiday_CNY(d: date) -> bool:
    return False

def _is_holiday_AED(d: date) -> bool:
    return False

def _is_holiday_KWD(d: date) -> bool:
    return False

def _is_holiday_QAR(d: date) -> bool:
    return False

def _is_holiday_SAR(d: date) -> bool:
    return False

def _is_holiday_RON(d: date) -> bool:
    return False

def _is_holiday_HUF(d: date) -> bool:
    return False


# ---------------------------------------------------------------------------
# Registry — maps currency code to its holiday function
# ---------------------------------------------------------------------------

HOLIDAY_CALENDARS = {
    "USD": _is_holiday_USD,
    "EUR": _is_holiday_EUR,
    "GBP": _is_holiday_GBP,
    "JPY": _is_holiday_JPY,
    "CHF": _is_holiday_CHF,
    "CAD": _is_holiday_CAD,
    "AUD": _is_holiday_AUD,
    "NZD": _is_holiday_NZD,
    "SEK": _is_holiday_SEK,
    "NOK": _is_holiday_NOK,
    "DKK": _is_holiday_DKK,
    "SGD": _is_holiday_SGD,
    "HKD": _is_holiday_HKD,
    "MXN": _is_holiday_MXN,
    "ZAR": _is_holiday_ZAR,
    "TRY": _is_holiday_TRY,
    "PLN": _is_holiday_PLN,
    "THB": _is_holiday_THB,
    "CNY": _is_holiday_CNY,
    "AED": _is_holiday_AED,
    "KWD": _is_holiday_KWD,
    "QAR": _is_holiday_QAR,
    "SAR": _is_holiday_SAR,
    "RON": _is_holiday_RON,
    "HUF": _is_holiday_HUF,
}


# ---------------------------------------------------------------------------
# Core calendar functions
# ---------------------------------------------------------------------------

def is_good_business_day(d: date, currencies: list) -> bool:
    """
    Returns True if date d is a good business day for ALL currencies in the list.
    A date is bad if it falls on a weekend or is a holiday for any currency.
    """
    # Weekend check
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # Holiday check for each currency
    for ccy in currencies:
        cal = HOLIDAY_CALENDARS.get(ccy)
        if cal and cal(d):
            return False

    return True


def next_business_day(d: date, currencies: list) -> date:
    """Move forward until we find a good business day."""
    d = d + timedelta(days=1)
    while not is_good_business_day(d, currencies):
        d = d + timedelta(days=1)
    return d


def prev_business_day(d: date, currencies: list) -> date:
    """Move backward until we find a good business day."""
    d = d - timedelta(days=1)
    while not is_good_business_day(d, currencies):
        d = d - timedelta(days=1)
    return d


def add_business_days(d: date, n: int, currencies: list) -> date:
    """Add n business days to date d."""
    remaining = n
    current = d
    while remaining > 0:
        current = current + timedelta(days=1)
        if is_good_business_day(current, currencies):
            remaining -= 1
    return current


def modified_following(d: date, currencies: list) -> date:
    """
    Apply Modified Following convention:
    - If d is a good business day, return d unchanged
    - Otherwise move forward to next business day
    - Unless that crosses into a new month, in which case move backward instead
    """
    if is_good_business_day(d, currencies):
        return d

    # Try following
    following = d + timedelta(days=1)
    while not is_good_business_day(following, currencies):
        following = following + timedelta(days=1)

    if following.month == d.month:
        return following

    # Following crossed month end — use preceding instead
    preceding = d - timedelta(days=1)
    while not is_good_business_day(preceding, currencies):
        preceding = preceding - timedelta(days=1)

    return preceding


def get_spot_date(today: date, ccy1: str, ccy2: str, settings: dict) -> date:
    """
    Calculate the spot value date for a currency pair.
    Spot days is driven by the currency with the LONGER settlement (max of the two).
    USD always settles T+2 for this purpose unless paired with CAD or TRY.
    Result is adjusted for weekends and holidays of both currencies plus USD.
    """
    # When one leg is USD, spot days are driven by the non-USD currency
    # For cross pairs (neither is USD), use the longer of the two
    if ccy1 == "USD":
        spot_days = settings[ccy2]["spot_days"]
    elif ccy2 == "USD":
        spot_days = settings[ccy1]["spot_days"]
    else:
        spot_days = max(settings[ccy1]["spot_days"], settings[ccy2]["spot_days"])

    # Calendars to check: both currencies plus USD always
    calendars = list({ccy1, ccy2, "USD"})

    # Add spot_days good business days from today
    spot = add_business_days(today, spot_days, calendars)
    return spot


def add_months(d: date, months: int) -> date:
    """Add a number of calendar months to a date, handling month-end."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    # Handle month-end: if original day does not exist in target month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


def get_tenor_date(spot: date, tenor: str, ccy1: str, ccy2: str) -> date:
    """
    Calculate the value date for a given tenor, starting from spot.
    Applies Modified Following convention.
    Tenor codes: SN, 1W, 2W, 3W, 1M...12M, 15M, 18M, 21M, 1Y, 2Y, 3Y
    """
    calendars = list({ccy1, ccy2, "USD"})

    if tenor == "SN":
        d = add_business_days(spot, 1, calendars)
        return d  # SN is always exactly 1bd — no MF adjustment needed

    elif tenor in ("1W", "SW"):
        d = spot + timedelta(weeks=1)

    elif tenor == "2W":
        d = spot + timedelta(weeks=2)

    elif tenor == "3W":
        d = spot + timedelta(weeks=3)

    elif tenor == "TN":
        # TN is 1 business day BEFORE spot
        d = prev_business_day(spot, calendars)
        return d  # No MF adjustment for pre-spot tenor

    else:
        # Monthly tenors: 1M, 2M ... 12M, 15M, 18M, 21M, 1Y, 2Y, 3Y
        months = _tenor_to_months(tenor)
        if months is None:
            raise ValueError(f"Unknown tenor: {tenor}")
        d = add_months(spot, months)

    return modified_following(d, calendars)


def _tenor_to_months(tenor: str) -> int:
    """Convert tenor string to number of months. Returns None if unrecognised."""
    tenor = tenor.upper()
    if tenor.endswith("M"):
        return int(tenor[:-1])
    elif tenor.endswith("Y"):
        return int(tenor[:-1]) * 12
    return None


def get_all_tenor_dates(today: date, ccy1: str, ccy2: str, settings: dict) -> dict:
    """
    Calculate value dates for all standard output tenors.
    Returns ordered dict: { tenor_label: date }
    """
    OUTPUT_TENORS = [
        "TN", "SPOT", "SN", "1W", "2W", "3W",
        "1M", "2M", "3M", "4M", "5M", "6M",
        "7M", "8M", "9M", "10M", "11M", "1Y",
        "15M", "18M", "21M", "2Y", "3Y"
    ]

    spot = get_spot_date(today, ccy1, ccy2, settings)
    calendars = list({ccy1, ccy2, "USD"})

    tenor_dates = {}
    for tenor in OUTPUT_TENORS:
        if tenor == "SPOT":
            tenor_dates["SPOT"] = spot
        else:
            tenor_dates[tenor] = get_tenor_date(spot, tenor, ccy1, ccy2)

    return tenor_dates


if __name__ == "__main__":
    from datetime import date
    import sys
    sys.path.insert(0, ".")
    from data.fetch_forwards import load_currency_settings

    settings = load_currency_settings()
    today = date.today()

    print(f"Today: {today}")
    print(f"\n--- EUR/GBP Tenor Dates ---")
    tenor_dates = get_all_tenor_dates(today, "EUR", "GBP", settings)
    for tenor, d in tenor_dates.items():
        print(f"  {tenor:>4}: {d}  ({d.strftime('%a')})")

    print(f"\n--- USD/CAD Tenor Dates ---")
    tenor_dates = get_all_tenor_dates(today, "USD", "CAD", settings)
    for tenor, d in tenor_dates.items():
        print(f"  {tenor:>4}: {d}  ({d.strftime('%a')})")