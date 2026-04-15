Build a full-stack app called "NYC Bird Analyst" - an agentic birding assistant for Manhattan.

IMPORTANT NOTES:
- NWS API requires User-Agent header or returns 403
- Vertex AI uses ADC auth only, no API keys
- Use async nodes in LangGraph with await graph.ainvoke()
- Strip markdown fences before JSON parsing:
  text.strip().removeprefix("```json").removesuffix("```").strip()
- Both LLM agents MUST have different system prompts

FILES TO CREATE:

=== backend/tools/ebird_tool.py ===
import httpx
from backend.constants import EBIRD_KEY, EBIRD_DAYS

async def get_recent_sightings(location_id: str, location_name: str) -> list[dict]:
    url = f"https://api.ebird.org/v2/data/obs/{location_id}/recent"
    headers = {"X-eBirdApiToken": EBIRD_KEY}
    params = {"back": EBIRD_DAYS, "maxResults": 200}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            sightings = r.json()
            for s in sightings:
                s["park_name"] = location_name
            print(f"eBird: fetched {len(sightings)} sightings from {location_name}")
            return sightings
    except Exception as e:
        print(f"eBird error for {location_name}: {e}")
        return []

=== backend/tools/weather_tool.py ===
import httpx

async def get_nyc_weekend_forecast() -> dict:
    url = "https://api.weather.gov/gridpoints/OKX/33,37/forecast"
    headers = {
        "User-Agent": "nyc-bird-analyst/1.0 (student-project@columbia.edu)",
        "Accept": "application/geo+json"
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            periods = r.json()["properties"]["periods"]
            weekend = {}
            for p in periods:
                name = p["name"]
                if "Saturday" in name or "Sunday" in name:
                    wind_dir = p.get("windDirection", "")
                    forecast = p.get("shortForecast", "")
                    if "SW" in wind_dir:
                        note = "Favorable SW winds push migrants north"
                    elif "NE" in wind_dir:
                        note = "NE winds suppress migration activity"
                    elif any(w in forecast.lower() for w in ["rain","shower","drizzle"]):
                        note = "Rain expected — fewer birds active"
                    else:
                        note = "Calm conditions, good for birding"
                    weekend[name] = {
                        "temperature": p.get("temperature"),
                        "windSpeed": p.get("windSpeed"),
                        "windDirection": wind_dir,
                        "shortForecast": forecast,
                        "birding_note": note
                    }
            return weekend
    except Exception as e:
        print(f"NWS error: {e}")
        return {}

=== backend/agents/eda_agent.py ===
import json
import pandas as pd
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.constants import GCP_PROJECT, GEMINI_MODEL

EDA_SYSTEM_PROMPT = """
You are a wildlife data analyst specializing in bird migration patterns in New York City.
You receive pre-computed pandas statistics from eBird sighting data and produce structured analysis.

You ALWAYS:
- Reference exact species counts per park from the data given
- Identify top 3 notable or rare species (low howMany = rare)
- Rank parks by species diversity using the numbers provided
- Output ONLY valid JSON with no prose and no markdown fences

You NEVER invent species or numbers not present in the input data.
"""

async def run_eda(raw_sightings: list[dict]) -> dict:
    if not raw_sightings:
        return {"parks_ranked": [], "total_unique_species_across_all_parks": 0,
                "most_notable_sighting": "No data", "chart_data": []}

    df = pd.DataFrame(raw_sightings)
    df["obsDt"] = pd.to_datetime(df["obsDt"], errors="coerce")
    df["date"] = df["obsDt"].dt.date
    df["howMany"] = pd.to_numeric(df.get("howMany", 1), errors="coerce").fillna(1)

    parks_summary = []
    for park, group in df.groupby("park_name"):
        species_count = group["comName"].nunique()
        total_sightings = len(group)
        rare = group[group["howMany"] == 1]["comName"].unique().tolist()
        rarity_score = round(len(rare) / species_count * 100, 1) if species_count else 0
        peak_date = str(group.groupby("date").size().idxmax()) if not group.empty else ""
        short_name = park.replace("Central Park — ", "").replace(" Park", "")
        parks_summary.append({
            "park": park,
            "short_name": short_name,
            "species_count": int(species_count),
            "total_sightings": int(total_sightings),
            "rarity_score": rarity_score,
            "notable_species": rare[:5],
            "peak_date": peak_date
        })

    parks_summary.sort(key=lambda x: x["species_count"], reverse=True)

    llm = ChatVertexAI(model_name=GEMINI_MODEL, project=GCP_PROJECT, location="us-east1")
    messages = [
        SystemMessage(content=EDA_SYSTEM_PROMPT),
        HumanMessage(content=f"""Analyze this park data and return ONLY this JSON structure:
{{
  "parks_ranked": [
    {{
      "park": str,
      "species_count": int,
      "total_sightings": int,
      "rarity_score": float,
      "notable_species": [str],
      "peak_date": str,
      "one_line_summary": str
    }}
  ],
  "total_unique_species_across_all_parks": int,
  "most_notable_sighting": str,
  "chart_data": [{{"park": str, "species_count": int}}]
}}

Data: {json.dumps(parks_summary)}""")
    ]
    response = await llm.ainvoke(messages)
    text = response.content.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)

