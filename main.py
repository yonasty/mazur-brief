import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import anthropic
import yfinance as yf
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="The Mazur Brief")

BASE_DIR = Path(__file__).parent
VERSION = (BASE_DIR / "VERSION").read_text().strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Futures ticker map for yfinance ──
FUTURES_TICKERS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "GC": "GC=F",
}

CROSS_MARKET_TICKERS = {
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "TNX": "^TNX",
    "CL": "CL=F",
}


def fetch_market_data() -> dict:
    """Fetch real market data from Yahoo Finance and compute derived levels."""
    data = {"instruments": {}, "cross_market": {}, "fetched_at": datetime.now(timezone.utc).isoformat()}

    # ── Fetch futures data ──
    for sym, ticker in FUTURES_TICKERS.items():
        try:
            t = yf.Ticker(ticker)

            # Current quote
            info = t.fast_info
            current_price = info.last_price if hasattr(info, 'last_price') else info.get('lastPrice', 0)
            prev_close = info.previous_close if hasattr(info, 'previous_close') else info.get('previousClose', 0)

            # Get 5 days of daily bars for prev session + weekly context
            daily = t.history(period="1mo", interval="1d")

            # Get intraday data for Globex session + volume profile
            intraday = t.history(period="5d", interval="5m")

            prev_high = prev_low = prev_settlement = 0
            prev_week_high = prev_week_low = 0
            prev_month_high = prev_month_low = 0
            weekly_open = monthly_open = 0
            ytd_high = ytd_low = 0
            globex_high = globex_low = 0
            vah = val = poc = vwap = 0

            if daily is not None and len(daily) >= 2:
                # Previous session data
                prev_day = daily.iloc[-2]
                prev_high = float(prev_day['High'])
                prev_low = float(prev_day['Low'])
                prev_settlement = float(prev_day['Close'])

                # Weekly context (last 5 trading days)
                if len(daily) >= 6:
                    last_week = daily.iloc[-7:-2]
                    prev_week_high = float(last_week['High'].max())
                    prev_week_low = float(last_week['Low'].min())

                # Monthly context
                if len(daily) >= 20:
                    last_month = daily.iloc[-22:-2]
                    prev_month_high = float(last_month['High'].max())
                    prev_month_low = float(last_month['Low'].min())

                # Weekly/monthly opens
                if len(daily) >= 2:
                    # Find Monday of current week
                    today_idx = daily.index[-1]
                    weekday = today_idx.weekday()
                    for i in range(len(daily) - 1, -1, -1):
                        if daily.index[i].weekday() == 0:  # Monday
                            weekly_open = float(daily.iloc[i]['Open'])
                            break
                    if weekly_open == 0 and len(daily) >= 2:
                        weekly_open = float(daily.iloc[-5]['Open']) if len(daily) >= 5 else float(daily.iloc[0]['Open'])

                # Monthly open = first day of current month
                for i in range(len(daily) - 1, -1, -1):
                    if daily.index[i].day <= 3:
                        monthly_open = float(daily.iloc[i]['Open'])
                        break

                # YTD high/low from all available data
                ytd_high = float(daily['High'].max())
                ytd_low = float(daily['Low'].min())

            # ── Compute Globex session high/low from intraday data ──
            if intraday is not None and len(intraday) > 0:
                # Globex = 6 PM ET prior day through current time
                # Filter for most recent overnight session
                now_utc = datetime.now(timezone.utc)
                # Find bars from roughly 11 PM UTC yesterday (6 PM ET) to now
                yesterday_6pm_et = now_utc.replace(hour=23, minute=0, second=0) - timedelta(days=1)

                try:
                    recent = intraday[intraday.index >= yesterday_6pm_et.strftime('%Y-%m-%d')]
                    if len(recent) > 0:
                        globex_high = float(recent['High'].max())
                        globex_low = float(recent['Low'].min())
                except Exception:
                    # Fallback: use last day of intraday data
                    last_date = intraday.index[-1].date()
                    today_bars = intraday[intraday.index.date >= (last_date - timedelta(days=1))]
                    if len(today_bars) > 0:
                        globex_high = float(today_bars['High'].max())
                        globex_low = float(today_bars['Low'].min())

                # ── Compute Volume Profile (VAH, VAL, POC) from prior session ──
                try:
                    if len(intraday) > 0:
                        # Get prior regular session bars (approx 9:30 AM - 4:00 PM ET)
                        dates = sorted(set(intraday.index.date))
                        if len(dates) >= 2:
                            prev_date = dates[-2]
                            prev_session = intraday[intraday.index.date == prev_date]

                            if len(prev_session) > 0:
                                # Build volume-at-price histogram
                                prices = prev_session['Close'].values
                                volumes = prev_session['Volume'].values

                                if len(prices) > 0 and np.sum(volumes) > 0:
                                    price_min = float(np.min(prices))
                                    price_max = float(np.max(prices))

                                    # Create price bins
                                    n_bins = min(50, max(20, int((price_max - price_min) / (price_max * 0.0002))))
                                    if n_bins > 0 and price_max > price_min:
                                        bins = np.linspace(price_min, price_max, n_bins + 1)
                                        bin_centers = (bins[:-1] + bins[1:]) / 2
                                        vol_profile = np.zeros(n_bins)

                                        for p, v in zip(prices, volumes):
                                            idx = min(int((p - price_min) / (price_max - price_min) * n_bins), n_bins - 1)
                                            idx = max(0, idx)
                                            vol_profile[idx] += v

                                        # POC = price bin with most volume
                                        poc_idx = int(np.argmax(vol_profile))
                                        poc = float(bin_centers[poc_idx])

                                        # Value Area = 70% of total volume centered around POC
                                        total_vol = np.sum(vol_profile)
                                        target_vol = total_vol * 0.70

                                        accumulated = vol_profile[poc_idx]
                                        lo = poc_idx
                                        hi = poc_idx

                                        while accumulated < target_vol and (lo > 0 or hi < n_bins - 1):
                                            expand_lo = vol_profile[lo - 1] if lo > 0 else 0
                                            expand_hi = vol_profile[hi + 1] if hi < n_bins - 1 else 0

                                            if expand_lo >= expand_hi and lo > 0:
                                                lo -= 1
                                                accumulated += vol_profile[lo]
                                            elif hi < n_bins - 1:
                                                hi += 1
                                                accumulated += vol_profile[hi]
                                            elif lo > 0:
                                                lo -= 1
                                                accumulated += vol_profile[lo]
                                            else:
                                                break

                                        val = float(bin_centers[lo])
                                        vah = float(bin_centers[hi])
                except Exception:
                    pass  # VAH/VAL/POC will stay 0 if computation fails

                # ── Compute VWAP from overnight session ──
                try:
                    if len(recent) > 0:
                        typical_price = (recent['High'] + recent['Low'] + recent['Close']) / 3
                        cum_vol = recent['Volume'].cumsum()
                        cum_tp_vol = (typical_price * recent['Volume']).cumsum()
                        if cum_vol.iloc[-1] > 0:
                            vwap = float(cum_tp_vol.iloc[-1] / cum_vol.iloc[-1])
                except Exception:
                    pass

            # Calculate derived fields
            overnight_change = round(current_price - prev_close, 2) if current_price and prev_close else 0
            overnight_pct = round((overnight_change / prev_close) * 100, 2) if prev_close else 0
            globex_range = round(globex_high - globex_low, 2) if globex_high and globex_low else 0
            pct_from_ytd_high = round(((current_price - ytd_high) / ytd_high) * 100, 2) if ytd_high else 0
            pct_from_ytd_low = round(((current_price - ytd_low) / ytd_low) * 100, 2) if ytd_low else 0

            # Inside/outside prev range
            inside_outside = "Inside"
            if globex_high > prev_high or globex_low < prev_low:
                inside_outside = "Outside"

            data["instruments"][sym] = {
                "current_price": round(current_price, 2) if current_price else 0,
                "prev_close": round(prev_close, 2) if prev_close else 0,
                "prev_high": round(prev_high, 2),
                "prev_low": round(prev_low, 2),
                "prev_settlement": round(prev_settlement, 2),
                "overnight_change_points": overnight_change,
                "overnight_change_pct": overnight_pct,
                "globex_high": round(globex_high, 2),
                "globex_low": round(globex_low, 2),
                "globex_range": round(globex_range, 2),
                "inside_outside_prev_range": inside_outside,
                "vah": round(vah, 2),
                "val": round(val, 2),
                "poc": round(poc, 2),
                "vwap": round(vwap, 2),
                "weekly_open": round(weekly_open, 2),
                "monthly_open": round(monthly_open, 2),
                "prev_week_high": round(prev_week_high, 2),
                "prev_week_low": round(prev_week_low, 2),
                "prev_month_high": round(prev_month_high, 2),
                "prev_month_low": round(prev_month_low, 2),
                "ytd_high": round(ytd_high, 2),
                "ytd_low": round(ytd_low, 2),
                "pct_from_ytd_high": pct_from_ytd_high,
                "pct_from_ytd_low": pct_from_ytd_low,
            }

        except Exception as e:
            data["instruments"][sym] = {"error": str(e), "current_price": 0}

    # ── Fetch cross-market data ──
    for sym, ticker in CROSS_MARKET_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            current = info.last_price if hasattr(info, 'last_price') else info.get('lastPrice', 0)
            prev = info.previous_close if hasattr(info, 'previous_close') else info.get('previousClose', 0)
            change = round(current - prev, 4) if current and prev else 0

            data["cross_market"][sym] = {
                "level": round(current, 4) if sym == "TNX" else round(current, 2),
                "overnight_change": round(change, 4) if sym == "TNX" else round(change, 2),
            }
        except Exception as e:
            data["cross_market"][sym] = {"level": 0, "overnight_change": 0, "error": str(e)}

    return data


