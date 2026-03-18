import numpy as np
import pandas as pd
from datetime import date
from scipy.interpolate import CubicSpline
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from calculations.business_calendar import get_all_tenor_dates, get_spot_date
from data.fetch_forwards import load_currency_settings, fetch_forward_curve


# ---------------------------------------------------------------------------
# Tenor to days conversion (from spot date)
# Used to build the interpolation x-axis
# ---------------------------------------------------------------------------

def dates_to_days(base_date: date, dates: list) -> np.ndarray:
    """Convert a list of dates to number of days from base_date."""
    return np.array([(d - base_date).days for d in dates])


# ---------------------------------------------------------------------------
# Build forward price spine from raw fetched curve
# ---------------------------------------------------------------------------

def build_forward_spine(raw_df: pd.DataFrame, spot_rate: float,
                        spot_date: date, divider: int) -> tuple:
    """
    Convert raw swap points DataFrame into a cubic spline of forward prices.

    raw_df: DataFrame with columns Tenor, Bid, Ask (swap points in pips)
    spot_rate: mid spot rate as quoted on investing.com
    spot_date: the spot value date
    divider: pip divider for this currency

    Returns:
        cs_bid: CubicSpline object for bid forward prices
        cs_ask: CubicSpline object for ask forward prices
        spine_dates: list of dates used to build the spline
    """
    from calculations.business_calendar import get_tenor_date

    # Map tenor labels to days from spot
    # We exclude TN from the spline — it is pre-spot
    spine_rows = []
    for _, row in raw_df.iterrows():
        tenor = row["Tenor"]
        if tenor == "TN":
            continue  # Excluded from interpolation spine
        try:
            # Get the value date for this tenor
            # We use USD/USD as placeholder calendars since we are working
            # on a single leg curve — the exact calendar adjustment is applied
            # at the crossing stage
            value_date = get_tenor_date(spot_date, tenor, "USD", "USD")
            days = (value_date - spot_date).days
            bid_fwd = spot_rate + row["Bid"] / divider
            ask_fwd = spot_rate + row["Ask"] / divider
            spine_rows.append({
                "days": days,
                "bid_fwd": bid_fwd,
                "ask_fwd": ask_fwd,
                "date": value_date
            })
        except Exception:
            continue

    if len(spine_rows) < 3:
        raise ValueError("Insufficient data points to build spline")

    spine_df = pd.DataFrame(spine_rows).sort_values("days").drop_duplicates("days")

    # Anchor at spot: day 0, forward price = spot mid, zero spread
    spot_row = pd.DataFrame([{
        "days": 0,
        "bid_fwd": spot_rate,
        "ask_fwd": spot_rate,
        "date": spot_date
    }])
    spine_df = pd.concat([spot_row, spine_df]).sort_values("days").reset_index(drop=True)

    x = spine_df["days"].values
    y_bid = spine_df["bid_fwd"].values
    y_ask = spine_df["ask_fwd"].values

    cs_bid = CubicSpline(x, y_bid)
    cs_ask = CubicSpline(x, y_ask)

    return cs_bid, cs_ask, spine_df["date"].tolist()


# ---------------------------------------------------------------------------
# Interpolate a single leg curve to exact target dates
# ---------------------------------------------------------------------------

def interpolate_leg(cs_bid: CubicSpline, cs_ask: CubicSpline,
                    spot_date: date, target_dates: list) -> pd.DataFrame:
    """
    Evaluate the cubic spline at each target date.
    Returns DataFrame with columns: date, bid_fwd, ask_fwd
    """
    rows = []
    for d in target_dates:
        days = (d - spot_date).days
        bid = float(cs_bid(days))
        ask = float(cs_ask(days))
        rows.append({"date": d, "bid_fwd": bid, "ask_fwd": ask})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cross two USD legs to get the resulting pair
# ---------------------------------------------------------------------------

