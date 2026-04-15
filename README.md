# Pidgey AI — NYC Bird Analyst

A multi-agent birding assistant that answers live questions about bird
sightings across NYC parks, grounded in real eBird data and real weather
forecasts. Built for Columbia MSDS Agentic AI — Project 2 by Huckjun Hong.

---

## Live Demo

- **Frontend**: https://hong-agentic-ai-p1.web.app
- **Backend API**: https://pidgey-ai-backend-836832472845.us-central1.run.app

---

## Architecture — Three Steps

Every query flows through a LangGraph `StateGraph` with three nodes defined
in `backend/graph.py` (`collect → eda → hypothesis → END`). The pipeline is
fully dynamic: the user's query selects the specifics (e.g. parks, bird type, species), 
the forecast horizon, and the analytical lens at runtime.

### Step 1 · Collect 

Data is fetched live at request time — nothing is hardcoded or cached.

- **eBird sightings** — `backend/tools/ebird_tool.py → get_recent_sightings()`
  pulls the last 30 days of checklists for each selected hotspot from
  `https://api.ebird.org/v2/data/obs/{locId}/recent` and stamps each
  sighting with its `park_name`.
- **Open-Meteo forecast** — `backend/tools/weather_tool.py →
  get_nyc_week_forecast()` delegating to `get_location_forecast()` pulls
  temperature, wind, precipitation, and WMO weathercode. The forecast
  horizon is query-driven (7 days by default, 16 days when the user asks
  about "next two weeks" / "extended").
- **Dynamic hotspot selection** — `backend/graph.py → collect_node()`
  parses park tokens from the query (ramble, inwood, prospect, etc.). If
  no specific park is named, it fans out to all 8 hotspots in
  `backend/constants.py HOTSPOTS`.
- **Timeframe parsing** — `backend/tools/timeframe.py → parse_timeframe()`
  classifies the query as `weekend | week | extended` and emits
  `allowed_dates` for downstream filtering.
- **Parallel execution** — `asyncio.gather()` fans out all eBird calls
  concurrently inside `collect_node`.

### Step 2 · EDA (Explore & Analyze)

All numeric work runs in pandas **before** any LLM is invoked, so the
model only has to reason over pre-computed statistics.

- `backend/agents/eda_agent.py → run_eda()` builds a DataFrame from raw
  sightings and, per park, computes:
  - `species_count` via `group.groupby("comName").nunique()`
  - `total_birds_counted`, `total_checklists`
  - `rarity_score` = share of species seen as singletons
  - `top_10_chart_data` — top species by individuals counted
  - `rare_species_list` — species with ≤2 reports and ≤3 total counts
  - `notable_species`, `peak_date`, `species_chart_data`
- `_detect_species_query()` + `_build_species_search_results()` switch the
  pipeline into species-search mode when the query names a specific bird
  or bird family (warbler, hawk, owl…), yielding a per-park breakdown.
- Dynamic behavior: "Which park has the most rare birds?" short-circuits
  species detection; "What birds at the Ramble?" restricts the analysis to
  one park; "Best park this weekend?" ranks all 8.

### Step 3 · Hypothesize

- `backend/agents/hypothesis_agent.py → run_hypothesis()` feeds the
  pre-computed EDA stats + weather into Gemini 2.0 Flash via Vertex AI and
  forces a strict JSON schema response.
- The prompt requires the model to cite exact `species_count`, name real
  species from `notable_species`, compare specific days from the forecast,
  and never invent numbers.
- Python post-processors bolt grounded data back onto the response:
  `_build_specific_park_answer()`, `_build_rarity_ranking_answer()`,
  `_build_weather_note()` (with full day-by-day temp / wind / quality
  summary), and species-chart attachments.

---

## Core Requirements Checklist

| Requirement | Implementation | Location |
|---|---|---|
| Frontend | React 18 + Recharts | `frontend/src/App.jsx` |
| Agent Framework | LangGraph `StateGraph` (async) | `backend/graph.py` |
| Tool Calling | eBird + Open-Meteo HTTP tools | `backend/tools/ebird_tool.py`, `backend/tools/weather_tool.py` |
| Non-trivial Dataset | Live eBird API (500+ sightings / query across 8 hotspots) | `backend/tools/ebird_tool.py` |
| Multi-agent Pattern | Orchestrator + 2 LLM agents with distinct system prompts | `backend/graph.py`, `backend/agents/` |
| Deployed | FastAPI → Cloud Run, React → Firebase Hosting | [URLs above] |