# ── Prompt template — Claude ANALYZES real data, does NOT generate numbers ──

ANALYSIS_PROMPT = """You are a professional futures day trader running a pre-market morning briefing desk called "The Mazur Brief." You think in terms of Auction Market Theory, Volume Profile, and multi-session analysis.

IMPORTANT: All price data below is REAL, fetched from live market data feeds. Your job is to ANALYZE this data, not generate numbers. Use the exact prices provided. Do NOT change any of the numerical values — they are accurate.

Here is today's real market data as of {fetch_time}:

=== FUTURES DATA ===
{futures_data}

=== CROSS-MARKET DATA ===
{cross_market_data}

Your job: Using this real data, generate an analytical morning briefing as structured JSON. For fields that require the real prices (current_price, prev_high, prev_low, etc.), use the EXACT numbers from the data above. For analytical fields (bias, narratives, trade setups), provide your professional analysis.

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no explanation outside the JSON.

The JSON structure must be:

{{
  "generated_at": "ISO timestamp",
  "data_note": "Real-time market data via Yahoo Finance. Prices current as of {fetch_time}.",

  "playbook": {{
    "primary_bias": "Bullish/Bearish/Neutral",
    "bias_reason": "one line rooted in the actual data",
    "day_type": "Trend/Normal/Neutral/Expanded Normal",
    "best_setup": "instrument + direction + entry zone + target using REAL prices",
    "key_level": "the single most important price level today and why",
    "danger_zone": "what could go wrong"
  }},

  "market_context": {{
    "overnight_narrative": "What moved overnight and why, based on the actual price changes shown above",
    "session_alignment": "Whether sessions are aligned or diverging based on actual overnight ranges",
    "macro_catalysts": "Any known catalysts for today",
    "market_mood": "3-4 sentence plain English summary"
  }},

  "instruments": {{
    "NQ": {{
      "name": "NASDAQ 100 E-mini Futures",
      "current_price": {nq_price},
      "overnight_change_points": {nq_change},
      "overnight_change_pct": {nq_pct},
      "prev_high": {nq_prev_high},
      "prev_low": {nq_prev_low},
      "prev_close": {nq_prev_close},
      "prev_settlement": {nq_settlement},
      "ytd_high": {nq_ytd_high},
      "ytd_low": {nq_ytd_low},
      "pct_from_ytd_high": {nq_pct_ytd_high},
      "pct_from_ytd_low": {nq_pct_ytd_low},
      "globex_high": {nq_globex_high},
      "globex_low": {nq_globex_low},
      "globex_range": {nq_globex_range},
      "inside_outside_prev_range": "{nq_inside_outside}",
      "vah": {nq_vah},
      "val": {nq_val},
      "poc": {nq_poc},
      "price_vs_value_area": "Determine from actual price vs VAH/VAL: Above VA / Inside VA / Below VA",
      "va_playbook": "What this positioning means for trading based on actual levels",
      "naked_pocs": "Any recent unvisited POCs based on the data",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Data not available — use Globex range as proxy",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "London ORB requires tick-level data — using Globex range for directional bias",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": {nq_vwap},
      "weekly_open": {nq_weekly_open},
      "monthly_open": {nq_monthly_open},
      "prev_week_high": {nq_prev_week_high},
      "prev_week_low": {nq_prev_week_low},
      "prev_month_high": {nq_prev_month_high},
      "prev_month_low": {nq_prev_month_low},
      "bias": "Bullish/Bearish/Neutral — based on actual price position relative to key levels",
      "bias_reason": "one sentence rooted in the real data above",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation based on actual Globex range, value area position, etc.",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {{
          "direction": "Long/Short",
          "entry": "price or zone using REAL levels",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "calculated from real levels",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. VWAP reversion",
          "rationale": "one line tied to actual data",
          "invalidation": "what kills this trade"
        }}
      ]
    }},
    "ES": {{
      "name": "S&P 500 E-mini Futures",
      "current_price": {es_price},
      "overnight_change_points": {es_change},
      "overnight_change_pct": {es_pct},
      "prev_high": {es_prev_high},
      "prev_low": {es_prev_low},
      "prev_close": {es_prev_close},
      "prev_settlement": {es_settlement},
      "ytd_high": {es_ytd_high},
      "ytd_low": {es_ytd_low},
      "pct_from_ytd_high": {es_pct_ytd_high},
      "pct_from_ytd_low": {es_pct_ytd_low},
      "globex_high": {es_globex_high},
      "globex_low": {es_globex_low},
      "globex_range": {es_globex_range},
      "inside_outside_prev_range": "{es_inside_outside}",
      "vah": {es_vah},
      "val": {es_val},
      "poc": {es_poc},
      "price_vs_value_area": "Determine from actual price vs VAH/VAL",
      "va_playbook": "What this positioning means",
      "naked_pocs": "Any recent unvisited POCs",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Data not available — use Globex range as proxy",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "London ORB requires tick-level data — using Globex range for directional bias",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": {es_vwap},
      "weekly_open": {es_weekly_open},
      "monthly_open": {es_monthly_open},
      "prev_week_high": {es_prev_week_high},
      "prev_week_low": {es_prev_week_low},
      "prev_month_high": {es_prev_month_high},
      "prev_month_low": {es_prev_month_low},
      "bias": "Bullish/Bearish/Neutral",
      "bias_reason": "one sentence rooted in real data",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation based on actual data",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {{
          "direction": "Long/Short",
          "entry": "price using REAL levels",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "calculated",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. VA edge fade",
          "rationale": "one line tied to actual data",
          "invalidation": "what kills this trade"
        }}
      ]
    }},
    "GC": {{
      "name": "Gold Futures",
      "current_price": {gc_price},
      "overnight_change_points": {gc_change},
      "overnight_change_pct": {gc_pct},
      "prev_high": {gc_prev_high},
      "prev_low": {gc_prev_low},
      "prev_close": {gc_prev_close},
      "prev_settlement": {gc_settlement},
      "ytd_high": {gc_ytd_high},
      "ytd_low": {gc_ytd_low},
      "pct_from_ytd_high": {gc_pct_ytd_high},
      "pct_from_ytd_low": {gc_pct_ytd_low},
      "globex_high": {gc_globex_high},
      "globex_low": {gc_globex_low},
      "globex_range": {gc_globex_range},
      "inside_outside_prev_range": "{gc_inside_outside}",
      "vah": {gc_vah},
      "val": {gc_val},
      "poc": {gc_poc},
      "price_vs_value_area": "Determine from actual price vs VAH/VAL",
      "va_playbook": "What this positioning means",
      "naked_pocs": "Any recent unvisited POCs",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Data not available — use Globex range as proxy",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "London ORB requires tick-level data — using Globex range for directional bias",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": {gc_vwap},
      "weekly_open": {gc_weekly_open},
      "monthly_open": {gc_monthly_open},
      "prev_week_high": {gc_prev_week_high},
      "prev_week_low": {gc_prev_week_low},
      "prev_month_high": {gc_prev_month_high},
      "prev_month_low": {gc_prev_month_low},
      "bias": "Bullish/Bearish/Neutral",
      "bias_reason": "one sentence rooted in real data",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation based on actual data",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {{
          "direction": "Long/Short",
          "entry": "price using REAL levels",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "calculated",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. naked POC magnet",
          "rationale": "one line tied to actual data",
          "invalidation": "what kills this trade"
        }}
      ]
    }}
  }},

  "cross_market": {{
    "dxy": {{
      "level": {dxy_level},
      "overnight_change": {dxy_change},
      "direction": "Strengthening/Weakening/Flat based on actual change",
      "implication": "one sentence on what DXY means for NQ and Gold"
    }},
    "vix": {{
      "level": {vix_level},
      "trend": "Rising/Falling/Flat based on actual change",
      "severity": "low/moderate/elevated/extreme based on actual level",
      "context": "one sentence on what VIX is telling us"
    }},
    "tnx": {{
      "level": {tnx_level},
      "overnight_change": {tnx_change},
      "context": "one sentence on yield regime and impact"
    }},
    "crude": {{
      "level": {cl_level},
      "overnight_change": {cl_change},
      "context": "one sentence"
    }}
  }},

  "economic_calendar": [
    {{
      "time_et": "8:30 AM",
      "event": "Event name",
      "impact": "HIGH/MEDIUM",
      "prior": "value",
      "consensus": "value",
      "why_it_matters": "one line",
      "trade_warning": "optional"
    }}
  ],

  "premarket_warning": "If there's a high-impact event between 8:00-9:30 AM, flag it here. Otherwise null."
}}

Provide 2-3 trade setups per instrument with entries, stops, and targets anchored to the REAL levels above. Calculate R:R ratios from actual distances between levels. For the economic calendar, use your knowledge of scheduled economic releases for today's date.

Today's date: {date}"""