=== backend/agents/hypothesis_agent.py ===
import json
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.constants import GCP_PROJECT, GEMINI_MODEL

HYPOTHESIS_SYSTEM_PROMPT = """
You are an expert NYC birding guide with deep knowledge of Manhattan parks
and bird migration along the Atlantic Flyway. You receive ranked park analysis
and weekend weather data and produce a practical evidence-based recommendation.

You ALWAYS:
- Name the single best park and explain why using exact numbers
- Cite specific species_count ("34 species this week")
- Name at least 2 specific bird species from the data
- Reference wind direction and its effect on migration
- Compare Saturday vs Sunday using the forecast
- Write in a friendly expert tone like a local birding expert texting a friend

You NEVER:
- Make vague statements without citing data
- Recommend a park without its species count
- Ignore the weather data provided
"""

async def run_hypothesis(eda_results: dict, weather: dict) -> dict:
    llm = ChatVertexAI(model_name=GEMINI_MODEL, project=GCP_PROJECT, location="us-east1")
    messages = [
        SystemMessage(content=HYPOTHESIS_SYSTEM_PROMPT),
        HumanMessage(content=f"""Based on this data, return ONLY this JSON:
{{
  "top_park": str,
  "best_day": str,
  "reason": str,
  "species_highlights": [str],
  "weather_note": str,
  "rankings": [{{"park": str, "species_count": int, "rarity_score": float}}],
  "chart_data": [{{"park": str, "species_count": int}}]
}}

EDA Results: {json.dumps(eda_results)}
Weather: {json.dumps(weather)}""")
    ]
    response = await llm.ainvoke(messages)
    text = response.content.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)

=== backend/graph.py ===
import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from backend.constants import HOTSPOTS
from backend.tools.ebird_tool import get_recent_sightings
from backend.tools.weather_tool import get_nyc_weekend_forecast
from backend.agents.eda_agent import run_eda
from backend.agents.hypothesis_agent import run_hypothesis

class BirdAnalystState(TypedDict):
    user_query: str
    selected_hotspots: dict
    raw_sightings: list
    weather: dict
    eda_results: dict
    hypothesis: dict

async def collect_node(state: BirdAnalystState) -> dict:
    query = state["user_query"].lower()
    if "ramble" in query:
        selected = {"Central Park — The Ramble": "L109516"}
    elif "north end" in query:
        selected = {"Central Park — North End": "L2581861"}
    elif "inwood" in query:
        selected = {"Inwood Hill Park": "L684740"}
    elif "riverside" in query:
        selected = {"Riverside Park": "L968327"}
    elif "fort tryon" in query:
        selected = {"Fort Tryon Park": "L630159"}
    elif "morningside" in query:
        selected = {"Morningside Park": "L2078464"}
    else:
        selected = HOTSPOTS

    tasks = [get_recent_sightings(lid, lname) for lname, lid in selected.items()]
    tasks.append(get_nyc_weekend_forecast())
    results = await asyncio.gather(*tasks)

    weather = results[-1]
    sightings_lists = results[:-1]
    raw_sightings = [s for sublist in sightings_lists for s in sublist]

    return {"selected_hotspots": selected, "raw_sightings": raw_sightings, "weather": weather}

async def eda_node(state: BirdAnalystState) -> dict:
    eda_results = await run_eda(state["raw_sightings"])
    return {"eda_results": eda_results}

async def hypothesis_node(state: BirdAnalystState) -> dict:
    hypothesis = await run_hypothesis(state["eda_results"], state["weather"])
    return {"hypothesis": hypothesis}

def build_graph():
    graph = StateGraph(BirdAnalystState)
    graph.add_node("collect", collect_node)
    graph.add_node("eda", eda_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "eda")
    graph.add_edge("eda", "hypothesis")
    graph.add_edge("hypothesis", END)
    return graph.compile()