---

## Grab-Bag Electives

| Elective | Implementation | Location |
|---|---|---|
| Structured Output | Strict JSON schema enforced by prompt + `validate_hypothesis_output()` + `post_llm_backstop()` | `backend/main.py`, `backend/agents/hypothesis_agent.py` |
| Second Data Retrieval | eBird API + Open-Meteo API (two independent external services) | `backend/tools/ebird_tool.py`, `backend/tools/weather_tool.py` |
| Data Visualization | Horizontal bar chart (species by park), grouped bar chart (generic-bird searches), top-10 chart, rarity table | `frontend/src/App.jsx` |
| Parallel Execution | `asyncio.gather()` over all eBird hotspot fetches | `backend/graph.py collect_node()` |
| Dynamic Forecast Horizon | 7-day default, 16-day when query asks for "extended" / "next two weeks" | `backend/tools/timeframe.py`, `weather_tool.py` |
| Timeframe-aware Weather | Filters forecast to `allowed_dates` so "this weekend" only ranks Sat/Sun | `backend/agents/hypothesis_agent.py _build_weather_note()` |

---

## Out-of-Scope Handling

Pidgey AI enforces a **three-layer defense** in `backend/main.py`. Every
layer has a positive framing — it nudges the user to a good birding
question instead of just refusing.

### Layer 1 — Pre-LLM Deterministic Gate (`oos_backstop()`)

Runs before any LLM or graph call. Order:

1. **Length guard** — rejects empty/near-empty queries.
2. **Fictional-term deny-list** (`FICTIONAL_TERMS`) — dragon, pokemon,
   unicorn…
3. **Nonsense repetition** (`check_nonsense()`) — catches repeated-token
   queries like "booby booby".
4. **Unknown-park detector** (`check_unknown_park_query()`) — if the user
   names a specific park NOT in our hotspot list, returns the friendly
   *"I love birding but haven't been there just yet..."* message.
   Generic references ("best park", "any park", "which park") are
   explicitly whitelisted via `GENERIC_PARK_MODIFIERS`.

### Layer 2 — LLM 4-Way Classifier (`classify_query()`)

Gemini 2.0 Flash classifies every query that passes Layer 1 into exactly
one of: `BIRDING`, `PROFANE`, `VIOLENT`, `OFFTOPIC`. This replaces the
older hardcoded profanity/violent/consumption term lists — the LLM
handles context ("rock dove" ≠ "throw rocks") and rephrasings that a
keyword list would miss. Each non-BIRDING label routes to a tailored
positive-framed refusal (profanity → "Let's keep it friendly!", violent
→ "I'm all about appreciating birds, not harming them!", off-topic →
help message).

### Layer 3 — Post-Generation Validation (`post_llm_backstop()`)

Inspects the generated hypothesis **after** the graph runs and overrides
with an OOS response if any negative control fires:

- `top_park` not in `VALID_PARKS` allow-list → hallucinated park.
- Confident recommendation with zero eBird sightings and no strong
  birding signal → slipped past the pre-LLM gate.
- Fictional term leaked through.

Additionally, `validate_hypothesis_output()` strips hallucinated species
from `species_highlights` by cross-referencing the raw eBird data.

### Negative Controls (documented)

The NEGATIVE CONTROLS block at the top of `backend/main.py` enumerates
ten things the assistant must NOT do (invent species, name invalid parks,
engage with violence/consumption/profanity/fictional creatures,
recommend without grounding, etc.) and names the two functions that
enforce them.

---

## Multi-Agent Pattern

**Pattern: Orchestrator + Analyst-Advisor (two specialized LLM agents).**

The orchestrator is the LangGraph `StateGraph` in `backend/graph.py`; it
routes state through the two agents, each with a **distinct system prompt
and distinct responsibility**.

