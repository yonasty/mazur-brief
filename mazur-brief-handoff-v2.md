# PROJECT: The Mazur Brief — Morning Trading Intelligence Dashboard
## Version 2.0 — Opus 4.6 Rewrite
**Goal: Build and deploy today. Text Joe a working link.**

---

## Step 1 — Before Writing Any Code

Search the Brain for deployment conventions:

```
ym_brain_recall(q="Cloud Run deployment GitHub CI/CD new app", world="software-co")
```

Follow those exact conventions for the entire infrastructure setup — GCP project, region, GitHub Actions workflow, secrets handling, everything. This app should be built and deployed exactly like every other app in Ben's ecosystem. Do not deviate, do not ask Ben to fill out forms or click through consoles. It should auto-deploy on push to main, the same way everything else does.

Also read the frontend-design skill (`/mnt/skills/public/frontend-design/SKILL.md`) before writing any UI code. This dashboard should look like something a professional built, not like AI slop.

---

## What We're Building

A single-URL morning intelligence dashboard for futures day trader Joe Mazur. No login, no password, fully public. He opens it at 5 AM ET and everything is already there — his complete pre-market preparation in one screen, replacing the 30-minute manual routine most traders do across 6 different tabs. Standalone tool, expandable in future Claude Code sessions.

This isn't a data dump. It's a **decision engine**. Every element on the page should answer one question: *What do I do when the bell rings?*

---

## Header & Branding

Fun, bold, slightly self-important header — like Joe named his own financial news desk. Tone: professional with a wink.

**Title:** "THE MAZUR BRIEF"

**Tagline** in smaller text below: *"Your 5 AM edge. Every morning."*

**Logo:** Custom SVG icon to the left of the title — a coffee cup with a candlestick chart rising out of it like steam. Monochrome, fits the dark terminal aesthetic.

The header should feel like the cold open of a one-man trading show. Slightly silly, genuinely useful.

---

## Stack

- Single `index.html` served statically via Cloud Run
- Anthropic API key stored as a Cloud Run secret / environment variable — never hardcoded
- Claude generates the morning briefing as structured JSON — all levels, analysis, trade setups, market context
- Model: `claude-sonnet-4-20250514`
- All data cached in localStorage keyed to today's date — no repeat API calls on refresh
- No database, no auth, no backend logic beyond serving the file

---

## The Prompt — This Is The Product

The Claude API prompt is where all the intelligence lives. This is what separates a useful dashboard from a glorified price ticker. The prompt must instruct Claude to think like a professional futures trader running a morning briefing, using Auction Market Theory, Volume Profile concepts, and multi-session analysis. Specifically, the prompt should request:

### Market Context Layer (What Happened While You Slept)
- Overnight narrative: What moved in Asia, what moved in London, and why
- Whether the three sessions (Asia → London → NY) are aligned or diverging — aligned sessions produce high-conviction trend days; divergence produces rotation and traps
- Any macro catalysts from overnight (central bank commentary, geopolitical, earnings)
- A plain-English "market mood" paragraph — 3-4 sentences max, no jargon, answering: *Is the market looking for direction, or has it already found it?*

### Per-Instrument Data (NQ, ES, GC)

**Price Structure:**
- Current price + overnight change (points and percentage)
- Previous day: high, low, close, and settlement
- YTD high and low (with how far current price is from each, as percentage)
- Overnight/Globex session: high, low, and range size
- Whether price is inside or outside the previous day's range (inside = compression/balance day likely; outside = trend day possible)

**Auction Market Theory Levels:**
- Previous day's Value Area High (VAH), Value Area Low (VAL), and Point of Control (POC) — these are the three most important levels in professional futures trading. Claude should estimate these from the prior session's price action and known settlement data.
- Whether the current overnight price is above, below, or inside the prior day's value area — this determines the opening playbook:
  - **Inside VA:** Expect rotation, fade the extremes
  - **Above VA:** Bullish bias, look for acceptance above VAH
  - **Below VA:** Bearish bias, look for acceptance below VAL
- Naked POCs: any recent session POCs that haven't been revisited (these act as magnets)

**Opening Range Breakout Levels:**
- London ORB (3:00–3:15 AM ET): high, low, range size, whether it's been broken and in which direction, extension targets at 1x, 1.5x, and 2x the range
- NY ORB (9:30–9:45 AM ET): placeholder section that says "Awaiting NY Open" until 9:45 AM ET, then fills automatically on refresh. Include the same fields: high, low, range, breakout status, extensions.
- ORB context note: The most common NQ pattern is a double-break (price breaks one side, then reverses to break the other), happening roughly 40% of the time. Claude should flag when conditions favor this pattern vs. a clean breakout.