=== backend/main.py ===
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.graph import build_graph

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
graph = build_graph()

class QueryRequest(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "NYC Bird Analyst running"}

@app.post("/analyze")
async def analyze(request: QueryRequest):
    result = await graph.ainvoke({"user_query": request.query})
    return result["hypothesis"]

=== backend/requirements.txt ===
fastapi
uvicorn[standard]
langgraph
langchain-google-vertexai
langchain-core
pandas
httpx
python-dotenv

=== backend/Dockerfile ===
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

=== frontend/package.json ===
{
  "name": "nyc-bird-analyst",
  "version": "1.0.0",
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "recharts": "^2.0.0",
    "react-scripts": "5.0.1"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build"
  },
  "browserslist": {
    "production": [">0.2%", "not dead"],
    "development": ["last 1 chrome version"]
  }
}

=== frontend/public/index.html ===
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NYC Bird Analyst</title>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>

=== frontend/src/index.js ===
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<React.StrictMode><App /></React.StrictMode>);

=== frontend/src/App.jsx ===
import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const suggestions = [
    "Best park for birding this weekend?",
    "What birds can I see in Central Park The Ramble?",
    "Is Saturday or Sunday better for birding?",
    "Any rare birds spotted in upper Manhattan?"
  ];

  const analyze = async (q) => {
    const question = q || query;
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: question })
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 24, fontFamily: 'sans-serif' }}>
      <h1 style={{ fontSize: 32, marginBottom: 4 }}>🐦 NYC Bird Analyst</h1>
      <p style={{ color: '#666', marginBottom: 24 }}>
        Find the best birding spots in Manhattan this weekend
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {suggestions.map(s => (
          <button key={s} onClick={() => { setQuery(s); analyze(s); }}
            style={{ padding: '6px 12px', borderRadius: 20, border: '1px solid #0ea5e9',
                     background: 'white', color: '#0ea5e9', cursor: 'pointer', fontSize: 13 }}>
            {s}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && analyze()}
          placeholder="Ask about birding in Manhattan..."
          style={{ flex: 1, padding: '10px 14px', borderRadius: 8,
                   border: '1px solid #ddd', fontSize: 15 }} />
        <button onClick={() => analyze()}
          style={{ padding: '10px 20px', borderRadius: 8, background: '#0ea5e9',
                   color: 'white', border: 'none', cursor: 'pointer', fontSize: 15 }}>
          {loading ? '...' : 'Analyze'}
        </button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>
          🔍 Fetching real-time eBird data and analyzing...
        </div>
      )}

      {error && (
        <div style={{ padding: 16, background: '#fee2e2', borderRadius: 8, color: '#dc2626' }}>
          Error: {error}
        </div>
      )}

      {result && (
        <div>
          <div style={{ padding: 20, background: '#eff6ff', borderRadius: 12, marginBottom: 16 }}>
            <h2 style={{ margin: '0 0 8px', fontSize: 22 }}>📍 {result.top_park}</h2>
            <p style={{ margin: '0 0 8px', color: '#1d4ed8', fontWeight: 600 }}>
              Best day: {result.best_day}
            </p>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{result.reason}</p>
          </div>

          <div style={{ padding: 16, background: '#fefce8', borderRadius: 12, marginBottom: 16 }}>
            <strong>🌤️ Weather Note:</strong> {result.weather_note}
          </div>

          {result.species_highlights?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 12 }}>🦅 Species to Watch For</h3>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {result.species_highlights.map(s => (
                  <span key={s} style={{ padding: '4px 12px', background: '#dcfce7',
                    borderRadius: 20, fontSize: 13, color: '#166534' }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {result.chart_data?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Species Diversity by Park — Last 7 Days</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={result.chart_data} layout="vertical"
                  margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="park" width={120} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="species_count" fill="#0ea5e9" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {result.rankings?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Full Park Rankings</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: '#f1f5f9' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Rank</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Park</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Species</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Rarity Score</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rankings.map((r, i) => (
                    <tr key={r.park} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '8px 12px' }}>#{i + 1}</td>
                      <td style={{ padding: '8px 12px' }}>{r.park}</td>
                      <td style={{ padding: '8px 12px' }}>{r.species_count}</td>
                      <td style={{ padding: '8px 12px' }}>{r.rarity_score?.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <footer style={{ marginTop: 40, paddingTop: 16, borderTop: '1px solid #e2e8f0',
                       color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>
        Data: eBird API + NWS Weather | Real-time Manhattan birding intelligence
      </footer>
    </div>
  );
}