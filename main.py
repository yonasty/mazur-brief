import os
import json
from pathlib import Path
from datetime import datetime, timezone

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="The Mazur Brief")

BASE_DIR = Path(__file__).parent
VERSION = (BASE_DIR / "VERSION").read_text().strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are a professional futures day trader running a pre-market morning briefing desk called "The Mazur Brief." You think in terms of Auction Market Theory, Volume Profile, and multi-session analysis. You produce structured intelligence for NQ (Nasdaq futures), ES (S&P futures), and GC (Gold futures).

Your job: generate a complete morning briefing as structured JSON. Every number must be your best estimate based on your training data and current market knowledge. If you don't have real-time data, use your most recent knowledge and clearly note the data freshness.

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no explanation outside the JSON.

The JSON structure must be:

{
  "generated_at": "ISO timestamp",
  "data_note": "Brief note about data freshness/limitations",

  "playbook": {
    "primary_bias": "Bullish/Bearish/Neutral",
    "bias_reason": "one line",
    "day_type": "Trend/Normal/Neutral/Expanded Normal",
    "best_setup": "instrument + direction + entry zone + target",
    "key_level": "the single most important price level today and why",
    "danger_zone": "what could go wrong"
  },

  "market_context": {
    "overnight_narrative": "What moved in Asia, London, and why",
    "session_alignment": "Whether Asia/London/NY are aligned or diverging and implications",
    "macro_catalysts": "Any overnight catalysts",
    "market_mood": "3-4 sentence plain English summary"
  },

  "instruments": {
    "NQ": {
      "name": "Nasdaq 100 Futures",
      "current_price": 0,
      "overnight_change_points": 0,
      "overnight_change_pct": 0,
      "prev_high": 0,
      "prev_low": 0,
      "prev_close": 0,
      "prev_settlement": 0,
      "ytd_high": 0,
      "ytd_low": 0,
      "pct_from_ytd_high": 0,
      "pct_from_ytd_low": 0,
      "globex_high": 0,
      "globex_low": 0,
      "globex_range": 0,
      "inside_outside_prev_range": "Inside/Outside",
      "vah": 0,
      "val": 0,
      "poc": 0,
      "price_vs_value_area": "Above VA/Inside VA/Below VA",
      "va_playbook": "What this positioning means for trading",
      "naked_pocs": "Any recent unvisited POCs",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Not broken/Broken high/Broken low/Both broken",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "Whether conditions favor double-break vs clean breakout",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": 0,
      "weekly_open": 0,
      "monthly_open": 0,
      "prev_week_high": 0,
      "prev_week_low": 0,
      "prev_month_high": 0,
      "prev_month_low": 0,
      "bias": "Bullish/Bearish/Neutral",
      "bias_reason": "one sentence rooted in data",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation of expected day type behavior",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {
          "direction": "Long/Short",
          "entry": "price or zone",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "e.g. 2.5:1",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. VWAP reversion",
          "rationale": "one line tied to data",
          "invalidation": "what kills this trade"
        }
      ]
    },
    "ES": {
      "name": "S&P 500 Futures",
      "current_price": 0,
      "overnight_change_points": 0,
      "overnight_change_pct": 0,
      "prev_high": 0,
      "prev_low": 0,
      "prev_close": 0,
      "prev_settlement": 0,
      "ytd_high": 0,
      "ytd_low": 0,
      "pct_from_ytd_high": 0,
      "pct_from_ytd_low": 0,
      "globex_high": 0,
      "globex_low": 0,
      "globex_range": 0,
      "inside_outside_prev_range": "Inside/Outside",
      "vah": 0,
      "val": 0,
      "poc": 0,
      "price_vs_value_area": "Above VA/Inside VA/Below VA",
      "va_playbook": "What this positioning means for trading",
      "naked_pocs": "Any recent unvisited POCs",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Not broken/Broken high/Broken low/Both broken",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "Whether conditions favor double-break vs clean breakout",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": 0,
      "weekly_open": 0,
      "monthly_open": 0,
      "prev_week_high": 0,
      "prev_week_low": 0,
      "prev_month_high": 0,
      "prev_month_low": 0,
      "bias": "Bullish/Bearish/Neutral",
      "bias_reason": "one sentence rooted in data",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation of expected day type behavior",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {
          "direction": "Long/Short",
          "entry": "price or zone",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "e.g. 2.5:1",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. VWAP reversion",
          "rationale": "one line tied to data",
          "invalidation": "what kills this trade"
        }
      ]
    },
    "GC": {
      "name": "Gold Futures",
      "current_price": 0,
      "overnight_change_points": 0,
      "overnight_change_pct": 0,
      "prev_high": 0,
      "prev_low": 0,
      "prev_close": 0,
      "prev_settlement": 0,
      "ytd_high": 0,
      "ytd_low": 0,
      "pct_from_ytd_high": 0,
      "pct_from_ytd_low": 0,
      "globex_high": 0,
      "globex_low": 0,
      "globex_range": 0,
      "inside_outside_prev_range": "Inside/Outside",
      "vah": 0,
      "val": 0,
      "poc": 0,
      "price_vs_value_area": "Above VA/Inside VA/Below VA",
      "va_playbook": "What this positioning means for trading",
      "naked_pocs": "Any recent unvisited POCs",
      "london_orb_high": 0,
      "london_orb_low": 0,
      "london_orb_range": 0,
      "london_orb_broken": "Not broken/Broken high/Broken low/Both broken",
      "london_orb_ext_1x": 0,
      "london_orb_ext_1_5x": 0,
      "london_orb_ext_2x": 0,
      "orb_context": "Whether conditions favor double-break vs clean breakout",
      "ny_orb_status": "Awaiting NY Open",
      "vwap": 0,
      "weekly_open": 0,
      "monthly_open": 0,
      "prev_week_high": 0,
      "prev_week_low": 0,
      "prev_month_high": 0,
      "prev_month_low": 0,
      "bias": "Bullish/Bearish/Neutral",
      "bias_reason": "one sentence rooted in data",
      "day_type_forecast": "Trend/Normal/Neutral/Expanded Normal",
      "day_type_detail": "Explanation of expected day type behavior",
      "ib_expectation": "Whether IB likely defines range or gets broken",
      "trade_setups": [
        {
          "direction": "Long/Short",
          "entry": "price or zone",
          "stop_loss": 0,
          "target_1": 0,
          "target_2": 0,
          "rr_ratio": "e.g. 2.5:1",
          "confidence": "High/Medium/Low",
          "setup_type": "e.g. VWAP reversion",
          "rationale": "one line tied to data",
          "invalidation": "what kills this trade"
        }
      ]
    }
  },

  "cross_market": {
    "dxy": {
      "level": 0,
      "overnight_change": 0,
      "direction": "Strengthening/Weakening/Flat",
      "implication": "one sentence on what DXY means for NQ and Gold"
    },
    "vix": {
      "level": 0,
      "trend": "Rising/Falling/Flat",
      "severity": "low/moderate/elevated/extreme",
      "context": "one sentence on what VIX is telling us"
    },
    "tnx": {
      "level": 0,
      "overnight_change": 0,
      "context": "one sentence on yield regime and impact on growth/tech"
    },
    "crude": {
      "level": 0,
      "overnight_change": 0,
      "context": "one sentence"
    }
  },

  "economic_calendar": [
    {
      "time_et": "8:30 AM",
      "event": "Event name",
      "impact": "HIGH/MEDIUM",
      "prior": "value",
      "consensus": "value",
      "why_it_matters": "one line",
      "trade_warning": "optional — flag if this could blow up setups"
    }
  ],

  "premarket_warning": "If there's a high-impact event between 8:00-9:30 AM, flag it here. Otherwise null."
}

