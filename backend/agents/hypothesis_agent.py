import json
from datetime import datetime
from collections import Counter
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage
from constants import GCP_PROJECT, GEMINI_MODEL, GCP_REGION

HYPOTHESIS_SYSTEM_PROMPT = """
You are an expert NYC birding guide with deep knowledge of parks in New York
and bird migration along the Atlantic Flyway. You receive ranked park analysis
and weekend weather data and produce a practical evidence-based recommendation.

You ALWAYS:
- Name the single best park and explain why using exact numbers
- Cite specific species_count ("34 species this week")
- Name at least 2 specific bird species from the data
- Reference wind direction and its effect on migration
- Compare weathers for different dates using the forecast
- Write in a friendly expert tone like a local birding expert texting a friend

You NEVER:
- Make vague statements without citing data
- Recommend a park without its species count
- Ignore the weather data provided

You MUST return only raw JSON. No markdown, no backticks,
no explanations. Start your response with { and end with }.
"""

RARE_KEYWORDS = ["rare", "unusual", "uncommon", "spotted", "sighting"]
RARITY_RANKING_MARKERS = ("most rare", "rarity", "most unusual", "rarest", "ranked by rarity")


def _is_rarity_ranking_query(q: str) -> bool:
    q = (q or "").lower()
    if any(m in q for m in RARITY_RANKING_MARKERS):
        return True
    return ("rare" in q or "unusual" in q) and ("which park" in q or "most" in q or "rank" in q or "compare" in q)


def _build_rarity_ranking_answer(eda_results: dict) -> tuple[str, list[dict], str | None]:
    parks = list((eda_results or {}).get("parks_ranked") or [])
    if not parks:
        return ("No park data available to rank by rarity.", [], None)
    ranked = sorted(parks, key=lambda p: p.get("rarity_score", 0) or 0, reverse=True)
    top = ranked[0]
    top_name = top.get("park", "")
    top_score = top.get("rarity_score", 0)
    top_notable = top.get("notable_species") or []
    notable_str = ", ".join(top_notable[:3]) if top_notable else "none flagged"

    lines = []
    for i, p in enumerate(ranked, start=1):
        nm = p.get("park", "")
        score = p.get("rarity_score", 0)
        spc = p.get("species_count", 0)
        notes = p.get("notable_species") or []
        notes_str = f" — e.g. {', '.join(notes[:2])}" if notes else ""
        lines.append(f"#{i} {nm}: {score}% rarity across {spc} species{notes_str}")

    direct_answer = (
        f"{top_name} has the most rare birds right now — "
        f"rarity score {top_score}% across {top.get('species_count', 0)} species "
        f"(notable: {notable_str}).\n\n"
        f"Full ranking by rarity score:\n" + "\n".join(lines)
    )
    rankings = [
        {
            "park": p.get("park", ""),
            "species_count": int(p.get("species_count", 0) or 0),
            "rarity_score": float(p.get("rarity_score", 0) or 0),
        }
        for p in ranked
    ]
    return direct_answer, rankings, top_name


def _fallback(response_type: str = "specific_park") -> dict:
    return {
        "response_type": response_type,
        "direct_answer": "Here are recent sightings from that park.",
        "top_park": None,
        "best_day": None,
        "reason": "",
        "species_highlights": [],
        "species_chart_data": [],
        "weather_note": "",
        "rankings": [],
        "chart_data": [],
    }


def _build_species_chart_data(eda_results: dict) -> list[dict]:
    counter: Counter = Counter()
    for park in eda_results.get("parks_ranked", []) or []:
        for entry in park.get("species_chart_data", []) or []:
            counter[entry["species"]] += int(entry.get("count", 0))
        if not park.get("species_chart_data"):
            for sp in park.get("notable_species", []) or []:
                counter[sp] += 1
    ranked = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:15]
    return [{"species": s, "count": c} for s, c in ranked]


def _build_rare_sightings(eda_results: dict) -> list[dict]:
    pairs = []
    for park in eda_results.get("parks_ranked", []) or []:
        park_name = park.get("park", "")
        for sp in park.get("notable_species", []) or []:
            pairs.append({"species": sp, "park": park_name})
    return pairs


