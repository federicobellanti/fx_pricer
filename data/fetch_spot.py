import asyncio
from playwright.async_api import async_playwright
import pandas as pd


def load_currency_settings(csv_path="CCY_Settings.csv"):
    """Load currency settings from CSV into a dictionary."""
    df = pd.read_csv(csv_path)
    settings = {}
    for _, row in df.iterrows():
        ccy = row["CURRENCY"]
        settings[ccy] = {
            "row": None if pd.isna(row["ROW"]) else int(row["ROW"]),
            "sense": int(row["SENSE"]),
            "divider": int(row["DIVIDER"]),
            "spot_days": int(row["SPOT"])
        }
    return settings


def build_spot_url(currency, settings):
    """
    Build the investing.com URL for a given currency vs USD.
    SENSE=1  (CCY/USD): eur-usd, gbp-usd, aud-usd, nzd-usd
    SENSE=-1 (USD/CCY): usd-jpy, usd-chf, usd-cad etc.
    """
    if currency == "USD":
        return None
    ccy = currency.lower()
    sense = settings[currency]["sense"]
    if sense == 1:
        return f"https://www.investing.com/currencies/{ccy}-usd"
    else:
        return f"https://www.investing.com/currencies/usd-{ccy}"


async def _fetch_single_spot(page, currency, settings):
    """
    Fetch spot rate for a single currency vs USD using an existing page object.
    Returns float as quoted on investing.com, or None on failure.
    """
    if currency == "USD":
        return 1.0

    url = build_spot_url(currency, settings)
    if url is None:
        return None

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector(
            "[data-test='instrument-price-last']",
            timeout=15000
        )
        price_text = await page.inner_text("[data-test='instrument-price-last']")
        price = float(price_text.replace(",", "").strip())
        return price

    except Exception as e:
        print(f"Error fetching spot for {currency}: {e}")
        return None


async def _fetch_spot_for_pair(ccy1, ccy2, settings):
    """
    Fetch spot rates for exactly two currencies.
    Opens one browser session, fetches both sequentially, closes.
    Returns dict: { ccy: rate }
    """
    results = {}

    # USD needs no fetch
    currencies_to_fetch = [
        c for c in [ccy1, ccy2] if c != "USD"
    ]

    # Deduplicate in case both are the same (edge case)
    currencies_to_fetch = list(dict.fromkeys(currencies_to_fetch))

    if not currencies_to_fetch:
        return {"USD": 1.0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for ccy in currencies_to_fetch:
            rate = await _fetch_single_spot(page, ccy, settings)
            if rate is not None:
                results[ccy] = rate
            else:
                results[ccy] = None

        await browser.close()

    # Always include USD
    results["USD"] = 1.0
    return results


def fetch_spot_for_pair(ccy1, ccy2, settings):
    """
    Synchronous entry point.
    Fetches spot rates for ccy1 and ccy2 only.
    Returns dict: { ccy: rate } where rate is as quoted on investing.com.
    """
    return asyncio.run(_fetch_spot_for_pair(ccy1, ccy2, settings))


if __name__ == "__main__":
    settings = load_currency_settings()

    # Test with EUR and GBP only
    print("Fetching EUR and GBP spot rates...\n")
    rates = fetch_spot_for_pair("EUR", "GBP", settings)

    print("\n--- Result ---")
    for ccy, rate in rates.items():
        if ccy == "USD":
            continue
        sense = settings[ccy]["sense"]
        label = f"{ccy}/USD" if sense == 1 else f"USD/{ccy}"
        print(f"  {label}: {rate}")