Provide your best estimates for all price levels based on your most recent market knowledge. Be specific with numbers — no placeholders. For trade setups, provide 2-3 per instrument with realistic entries, stops, and targets. Calculate R:R ratios accurately.

Today's date for the briefing: {date}"""

USER_PROMPT = "Generate today's complete morning briefing as the JSON structure specified. Use your best current market knowledge. All prices should be realistic estimates. Include 2-3 trade setups per instrument with calculated R:R ratios. Return ONLY the JSON object, nothing else."

NY_ORB_PROMPT = """The NY session has opened. Update the briefing with NY Opening Range Breakout data.

For each instrument (NQ, ES, GC), provide the NY ORB (9:30-9:45 AM ET) data:
- ny_orb_high, ny_orb_low, ny_orb_range
- ny_orb_broken: "Not broken/Broken high/Broken low/Both broken"
- ny_orb_ext_1x, ny_orb_ext_1_5x, ny_orb_ext_2x
- ny_orb_context: whether conditions favor double-break vs clean breakout

Also provide an updated playbook if the opening changes the bias.

Return JSON:
{
  "instruments": {
    "NQ": { "ny_orb_high": 0, "ny_orb_low": 0, "ny_orb_range": 0, "ny_orb_broken": "", "ny_orb_ext_1x": 0, "ny_orb_ext_1_5x": 0, "ny_orb_ext_2x": 0, "ny_orb_context": "" },
    "ES": { ... same fields ... },
    "GC": { ... same fields ... }
  },
  "updated_playbook": {
    "primary_bias": "",
    "bias_reason": "",
    "best_setup": "",
    "key_level": "",
    "danger_zone": ""
  }
}

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

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=SYSTEM_PROMPT.replace("{date}", today),
            messages=[{"role": "user", "content": USER_PROMPT}],
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
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

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