def _weather_advice(weather: dict) -> str:
    sat = next((v for k, v in (weather or {}).items() if "Saturday" in k and "Night" not in k), None)
    sun = next((v for k, v in (weather or {}).items() if "Sunday" in k and "Night" not in k), None)
    if sat:
        wind = sat.get("windDirection", "")
        forecast = (sat.get("shortForecast") or "").lower()
        sat_good = ("NE" not in wind) and not any(w in forecast for w in ["rain", "shower", "drizzle"])
        if sat_good:
            return f"\nBest time: Head out Saturday morning — {sat.get('birding_note', '')}"
    if sun:
        return f"\nBest time: {sun.get('birding_note', '')}"
    return ""


def _build_species_search_answer(search: dict, weather_note: str) -> str:
    species_name = search.get("searched_species", "that species")
    found = search.get("found_in_parks", []) or []
    is_generic = search.get("is_generic_type", False)
    total_sightings = search.get("total_sightings") or sum(p["sighting_count"] for p in found)
    total_unique = search.get("total_unique_species", 0)
    if not found:
        return (
            f"No {species_name} sightings reported in our 8 NYC hotspots in the last 30 days. "
            "Try asking about more common species like Red-tailed Hawk or American Robin."
        )

    label = f"{species_name}s" if is_generic else species_name.title()
    best_park = found[0]["park"]
    best_count = found[0]["sighting_count"]
    last_seen = found[0].get("last_seen")
    last_seen_str = ""
    if last_seen:
        try:
            dt = datetime.fromisoformat(str(last_seen))
            last_seen_str = dt.strftime("%B %d")
        except Exception:
            last_seen_str = str(last_seen)[:10]

    def _park_line(p):
        base = f"• {p['park']}: {p['sighting_count']} sighting{'s' if p['sighting_count'] > 1 else ''}"
        if is_generic and p.get("unique_species"):
            top = p.get("top_species") or p.get("species_list") or []
            sample = (
                f" ({', '.join(top[:3])}{'...' if len(top) > 3 else ''})"
                if top else ""
            )
            base += f" of {p['unique_species']} species{sample}"
        return base

    def _top_two(items, key):
        ranked = sorted(items, key=lambda p: p.get(key, 0) or 0, reverse=True)
        return ranked[:2]

    if is_generic:
        headline = (
            f"Good news! {total_sightings} {label} sightings across "
            f"{total_unique} species in {len(found)} NYC park"
            f"{'s' if len(found) > 1 else ''} in the last 30 days."
        )

        by_species = _top_two(found, "unique_species")
        by_count = _top_two(found, "sighting_count")

        def _followed(parks, fmt):
            if not parks:
                return ""
            first = fmt(parks[0])
            if len(parks) > 1 and parks[1].get("park") != parks[0].get("park"):
                return f"{first}, followed by {fmt(parks[1])}"
            return first

        species_line = _followed(
            by_species,
            lambda p: f"{p['park']} ({p.get('unique_species', 0)} species)",
        )
        count_line = _followed(
            by_count,
            lambda p: f"{p['park']} ({p['sighting_count']} counts)",
        )

        observations = []
        if species_line:
            observations.append(
                f"The most {species_name} species diversity was seen in {species_line}."
            )
        if count_line:
            observations.append(
                f"By counts, the most {label} were seen in {count_line}."
            )

        direct_answer = f"{headline}\n\nKey observations:\n" + "\n".join(observations)
        return direct_answer

    headline = (
        f"Good news! {label} have been spotted "
        f"{total_sightings} times across {len(found)} NYC park"
        f"{'s' if len(found) > 1 else ''} in the last 30 days."
    )

    park_lines = "\n".join(_park_line(p) for p in found)
    direct_answer = (
        f"{headline}\n\n"
        f"Your best bet is {best_park} with {best_count} recent sighting"
        f"{'s' if best_count > 1 else ''}"
        f"{f' (last seen {last_seen_str})' if last_seen_str else ''}.\n\n"
        f"All sightings:\n{park_lines}"
    )
    return direct_answer


