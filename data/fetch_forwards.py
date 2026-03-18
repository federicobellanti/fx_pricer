import requests
import pandas as pd
import io
import json
from bs4 import BeautifulSoup

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


def parse_tenor(tenor_str):
    """
    Parse tenor string from investing.com format.
    Examples: 'EURUSD TN FWD' -> 'TN'
              'EURUSD SW FWD' -> 'SW'
              'EURUSD 3M FWD' -> '3M'
    Returns None if tenor is ON (excluded) or beyond 3Y.
    """
    # Tenor string is the middle token between pair and FWD
    parts = tenor_str.strip().split()
    if len(parts) < 3:
        return None
    
    tenor = parts[1].upper()
    
    # Exclude ON entirely
    if tenor == "ON":
        return None
    
    # Treat SW as 1W
    if tenor == "SW":
        tenor = "1W"
    
    # Exclude tenors beyond 3Y
    beyond_3y = ["4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "30Y"]
    if tenor in beyond_3y:
        return None
    
    return tenor


def fetch_forward_curve(currency, settings):
    """
    Fetch forward curve for a given currency vs USD from investing.com.
    Returns a DataFrame with columns: Tenor, Bid, Ask
    Returns None if fetch fails.
    """
    if currency == "USD":
        return None  # USD handled separately as flat curve
    
    row_id = settings[currency]["row"]
    if row_id is None:
        return None
    
    url = f"https://www.investing.com/center_forward_rates.php?currencies={row_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.investing.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching {currency}: {e}")
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    
    if table is None:
        print(f"No table found for {currency}")
        return None
    
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        
        name_cell = cells[1].get_text(strip=True)
        tenor = parse_tenor(name_cell)
        
        if tenor is None:
            continue
        
        try:
            bid = float(cells[2].get_text(strip=True).replace(",", ""))
            ask = float(cells[3].get_text(strip=True).replace(",", ""))
        except ValueError:
            continue
        
        rows.append({
            "Tenor": tenor,
            "Bid": bid,
            "Ask": ask
        })
    
    if not rows:
        print(f"No data rows parsed for {currency}")
        return None
    
    df = pd.DataFrame(rows)
    return df


def fetch_all_curves(currencies, settings):
    """
    Fetch forward curves for a list of currencies.
    Returns a dictionary: { currency_code: DataFrame }
    """
    curves = {}
    for ccy in currencies:
        if ccy == "USD":
            continue
        print(f"Fetching {ccy}...")
        df = fetch_forward_curve(ccy, settings)
        if df is not None:
            curves[ccy] = df
        else:
            print(f"Warning: could not fetch curve for {ccy}")
    return curves


if __name__ == "__main__":
    # Quick test — fetch EUR and GBP curves and print them
    settings = load_currency_settings()
    for ccy in ["EUR", "GBP"]:
        print(f"\n--- {ccy}/USD Forward Curve ---")
        df = fetch_forward_curve(ccy, settings)
        if df is not None:
            print(df.to_string(index=False))
        else:
            print("Failed to fetch")