**Institutional Reference Levels:**
- VWAP (developing, from overnight session start at 6 PM ET prior day) — the single most important institutional benchmark
- Weekly opening price (Sunday 6 PM ET open)
- Monthly opening price
- Prior week's high and low
- Prior month's high and low

**Session Bias & Day Type Forecast:**
- Bias: Bullish / Bearish / Neutral — with a one-sentence reason rooted in the data above, not vibes
- Predicted day type (based on Auction Market Theory):
  - **Trend Day:** IB likely to be broken early and extended significantly in one direction. Look for Open-Drive or Open-Test-Drive patterns.
  - **Normal Day:** IB sets the range for the session. Fade the extremes.
  - **Neutral Day:** Tight range, low conviction. Reduce size or sit out.
  - **Expanded Normal:** IB breaks late in the session for a move into the close.
- Initial Balance expectation: whether the first 30-60 minutes is likely to define the day's range or get broken. Pro traders watch IB extension — in ~98% of sessions, either the IB high or IB low gets broken.

**Trade Setups (2-3 per instrument, max):**
Each setup must include:
- Direction: Long or Short
- Entry price or zone
- Stop loss (tight — just beyond the invalidation level)
- Target 1 (conservative — nearest structural level)
- Target 2 (aggressive — next structural level beyond that)
- R:R ratio (calculated, not estimated)
- Confidence: High / Medium / Low
- Setup type: (e.g., "VWAP reversion," "London ORB breakout," "VA edge fade," "naked POC magnet")
- One-line rationale tied to the data
- Invalidation condition: what has to happen for this trade to be dead

### Macro & Cross-Market Context

**DXY (Dollar Index):**
- Current level and overnight change
- Whether it's strengthening or weakening and what that implies for NQ (inverse correlation) and Gold (inverse correlation)
- One sentence on the DXY trend: "Dollar is bid/offered/flat — headwind/tailwind for risk assets"

**VIX:**
- Single number, prominently displayed
- Color-coded: green below 15, amber 15-20, red 20-25, flashing red above 25
- VIX trend direction: rising VIX into falling ES = genuine fear; falling VIX into rising ES = complacency
- One sentence: what VIX is telling us about today's expected range and whether premium is expanding or compressing

**10-Year Treasury Yield (TNX):**
- Current level
- Overnight change
- This is the missing piece from v1 — bond yields drive everything. Rising yields pressure growth/tech (NQ), falling yields support it. One sentence on the current regime.

**Crude Oil (CL):**
- Current level and overnight change
- One sentence only — included because energy moves can spike VIX and disrupt equity setups

### Economic Calendar

- Today's HIGH and MEDIUM impact events only
- Time in ET
- Prior reading, consensus forecast, and why it matters in one line
- Flag any event that could blow up a trade setup (e.g., "CPI at 8:30 — all setups are paused until 8:35")
- **Pre-market critical window**: if there's a high-impact event between 8:00-9:30 AM, flag it prominently — Joe needs to know if he should wait for the print before entering anything

### The Playbook — Top of Page Summary

After all the analysis, Claude should produce a 3-5 bullet **"Playbook"** section that goes at the TOP of the dashboard, above everything else. This is the executive summary. Format:

> **TODAY'S PLAYBOOK**
> - Primary bias: [Bullish/Bearish/Neutral] — [one-line reason]
> - Day type expectation: [Trend/Normal/Neutral/Expanded Normal]
> - Best setup: [instrument + direction + entry zone + target]
> - Key level to watch: [the single most important price level today and why]
> - Danger zone: [what could go wrong — the scenario that invalidates everything above]

This is what Joe reads first. If he only has 30 seconds, this is enough.

---

## Timing, Caching & Refresh Logic

- On page load: check localStorage for today's cached briefing (keyed to YYYY-MM-DD)
- If fresh: render immediately, no API call
- If stale or missing: call Claude API, cache result, render
- **Two-stage refresh model:**
  - "Refresh Pre-Market" button: re-fetches the full briefing (use before 9:30 AM)
  - "Update NY ORB" button: appears at 9:45 AM ET — makes a targeted follow-up API call to fill in the NY ORB section and update the Playbook with any revised bias based on the open