| # | Agent | File | Role | System Prompt Identity |
|---|---|---|---|---|
| 1 | **Wildlife Data Analyst** | `backend/agents/eda_agent.py` | Consumes pre-computed pandas stats and emits a structured JSON analysis (parks_ranked, species counts, notable species, charts) | "You are a wildlife data analyst specializing in bird migration patterns in New York City…" |
| 2 | **NYC Birding Guide** | `backend/agents/hypothesis_agent.py` | Consumes EDA output + weather and produces a friendly, evidence-based recommendation citing specific species / numbers / days | "You are an expert NYC birding guide with deep knowledge of parks in New York and bird migration along the Atlantic Flyway…" |

The two agents never share a prompt, never make the same call, and cannot
answer each other's questions — separation is enforced by the graph edges.

---

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- A GCP project with **Vertex AI** enabled
- `gcloud CLI` authenticated with Application Default Credentials
  (`gcloud auth application-default login`)
- An **eBird API key** (set in `backend/constants.py EBIRD_KEY`)

### Backend

```bash
cd NYC-Bird-Analyst
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

### Frontend

```bash
cd frontend
npm install
npm start
```

The React dev server runs on `http://localhost:3000` and talks to the
backend via `REACT_APP_API_URL` (defaults to `http://localhost:8000`).

---

## Sample Queries

Each example exercises a different `response_type` so you can verify all
pipeline paths end-to-end.

| # | Query | `response_type` | What to verify |
|---|---|---|---|
| 1 | *"Best park for birding this weekend?"* | `recommendation` | Picks Sat/Sun from forecast, ranks all 8 hotspots, appends top-5 species + rare species for the winning park |
| 2 | *"What birds can I see in Central Park The Ramble?"* | `specific_park` | Restricts EDA to The Ramble; shows top-10 chart + rare species list |
| 3 | *"Is Saturday or Sunday better for birding?"* | `weather` | Weather-first answer; day-by-day temp/wind/quality summary |
| 4 | *"Any rare birds spotted in upper Manhattan?"* | `species_list` | Bullet list of notable species grounded in last-30-day data |
| 5 | *"Which park has the most rare birds?"* | `rarity_ranking` | Ranks parks by `rarity_score`, names the winner, lists full ranking |
| 6 | *"Where can I see a Bald Eagle in NYC?"* | `species_search` (specific) | Per-park breakdown with sighting counts and last-seen dates |
| 7 | *"Which park has the most warblers?"* | `species_search` (generic) | Grouped bar chart across top warbler species × parks |
| 8 | *"What birds are at Madison Square Park?"* | OOS — unknown-park | Returns friendly *"haven't been there just yet"* message |

**OOS negative examples** (all refused, each with a tailored positive message):

- *"Best burger in NYC?"* — off-topic → OOS help
- *"Can I eat a pigeon?"* — consumption intent refusal
- *"where can i go throw rocks at sparrows?"* — violent-intent refusal
- *"Booby booby"* — nonsense refusal

---

## Project Layout

```
NYC-Bird-Analyst/
├── backend/
│   ├── main.py                   # FastAPI, pre+post-LLM backstops, /analyze
│   ├── graph.py                  # LangGraph StateGraph: collect → eda → hypothesis
│   ├── constants.py              # HOTSPOTS, EBIRD_KEY, GEMINI_MODEL
│   ├── agents/
│   │   ├── eda_agent.py          # Wildlife Data Analyst (LLM #1)
│   │   └── hypothesis_agent.py   # NYC Birding Guide (LLM #2)
│   └── tools/
│       ├── ebird_tool.py         # eBird recent-observations
│       ├── weather_tool.py       # Open-Meteo forecast
│       └── timeframe.py          # weekend/week/extended parsing
└── frontend/
    └── src/App.jsx               # React UI + Recharts visualizations
```

---

## Stack

- **LLM**: Gemini 2.0 Flash (`gemini-2.0-flash-001`) via Vertex AI ADC auth
- **Orchestration**: LangGraph `StateGraph` (async nodes, `await graph.ainvoke`)
- **Data**: eBird API, Open-Meteo API
- **Backend**: FastAPI + httpx + pandas, deployed on Cloud Run
- **Frontend**: React 18 + Recharts, deployed on Firebase Hosting