def cross_legs(leg1_df: pd.DataFrame, leg2_df: pd.DataFrame,
               sense1: int, sense2: int) -> pd.DataFrame:
    """
    Cross two forward price DataFrames to get the resulting pair.

    Formula: CCY1/CCY2 = (leg1 ^ sense1) / (leg2 ^ sense2)

    For bid/ask crossing:
        crossed_bid = bid of numerator / ask of denominator
        crossed_ask = ask of numerator / bid of denominator

    Both DataFrames must have identical date columns.
    """
    assert len(leg1_df) == len(leg2_df), "Leg DataFrames must have same length"

    rows = []
    for i in range(len(leg1_df)):
        d = leg1_df.iloc[i]["date"]

        l1_bid = leg1_df.iloc[i]["bid_fwd"]
        l1_ask = leg1_df.iloc[i]["ask_fwd"]
        l2_bid = leg2_df.iloc[i]["bid_fwd"]
        l2_ask = leg2_df.iloc[i]["ask_fwd"]

        # Apply sense as exponent to get CCY/USD equivalent
        # sense=1:  rate is already CCY/USD, use as-is
        # sense=-1: rate is USD/CCY, so CCY/USD = 1/rate
        #           bid CCY/USD = 1 / ask USD/CCY
        #           ask CCY/USD = 1 / bid USD/CCY

        if sense1 == 1:
            num_bid = l1_bid
            num_ask = l1_ask
        else:
            num_bid = 1.0 / l1_ask
            num_ask = 1.0 / l1_bid

        if sense2 == 1:
            den_bid = l2_bid
            den_ask = l2_ask
        else:
            den_bid = 1.0 / l2_ask
            den_ask = 1.0 / l2_bid

        # CCY1/CCY2 = CCY1/USD / CCY2/USD
        crossed_bid = num_bid / den_ask
        crossed_ask = num_ask / den_bid

        rows.append({
            "date": d,
            "bid_fwd": crossed_bid,
            "ask_fwd": crossed_ask
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Handle TN row separately
# ---------------------------------------------------------------------------

def compute_tn_row(tn_date: date, spot_mid: float,
                   tn_bid_pts: float, tn_ask_pts: float,
                   divider: int) -> dict:
    """
    Compute TN forward prices applying the bid/ask inversion rule.
    FX Forward Bid (TN) = Spot Mid - Swap Points Ask / divider
    FX Forward Ask (TN) = Spot Mid - Swap Points Bid / divider
    """
    fwd_bid = spot_mid - tn_ask_pts / divider
    fwd_ask = spot_mid - tn_bid_pts / divider
    return {
        "date": tn_date,
        "bid_fwd": fwd_bid,
        "ask_fwd": fwd_ask
    }


# ---------------------------------------------------------------------------
# Master function: build complete output table for a currency pair
# ---------------------------------------------------------------------------

def build_output_table(ccy1: str, ccy2: str,
                       spot_rates: dict, settings: dict,
                       today: date = None) -> pd.DataFrame:
    """
    Build the complete forward curve output table for CCY1/CCY2.

    Returns DataFrame with columns:
        Tenor, Date, Spot_Mid, SwapBid, SwapAsk, FwdBid, FwdAsk
    """
    if today is None:
        today = date.today()

    # --- Step 1: Get all tenor dates for the output table ---
    tenor_dates = get_all_tenor_dates(today, ccy1, ccy2, settings)
    spot_date = tenor_dates["SPOT"]

    # --- Step 2: Get spot rates ---
    # Spot rates are stored as quoted on investing.com
    # Apply sense exponent to get CCY/USD equivalent

    def to_ccy_usd(ccy):
        if ccy == "USD":
            return 1.0
        rate = spot_rates[ccy]
        sense = settings[ccy]["sense"]
        if sense == 1:
            return rate        # already CCY/USD
        else:
            return 1.0 / rate  # invert USD/CCY to get CCY/USD

    spot1_ccy_usd = to_ccy_usd(ccy1)
    spot2_ccy_usd = to_ccy_usd(ccy2)
    spot_mid = spot1_ccy_usd / spot2_ccy_usd

    # --- Step 3: Fetch raw forward curves ---
    # For USD leg, create a flat curve
    def get_raw_curve(ccy):
        if ccy == "USD":
            return None
        return fetch_forward_curve(ccy, settings)

    raw1 = get_raw_curve(ccy1)
    raw2 = get_raw_curve(ccy2)

    # --- Step 4: Get spot dates for each individual leg ---
    from calculations.business_calendar import get_spot_date as get_sd
    spot1_date = get_sd(today, ccy1, "USD", settings)
    spot2_date = get_sd(today, ccy2, "USD", settings)

    # --- Step 5: Build splines for each leg ---
    # Target dates: all output tenor dates except TN and SPOT
    target_dates = [
        d for t, d in tenor_dates.items()
        if t not in ("TN", "SPOT")
    ]

    def build_leg_interpolated(ccy, raw_df, spot_rate_ccy_usd, leg_spot_date):
        if ccy == "USD":
            # Flat curve: forward price = 1.0 everywhere
            rows = [{"date": d, "bid_fwd": 1.0, "ask_fwd": 1.0}
                    for d in target_dates]
            return pd.DataFrame(rows)

        divider = settings[ccy]["divider"]
        cs_bid, cs_ask, _ = build_forward_spine(
            raw_df, spot_rate_ccy_usd, leg_spot_date, divider
        )
        return interpolate_leg(cs_bid, cs_ask, leg_spot_date, target_dates)

    leg1_df = build_leg_interpolated(ccy1, raw1, spot1_ccy_usd, spot1_date)
    leg2_df = build_leg_interpolated(ccy2, raw2, spot2_ccy_usd, spot2_date)

    # --- Step 6: Cross the two legs ---
    sense1 = settings[ccy1]["sense"]
    sense2 = settings[ccy2]["sense"]
    crossed_df = cross_legs(leg1_df, leg2_df, sense1, sense2)

    # --- Step 7: Compute swap points for output (crossed fwd - spot mid) ---
    # Use the divider of ccy1 for display purposes
    # (convention: cross swap points expressed in ccy2 pips)
    # We will derive swap points by difference: fwd - spot_mid
    # No divider needed here since we are working in price terms

    # --- Step 8: Handle TN row ---
    tn_date = tenor_dates["TN"]

    def get_tn_pts(ccy, raw_df):
        if ccy == "USD" or raw_df is None:
            return 0.0, 0.0
        tn_rows = raw_df[raw_df["Tenor"] == "TN"]
        if tn_rows.empty:
            return 0.0, 0.0
        return float(tn_rows.iloc[0]["Bid"]), float(tn_rows.iloc[0]["Ask"])

    # For TN we need the crossed spot mid (already computed)
    # and the TN swap points for each leg, then cross them
    tn1_bid, tn1_ask = get_tn_pts(ccy1, raw1)
    tn2_bid, tn2_ask = get_tn_pts(ccy2, raw2)

    div1 = settings[ccy1]["divider"] if ccy1 != "USD" else 10000
    div2 = settings[ccy2]["divider"] if ccy2 != "USD" else 10000

    tn1_fwd_bid = spot1_ccy_usd - tn1_ask / div1
    tn1_fwd_ask = spot1_ccy_usd - tn1_bid / div1
    tn2_fwd_bid = spot2_ccy_usd - tn2_ask / div2
    tn2_fwd_ask = spot2_ccy_usd - tn2_bid / div2

    # Cross TN forwards
    if sense1 == 1:
        tn_num_bid, tn_num_ask = tn1_fwd_bid, tn1_fwd_ask
    else:
        tn_num_bid = 1.0 / tn1_fwd_ask
        tn_num_ask = 1.0 / tn1_fwd_bid

    if sense2 == 1:
        tn_den_bid, tn_den_ask = tn2_fwd_bid, tn2_fwd_ask
    else:
        tn_den_bid = 1.0 / tn2_fwd_ask
        tn_den_ask = 1.0 / tn2_fwd_bid

    tn_crossed_bid = tn_num_bid / tn_den_ask
    tn_crossed_ask = tn_num_ask / tn_den_bid

    # --- Step 9: Assemble final output table ---
    OUTPUT_TENORS = [
        "TN", "SPOT", "SN", "1W", "2W", "3W",
        "1M", "2M", "3M", "4M", "5M", "6M",
        "7M", "8M", "9M", "10M", "11M", "1Y",
        "15M", "18M", "21M", "2Y", "3Y"
    ]

    rows = []
    crossed_idx = 0

    for tenor in OUTPUT_TENORS:
        d = tenor_dates[tenor]

        if tenor == "TN":
            fwd_bid = tn_crossed_bid
            fwd_ask = tn_crossed_ask
            swap_bid = spot_mid - fwd_ask  # inverted
            swap_ask = spot_mid - fwd_bid  # inverted

        elif tenor == "SPOT":
            fwd_bid = spot_mid
            fwd_ask = spot_mid
            swap_bid = 0.0
            swap_ask = 0.0

        else:
            fwd_bid = crossed_df.iloc[crossed_idx]["bid_fwd"]
            fwd_ask = crossed_df.iloc[crossed_idx]["ask_fwd"]
            swap_bid = fwd_bid - spot_mid
            swap_ask = fwd_ask - spot_mid
            crossed_idx += 1

        rows.append({
            "Tenor": tenor,
            "Date": d,
            "Spot_Mid": round(spot_mid, 6),
            "Swap_Bid": round(swap_bid, 6),
            "Swap_Ask": round(swap_ask, 6),
            "Fwd_Bid": round(fwd_bid, 6),
            "Fwd_Ask": round(fwd_ask, 6)
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    from data.fetch_forwards import load_currency_settings
    from data.fetch_spot import fetch_spot_for_pair

    settings = load_currency_settings()
    today = date.today()

    ccy1, ccy2 = "EUR", "GBP"
    print(f"Fetching spot rates for {ccy1} and {ccy2}...")
    spot_rates = fetch_spot_for_pair(ccy1, ccy2, settings)

    print(f"\nBuilding {ccy1}/{ccy2} forward curve...\n")
    df = build_output_table(ccy1, ccy2, spot_rates, settings, today)
    print(df.to_string(index=False))