- Show the timestamp of the last briefing generation prominently: "Briefing generated at 5:02 AM ET"
- If API key is missing or call fails: show a clear friendly error with instructions, not a blank screen
- While loading: show a skeleton UI with the section headers and pulsing placeholder bars — Joe should see the structure immediately and know data is incoming

---

## Design Direction

### Overall Aesthetic
Dark background — near black (#0d0d0d), not pure black. This is a tool used in a dark room at 5 AM by someone who stares at charts all day. The design should feel like a Bloomberg terminal that was redesigned by someone who actually cares about typography.

### Typography
- **Numbers (all prices, levels, percentages):** Monospace — JetBrains Mono (Google Fonts). Numbers are the product. They must be instantly scannable, perfectly aligned, and larger than you think they should be.
- **Section headers:** A bold geometric sans — Syne (Google Fonts). Slightly unusual, slightly aggressive. Not corporate.
- **Body text / analysis paragraphs:** DM Sans (Google Fonts). Clean, readable, doesn't compete with the numbers.
- **The Playbook section:** Larger type than everything else. This is the headline. Treat it like the front page of a newspaper.

### Color System
- **Background:** #0d0d0d (near-black)
- **Surface/cards:** #141414 with a subtle 1px border of #1f1f1f
- **Primary text:** #e8e8e8 (warm white, not blue-white)
- **Secondary text:** #6b6b6b
- **Bullish / Long:** #00dc82 (electric green — not the default CSS green)
- **Bearish / Short:** #ff4444 (clean red)
- **Neutral / Caution:** #ffaa00 (amber)
- **High confidence:** green glow/highlight
- **Medium confidence:** amber
- **Low confidence:** muted, desaturated
- **VIX danger states:** progressive red intensity with a subtle pulse animation above 25
- **Accent:** #00b4d8 (cyan) — used sparingly for interactive elements, links, the refresh button

### Layout & Information Hierarchy
1. **THE PLAYBOOK** — full width, top of page, largest type. This is the hero section.
2. **Market Overview paragraph** — full width, below playbook. The "here's what happened overnight" narrative.
3. **Instrument cards** — three-column grid (NQ | ES | GC). Each card contains all levels, ORB data, bias, and trade setups for that instrument. Dense but scannable. Use subtle horizontal rules to separate sub-sections within each card.
4. **Cross-Market strip** — horizontal bar below instrument cards showing DXY, VIX, TNX, CL as compact readouts with directional arrows and color coding.
5. **Economic Calendar** — compact table at the bottom. High-impact events get a red left-border accent. Times in ET.
6. **Footer:** Refresh buttons, generation timestamp, and a small disclaimer.

### Micro-Details That Matter
- Price changes: positive numbers get the green color + a subtle "▲" prefix. Negative get red + "▼". Zero change gets amber "—".
- Trade setups should feel like cards within cards — slightly elevated from the instrument card surface, with a left-border accent matching the direction (green for long, red for short).
- The London ORB section should have a subtle visual indicator of whether the range has been broken — a small progress-bar style element showing price relative to the ORB high/low.
- Add a subtle grain/noise texture overlay at very low opacity (2-3%) over the entire page — breaks up the digital flatness.
- Skeleton loading state: dark placeholder bars with a slow shimmer animation, matching the exact layout structure so content doesn't jump when it loads.

### What This Should NOT Look Like
- No purple gradients
- No rounded-everything bubbly UI
- No "dashboard template" energy
- No stock photos or decorative illustrations
- No excessive whitespace — this is a data-dense tool for a professional. Respect the density.
- No light mode option (it's 5 AM, respect the darkness)

---

## Expandability

Version 1. Keep code clean and commented so future Claude Code sessions can add:
- TradingView lightweight chart embeds per instrument (they have a free JS library)
- Interactive trade journal — log trades, see P&L
- Notes/watchlist section Joe can type into (persisted in localStorage)
- Live economic calendar API integration (Finnhub or Trading Economics)
- Historical playbook archive — save past briefings and review accuracy
- Alerts: configurable price alerts that trigger browser notifications when levels are hit
- Performance tracker: if Joe logs his trades, correlate them back to the Mazur Brief's suggested setups to measure signal quality over time

---

## Deliverables

1. `index.html` — fully working, production-grade, ready to deploy
2. All supporting files for Cloud Run deployment following Ben's standard conventions from the Brain
3. GitHub repo set up with CI/CD — push to main auto-deploys
4. A working URL Ben can text to Joe today

**One push. One link. Text it to Joe.**