def _build_specific_park_answer(park_data: dict) -> str:
    park_name = park_data.get("park", "this park")
    species_count = park_data.get("species_count", 0)
    total_birds = park_data.get("total_birds_counted", 0)
    total_checklists = park_data.get("total_checklists") or "multiple"
    top_species = park_data.get("top_10_chart_data") or []
    rare_list = park_data.get("rare_species_list") or []

    if top_species:
        top_lines = "\n".join(
            f"• {s['species']} ({s['total_counted']} individuals counted)"
            for s in top_species[:5]
        )
    else:
        top_lines = "• various species"

    if rare_list:
        rare_names = ", ".join(r["name"] for r in rare_list[:4])
    else:
        rare_names = "none flagged in last 30 days"

    return (
        f"{park_name} has {species_count} species recorded across "
        f"{total_checklists} birder visits in the last 30 days, "
        f"with {total_birds} individual birds counted.\n\n"
        f"Most commonly seen:\n{top_lines}\n\n"
        f"Rare species to look out for: {rare_names}."
    )


def _select_park(eda_results: dict, user_query: str) -> dict | None:
    parks = (eda_results or {}).get("parks_ranked") or []
    if not parks:
        return None
    q = (user_query or "").lower()
    for p in parks:
        name = (p.get("park") or "").lower()
        short = name.replace("central park — ", "").replace(" park", "")
        if short and short in q:
            return p
        if name and name in q:
            return p
    return parks[0]


_QUALITY_ORDER = {"Excellent": 0, "Good": 1, "Fair": 2, "Poor": 3}


def _conditions_rank(forecast: str) -> int:
    c = (forecast or "").lower()
    if "clear" in c:
        return 0
    if "partly cloudy" in c or "partly sunny" in c:
        return 2
    if "overcast" in c or "cloudy" in c:
        return 3
    return 4


def _temp_penalty(d: dict) -> float:
    try:
        return abs(float(d.get("temperature", 60)) - 62)
    except Exception:
        return 99


def _rank_key(d: dict) -> tuple:
    return (
        _QUALITY_ORDER.get(d.get("birding_quality", "Good"), 1),
        _conditions_rank(d.get("shortForecast", "")),
        float(d.get("precipitation", 0) or 0),
        float(d.get("windspeed", 0) or 0),
        _temp_penalty(d),
        d.get("date", d.get("name", "")),
    )


def _best_days(days: list) -> list:
    if not days:
        return []
    ranked = sorted(days, key=_rank_key)
    return [ranked[0]]


def _birding_rationale(d: dict) -> str:
    cond = (d.get("shortForecast") or "").lower()
    if "overcast" in cond or "cloudy" in cond:
        return "Overcast skies keep birds active and foraging longer."
    if "clear" in cond:
        return "Clear, calm conditions make for excellent dawn and dusk activity."
    if "rain" in cond or "shower" in cond or "drizzle" in cond:
        return "Birds tend to resume feeding heavily right after a rain break."
    return "Mild conditions mean steady bird activity throughout the morning."


def _best_days_phrase(best: list) -> str:
    names = [d.get("display_date") or d.get("name", "") for d in best]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _day_summary_line(d: dict) -> str:
    return (
        f"• {d.get('display_date') or d.get('name','')}: "
        f"{d.get('shortForecast','').lower()}, "
        f"{d.get('temperature','?')}°F, wind {d.get('windspeed','?')} mph "
        f"[{d.get('birding_quality','?')}]"
    )


def _build_weather_note(
    weather: dict,
    featured_park: str | None = None,
    date_filter: dict | None = None,
) -> tuple[str, str]:
    all_days = list((weather or {}).values())
    if not all_days:
        return "Weather data unavailable.", "N/A"

    timeframe_label = (date_filter or {}).get("label") or "this week"
    allowed = (date_filter or {}).get("allowed_dates")
    scoped = [d for d in all_days if d.get("date") in allowed] if allowed else all_days
    if not scoped:
        scoped = all_days

    best = _best_days(scoped)
    if not best:
        return f"No strong birding days in {timeframe_label}.", all_days[0].get("display_date", "")

    leader = best[0]
    destination = f" to visit {featured_park}" if featured_park else " for birding"
    rationale = _birding_rationale(leader)

    summary_lines = "\n".join(_day_summary_line(d) for d in scoped)
    header = (
        f"Best day in {timeframe_label}{destination}: "
        f"{leader.get('display_date') or leader.get('name','')} — "
        f"{leader.get('shortForecast','').lower()}, "
        f"{leader.get('temperature','?')}°F, wind {leader.get('windspeed','?')} mph. "
        f"{rationale}"
    )
    weather_note = f"{header}\n\nForecast for {timeframe_label}:\n{summary_lines}"
    return weather_note, leader.get("display_date") or leader.get("name", "")