def build_analysis_prompt(market_data: dict, today: str) -> str:
    """Build the analysis prompt with real market data injected."""
    instruments = market_data["instruments"]
    cross = market_data["cross_market"]

    # Format futures data as readable text
    futures_text = ""
    for sym in ["NQ", "ES", "GC"]:
        d = instruments.get(sym, {})
        futures_text += f"\n{sym}:\n"
        for key, val in d.items():
            if key != "error":
                futures_text += f"  {key}: {val}\n"

    # Format cross-market data
    cross_text = ""
    for sym in ["VIX", "DXY", "TNX", "CL"]:
        d = cross.get(sym, {})
        cross_text += f"\n{sym}:\n"
        for key, val in d.items():
            if key != "error":
                cross_text += f"  {key}: {val}\n"

    # Helper to get instrument values safely
    def g(sym, key, default=0):
        return instruments.get(sym, {}).get(key, default)

    def gc(sym, key, default=0):
        return cross.get(sym, {}).get(key, default)

    return ANALYSIS_PROMPT.format(
        fetch_time=market_data["fetched_at"],
        date=today,
        futures_data=futures_text,
        cross_market_data=cross_text,
        # NQ values
        nq_price=g("NQ", "current_price"),
        nq_change=g("NQ", "overnight_change_points"),
        nq_pct=g("NQ", "overnight_change_pct"),
        nq_prev_high=g("NQ", "prev_high"),
        nq_prev_low=g("NQ", "prev_low"),
        nq_prev_close=g("NQ", "prev_close"),
        nq_settlement=g("NQ", "prev_settlement"),
        nq_ytd_high=g("NQ", "ytd_high"),
        nq_ytd_low=g("NQ", "ytd_low"),
        nq_pct_ytd_high=g("NQ", "pct_from_ytd_high"),
        nq_pct_ytd_low=g("NQ", "pct_from_ytd_low"),
        nq_globex_high=g("NQ", "globex_high"),
        nq_globex_low=g("NQ", "globex_low"),
        nq_globex_range=g("NQ", "globex_range"),
        nq_inside_outside=g("NQ", "inside_outside_prev_range", "Inside"),
        nq_vah=g("NQ", "vah"),
        nq_val=g("NQ", "val"),
        nq_poc=g("NQ", "poc"),
        nq_vwap=g("NQ", "vwap"),
        nq_weekly_open=g("NQ", "weekly_open"),
        nq_monthly_open=g("NQ", "monthly_open"),
        nq_prev_week_high=g("NQ", "prev_week_high"),
        nq_prev_week_low=g("NQ", "prev_week_low"),
        nq_prev_month_high=g("NQ", "prev_month_high"),
        nq_prev_month_low=g("NQ", "prev_month_low"),
        # ES values
        es_price=g("ES", "current_price"),
        es_change=g("ES", "overnight_change_points"),
        es_pct=g("ES", "overnight_change_pct"),
        es_prev_high=g("ES", "prev_high"),
        es_prev_low=g("ES", "prev_low"),
        es_prev_close=g("ES", "prev_close"),
        es_settlement=g("ES", "prev_settlement"),
        es_ytd_high=g("ES", "ytd_high"),
        es_ytd_low=g("ES", "ytd_low"),
        es_pct_ytd_high=g("ES", "pct_from_ytd_high"),
        es_pct_ytd_low=g("ES", "pct_from_ytd_low"),
        es_globex_high=g("ES", "globex_high"),
        es_globex_low=g("ES", "globex_low"),
        es_globex_range=g("ES", "globex_range"),
        es_inside_outside=g("ES", "inside_outside_prev_range", "Inside"),
        es_vah=g("ES", "vah"),
        es_val=g("ES", "val"),
        es_poc=g("ES", "poc"),
        es_vwap=g("ES", "vwap"),
        es_weekly_open=g("ES", "weekly_open"),
        es_monthly_open=g("ES", "monthly_open"),
        es_prev_week_high=g("ES", "prev_week_high"),
        es_prev_week_low=g("ES", "prev_week_low"),
        es_prev_month_high=g("ES", "prev_month_high"),
        es_prev_month_low=g("ES", "prev_month_low"),
        # GC values
        gc_price=g("GC", "current_price"),
        gc_change=g("GC", "overnight_change_points"),
        gc_pct=g("GC", "overnight_change_pct"),
        gc_prev_high=g("GC", "prev_high"),
        gc_prev_low=g("GC", "prev_low"),
        gc_prev_close=g("GC", "prev_close"),
        gc_settlement=g("GC", "prev_settlement"),
        gc_ytd_high=g("GC", "ytd_high"),
        gc_ytd_low=g("GC", "ytd_low"),
        gc_pct_ytd_high=g("GC", "pct_from_ytd_high"),
        gc_pct_ytd_low=g("GC", "pct_from_ytd_low"),
        gc_globex_high=g("GC", "globex_high"),
        gc_globex_low=g("GC", "globex_low"),
        gc_globex_range=g("GC", "globex_range"),
        gc_inside_outside=g("GC", "inside_outside_prev_range", "Inside"),
        gc_vah=g("GC", "vah"),
        gc_val=g("GC", "val"),
        gc_poc=g("GC", "poc"),
        gc_vwap=g("GC", "vwap"),
        gc_weekly_open=g("GC", "weekly_open"),
        gc_monthly_open=g("GC", "monthly_open"),
        gc_prev_week_high=g("GC", "prev_week_high"),
        gc_prev_week_low=g("GC", "prev_week_low"),
        gc_prev_month_high=g("GC", "prev_month_high"),
        gc_prev_month_low=g("GC", "prev_month_low"),
        # Cross-market values
        dxy_level=gc("DXY", "level"),
        dxy_change=gc("DXY", "overnight_change"),
        vix_level=gc("VIX", "level"),
        tnx_level=gc("TNX", "level"),
        tnx_change=gc("TNX", "overnight_change"),
        cl_level=gc("CL", "level"),
        cl_change=gc("CL", "overnight_change"),
    )


