import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from constants import HOTSPOTS
from tools.ebird_tool import get_recent_sightings
from tools.weather_tool import get_nyc_week_forecast
from tools.timeframe import parse_timeframe
from agents.eda_agent import run_eda
from agents.hypothesis_agent import run_hypothesis


class BirdAnalystState(TypedDict, total=False):
    user_query: str
    date_filter: dict
    selected_hotspots: dict
    raw_sightings: list
    weather: dict
    eda_results: dict
    hypothesis: dict


async def collect_node(state: BirdAnalystState) -> dict:
    query = state["user_query"].lower()
    selected = {}
    for name, lid in HOTSPOTS.items():
        short = name.lower().replace("central park — ", "").replace(" park", "")
        if short and short in query:
            selected[name] = lid
            break
        if name.lower() in query:
            selected[name] = lid
            break
    if not selected and "central park" in query:
        for name, lid in HOTSPOTS.items():
            if name.lower().startswith("central park"):
                selected[name] = lid
                break
    if not selected:
        selected = HOTSPOTS

    ebird_tasks = [get_recent_sightings(lid, lname) for lname, lid in selected.items()]
    sightings_lists = await asyncio.gather(*ebird_tasks)
    raw_sightings = [s for sublist in sightings_lists for s in sublist]

    if raw_sightings:
        lats = [s["lat"] for s in raw_sightings if s.get("lat")]
        lngs = [s["lng"] for s in raw_sightings if s.get("lng")]
        avg_lat = sum(lats) / len(lats) if lats else 40.7812
        avg_lng = sum(lngs) / len(lngs) if lngs else -73.9665
        loc_name = list(selected.keys())[0] if len(selected) == 1 else "NYC"
    else:
        avg_lat, avg_lng = 40.7812, -73.9665
        loc_name = "NYC"

    date_filter = parse_timeframe(state["user_query"])
    weather = await get_nyc_week_forecast(avg_lat, avg_lng, loc_name, date_filter["days"])

    print(f"Weather data collected for {loc_name}: {len(weather)} days (timeframe={date_filter['kind']})")

    return {
        "selected_hotspots": selected,
        "raw_sightings": raw_sightings,
        "weather": weather,
        "date_filter": date_filter,
    }


async def eda_node(state: BirdAnalystState) -> dict:
    eda_results = await run_eda(state["raw_sightings"], state["user_query"])
    return {"eda_results": eda_results}


async def hypothesis_node(state: BirdAnalystState) -> dict:
    hypothesis = await run_hypothesis(
        state["eda_results"],
        state["weather"],
        state["user_query"],
        state.get("date_filter") or {},
    )
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