async def run_hypothesis(eda_results: dict, weather: dict, user_query: str, date_filter=None) -> dict:
    print(f"Weather received: {weather}")
    print(f"Weather keys: {list(weather.keys()) if weather else 'EMPTY'}")
    weather_note, best_day = _build_weather_note(weather, None, date_filter)

    species_search = eda_results.get("species_search_results") if isinstance(eda_results, dict) else None
    if species_search:
        found = species_search.get("found_in_parks") or []
        featured = found[0]["park"] if found else None
        species_weather_note, species_best_day = _build_weather_note(weather, featured, date_filter)
        return {
            "response_type": "species_search",
            "direct_answer": _build_species_search_answer(species_search, species_weather_note),
            "top_park": None,
            "best_day": species_best_day,
            "reason": "",
            "species_highlights": [],
            "species_chart_data": [],
            "species_search_results": species_search,
            "weather_note": species_weather_note,
            "rankings": [],
            "chart_data": [],
        }

    if _is_rarity_ranking_query(user_query):
        direct_answer, rankings, top_park = _build_rarity_ranking_answer(eda_results)
        species_chart_data = _build_species_chart_data(eda_results)
        rec_note, rec_best = _build_weather_note(weather, top_park, date_filter)
        return {
            "response_type": "rarity_ranking",
            "direct_answer": direct_answer,
            "top_park": top_park,
            "best_day": rec_best,
            "reason": (
                f"Ranked by rarity score — the % of species seen as singletons in each park."
            ),
            "species_highlights": [],
            "species_chart_data": species_chart_data,
            "weather_note": rec_note,
            "rankings": rankings,
            "chart_data": [
                {"park": r["park"], "species_count": r["species_count"]} for r in rankings
            ],
        }

    species_chart_data = _build_species_chart_data(eda_results)
    rare_sightings = _build_rare_sightings(eda_results)

    q_lower = (user_query or "").lower()
    is_rare_query = any(k in q_lower for k in RARE_KEYWORDS)

    empty_msg = (
        "No unusual sightings reported in the last 30 days across "
        "our 8 Manhattan hotspots. This can happen outside peak "
        "migration season. Try asking about common species instead: "
        "'What birds can I see in Central Park The Ramble?'"
    )
    rare_formatted = (
        "\n".join(f"• {r['species']} at {r['park']}" for r in rare_sightings)
        if rare_sightings
        else empty_msg
    )

    rare_instructions = ""
    if is_rare_query:
        rare_instructions = f"""
This is a RARE BIRDS query. Set response_type to "species_list".
For rare bird queries, you MUST only list species that appear in the
notable_species lists from the eda_results data provided. These are real
sightings from the last 30 days. Do NOT use your training knowledge to
suggest species. If notable_species lists are empty, say
'{empty_msg}'

Set direct_answer to exactly this pre-formatted text (verbatim):
"Recent rare sightings in Upper Manhattan (last 30 days):
{rare_formatted}"
"""

    llm = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_REGION)
    messages = [
        SystemMessage(content=HYPOTHESIS_SYSTEM_PROMPT),
        HumanMessage(content=f"""The user asked: '{user_query}'
Answer their SPECIFIC question using the data.
- If they asked to list species: list actual species names
- If they asked to compare parks: compare with numbers
- If they asked about one park: focus only on that park
- If they asked about weather: lead with weather analysis
- If they asked for best park: give ranked recommendation
Always cite specific numbers and species names from the data.
Never give the same generic answer regardless of question.
{rare_instructions}
Return ONLY this JSON (no markdown, no backticks):
{{
  "response_type": str,
  "direct_answer": str,
  "top_park": str,
  "best_day": str,
  "reason": str,
  "species_highlights": [str],
  "weather_note": str,
  "rankings": [{{"park": str, "species_count": int, "rarity_score": float}}],
  "chart_data": [{{"park": str, "species_count": int}}]
}}

Set response_type based on the user's question:
- One specific park question -> "specific_park"
- List species question -> "species_list"
- Weather or which day question -> "weather"
- Best park recommendation -> "recommendation"
- Compare parks -> "comparison"

Do NOT generate species_chart_data — it will be added in Python.

Weather contains all upcoming daytime forecast periods keyed by their
real name (e.g. "Today", "Monday", "Tuesday"...). Refer to days by
their actual names — NEVER hardcode "Saturday" or "Sunday".

The best day for birding this week is {best_day}. Reference this in
your recommendation's reason field.

Do NOT include any weather text in direct_answer — weather_note is
a separate field handled in Python.

EDA Results: {json.dumps(eda_results)}
Weather: {json.dumps(weather)}
Precomputed rare sightings (for your reference): {json.dumps(rare_sightings)}""")
    ]
    response = await llm.ainvoke(messages)
    raw = response.content
    text = raw.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        parsed = json.loads(text)
    except Exception as e:
        print(f"hypothesis_agent JSON parse failed: {e}")
        print(f"Raw response: {raw!r}")
        fallback = _fallback("species_list" if is_rare_query else "specific_park")
        fallback["species_chart_data"] = species_chart_data
        fallback["weather_note"] = weather_note
        fallback["best_day"] = best_day
        if is_rare_query:
            fallback["direct_answer"] = (
                (empty_msg if not rare_sightings else f"Recent rare sightings in Upper Manhattan (last 30 days):\n{rare_formatted}")
            )
        else:
            park_data = _select_park(eda_results, user_query)
            if park_data:
                fallback["direct_answer"] = _build_specific_park_answer(park_data)
                fallback["top_10_chart_data"] = park_data.get("top_10_chart_data", [])
                fallback["rare_species_list"] = park_data.get("rare_species_list", [])
                fallback["top_park"] = park_data.get("park")
        return fallback

    parsed["species_chart_data"] = species_chart_data
    parsed["weather_note"] = weather_note
    parsed["best_day"] = best_day
    if is_rare_query:
        parsed["response_type"] = "species_list"
        parsed["direct_answer"] = (
            (empty_msg if not rare_sightings else f"Recent rare sightings in Upper Manhattan (last 30 days):\n{rare_formatted}")
        )
    if parsed.get("response_type") == "weather":
        parsed["direct_answer"] = "Here's the birding weather forecast for this week in NYC:"
    if parsed.get("response_type") == "specific_park":
        park_data = _select_park(eda_results, user_query)
        if park_data:
            parsed["direct_answer"] = _build_specific_park_answer(park_data)
            parsed["top_10_chart_data"] = park_data.get("top_10_chart_data", [])
            parsed["rare_species_list"] = park_data.get("rare_species_list", [])
            parsed["top_park"] = park_data.get("park")
            sp_note, sp_best = _build_weather_note(weather, park_data.get("park"), date_filter)
            parsed["weather_note"] = sp_note
            parsed["best_day"] = sp_best
    elif parsed.get("response_type") == "recommendation" and parsed.get("top_park"):
        rec_note, rec_best = _build_weather_note(weather, parsed["top_park"], date_filter)
        parsed["weather_note"] = rec_note
        parsed["best_day"] = rec_best

        park_data = next(
            (p for p in (eda_results.get("parks_ranked") or []) if p.get("park") == parsed["top_park"]),
            None,
        )
        if park_data:
            detail_block = _build_specific_park_answer(park_data)
            existing = (parsed.get("direct_answer") or "").strip()
            parsed["direct_answer"] = (
                f"{existing}\n\nHere's what's been seen at {park_data.get('park')} recently:\n\n{detail_block}"
                if existing else detail_block
            )
            parsed["top_10_chart_data"] = park_data.get("top_10_chart_data", [])
            parsed["rare_species_list"] = park_data.get("rare_species_list", [])
    return parsed