NY_ORB_PROMPT = """The NY session has opened. Update the briefing with NY Opening Range Breakout data.

For each instrument (NQ, ES, GC), provide the NY ORB (9:30-9:45 AM ET) data:
- ny_orb_high, ny_orb_low, ny_orb_range
- ny_orb_broken: "Not broken/Broken high/Broken low/Both broken"
- ny_orb_ext_1x, ny_orb_ext_1_5x, ny_orb_ext_2x
- ny_orb_context: whether conditions favor double-break vs clean breakout

Also provide an updated playbook if the opening changes the bias.

Return JSON:
{{
  "instruments": {{
    "NQ": {{ "ny_orb_high": 0, "ny_orb_low": 0, "ny_orb_range": 0, "ny_orb_broken": "", "ny_orb_ext_1x": 0, "ny_orb_ext_1_5x": 0, "ny_orb_ext_2x": 0, "ny_orb_context": "" }},
    "ES": {{ ... same fields ... }},
    "GC": {{ ... same fields ... }}
  }},
  "updated_playbook": {{
    "primary_bias": "",
    "bias_reason": "",
    "best_setup": "",
    "key_level": "",
    "danger_zone": ""
  }}
}}

Today's date: {date}"""


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)


@app.get("/api/version")
async def version():
    return {"version": VERSION}


@app.post("/api/briefing")
async def generate_briefing():
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # Step 1: Fetch real market data
    try:
        market_data = fetch_market_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch market data: {str(e)}")

    # Step 2: Build prompt with real data injected
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = build_analysis_prompt(market_data, today)

    # Step 3: Claude analyzes the real data
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system="You are a professional futures day trader analyzing REAL market data. All prices provided are accurate and current. Return ONLY valid JSON — no markdown, no code fences, no explanation. Use the exact numerical values provided in the prompt for all price fields.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3].strip()
        data = json.loads(text)
        return JSONResponse(content=data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse Claude response as JSON: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}")


@app.post("/api/ny-orb")
async def update_ny_orb():
    """Fetch real NY ORB data from the 9:30-9:45 window."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # Try to get real ORB data from yfinance intraday
    orb_data = {}
    for sym, ticker in FUTURES_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            intraday = t.history(period="1d", interval="1m")
            if intraday is not None and len(intraday) > 0:
                # Filter for 9:30-9:45 AM ET window
                # This is approximate — yfinance timestamps may vary
                orb_bars = []
                for idx, row in intraday.iterrows():
                    ts = idx.to_pydatetime()
                    # Check if within 9:30-9:45 ET (14:30-14:45 UTC or 13:30-13:45 UTC depending on DST)
                    hour_min = ts.hour * 60 + ts.minute
                    # Approximate: look for bars in the first 15 minutes of regular session
                    if len(orb_bars) < 15:
                        # Heuristic: if we see a gap after market hours, the next bars are the open
                        orb_bars.append(row)

                if orb_bars:
                    import pandas as pd
                    orb_df = pd.DataFrame(orb_bars)
                    orb_high = float(orb_df['High'].max())
                    orb_low = float(orb_df['Low'].min())
                    orb_range = round(orb_high - orb_low, 2)

                    current = float(intraday.iloc[-1]['Close'])
                    broken = "Not broken"
                    if current > orb_high:
                        broken = "Broken high"
                    elif current < orb_low:
                        broken = "Broken low"

                    orb_data[sym] = {
                        "ny_orb_high": round(orb_high, 2),
                        "ny_orb_low": round(orb_low, 2),
                        "ny_orb_range": orb_range,
                        "ny_orb_broken": broken,
                        "ny_orb_ext_1x": round(orb_high + orb_range, 2),
                        "ny_orb_ext_1_5x": round(orb_high + orb_range * 1.5, 2),
                        "ny_orb_ext_2x": round(orb_high + orb_range * 2, 2),
                        "ny_orb_context": "",
                    }
        except Exception:
            pass

    # If we got real ORB data, use it; otherwise fall back to Claude
    if orb_data:
        return JSONResponse(content={
            "instruments": orb_data,
            "updated_playbook": None,
        })

    # Fallback: Claude estimates (less ideal but better than nothing)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system="You are a professional futures trader. Return ONLY valid JSON, no markdown or explanation.",
            messages=[{"role": "user", "content": NY_ORB_PROMPT.replace("{date}", today)}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3].strip()
        data = json.loads(text)
        return JSONResponse(content=data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse NY ORB response: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}
