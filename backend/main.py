import re
from datetime import datetime, timedelta
import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from graph import build_graph
from constants import GCP_PROJECT, GEMINI_MODEL


def _range(start, end):
    out = []
    d = start
    while d <= end:
        out.append(str(d))
        d += timedelta(days=1)
    return out


def parse_date_filter(query: str) -> dict:
    nyc_tz = pytz.timezone("America/New_York")
    today = datetime.now(nyc_tz).date()
    query_lower = query.lower()

    def result(mode, dates, label, focus):
        return {"mode": mode, "dates": dates, "label": label, "focus": focus}

    m = re.search(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s*'
        r'(?:-|–|to)+\s*(?:[a-z]*\s+)?(\d{1,2})',
        query_lower,
    )
    if m:
        month_str = m.group(1)[:3].capitalize()
        start_d, end_d = int(m.group(2)), int(m.group(3))
        try:
            start = datetime.strptime(
                f"{month_str} {start_d} {today.year}", "%b %d %Y"
            ).date()
            end = datetime.strptime(
                f"{month_str} {end_d} {today.year}", "%b %d %Y"
            ).date()
            return result(
                "date_range", _range(start, end),
                f"{start.strftime('%b %d')} – {end.strftime('%b %d')}",
                "specific",
            )
        except Exception:
            pass

    m = re.search(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b',
        query_lower,
    )
    if m:
        try:
            month_str = m.group(1)[:3].capitalize()
            d = datetime.strptime(
                f"{month_str} {int(m.group(2))} {today.year}", "%b %d %Y"
            ).date()
            return result("single_day", [str(d)], d.strftime("%B %d"), "specific")
        except Exception:
            pass

    if re.search(r'\d{1,2}/\d{1,2}', query_lower):
        matches = re.findall(r'(\d{1,2})/(\d{1,2})', query_lower)
        try:
            if len(matches) == 2:
                start = datetime(today.year, int(matches[0][0]), int(matches[0][1])).date()
                end = datetime(today.year, int(matches[1][0]), int(matches[1][1])).date()
                return result(
                    "date_range", _range(start, end),
                    f"{start.strftime('%b %d')} – {end.strftime('%b %d')}",
                    "specific",
                )
            if len(matches) == 1:
                d = datetime(today.year, int(matches[0][0]), int(matches[0][1])).date()
                return result("single_day", [str(d)], d.strftime("%B %d"), "specific")
        except Exception:
            pass

    if "tomorrow" in query_lower:
        d = today + timedelta(days=1)
        return result("single_day", [str(d)], "tomorrow", "specific")

    if re.search(r'\btoday\b', query_lower):
        return result("single_day", [str(today)], "today", "specific")

    if "next weekend" in query_lower:
        days_to_sat = (5 - today.weekday()) % 7
        sat = today + timedelta(days=days_to_sat + 7)
        return result(
            "named_period", [str(sat), str(sat + timedelta(days=1))],
            "next weekend", "specific",
        )

    if "this weekend" in query_lower:
        days_to_sat = (5 - today.weekday()) % 7
        if days_to_sat == 0:
            days_to_sat = 7
        sat = today + timedelta(days=days_to_sat)
        return result(
            "named_period", [str(sat), str(sat + timedelta(days=1))],
            "this weekend", "specific",
        )

    if "next week" in query_lower:
        days_to_mon = (7 - today.weekday()) % 7
        if days_to_mon == 0:
            days_to_mon = 7
        mon = today + timedelta(days=days_to_mon)
        dates = [str(mon + timedelta(days=i)) for i in range(7)]
        return result("named_period", dates, "next week", "specific")

    if "this week" in query_lower:
        sunday = today + timedelta(days=(6 - today.weekday()) % 7)
        return result("named_period", _range(today, sunday), "this week", "specific")

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(day_names):
        if f"next {day}" in query_lower:
            days_ahead = (i - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            d = today + timedelta(days=days_ahead)
            return result("single_day", [str(d)], f"next {day.capitalize()}", "specific")
        if f"this {day}" in query_lower:
            days_ahead = (i - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            d = today + timedelta(days=days_ahead)
            return result("single_day", [str(d)], f"this {day.capitalize()}", "specific")

    return {"mode": "full_forecast", "dates": [], "label": "", "focus": "general"}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*", "https://hong-agentic-ai-p1.web.app", "https://hong-agentic-ai-p1.firebaseapp.com"],
                   allow_methods=["*"], allow_headers=["*"])
graph = build_graph()

class QueryRequest(BaseModel):
    query: str

BIRDING_KEYWORDS = [
    "bird", "birding", "birder", "species",
    "wildlife", "migration", "nest",
    "flock", "feather", "beak",
    "ramble", "inwood", "morningside", "tryon", "prospect",
    "greenwood", "reservoir", "bryant",
    "warbler", "hawk", "eagle", "owl", "falcon",
    "heron", "duck", "goose", "sparrow", "finch",
    "robin", "crow", "pigeon", "woodpecker", "swift",
    "swallow", "thrush", "vireo", "tanager", "oriole",
    "bunting", "grosbeak", "flycatcher", "kingfisher",
    "jay", "wren", "nuthatch", "creeper", "kinglet",
    "waxwing", "starling", "blackbird", "grackle",
    "towhee", "junco", "redpoll", "siskin", "crossbill",
    "merlin", "kestrel", "osprey", "vulture", "ibis",
    "egret", "cormorant", "gannet", "tern", "gull",
    "plover", "sandpiper", "snipe", "rail", "coot",
    "loon", "grebe", "teal", "wigeon", "pintail",
    "shoveler", "scaup", "scoter", "bufflehead",
    "goldeneye", "merganser", "canvasback", "redhead",
]

FICTIONAL_TERMS = [
    "dragon", "unicorn", "dinosaur", "phoenix",
    "griffin", "mermaid", "elf", "wizard",
    "vampire", "zombie", "alien", "robot",
    "pokemon", "pikachu", "charizard",
]

VALID_PARKS = [
    "Central Park — The Ramble",
    "Central Park — North End",
    "Central Park — Reservoir",
    "Inwood Hill Park",
    "Riverside Park",
    "Fort Tryon Park",
    "Morningside Park",
    "Bryant Park",
    "Prospect Park",
    "Green-Wood Cemetery",
]


def build_oos_response(message: str) -> dict:
    return {
        "response_type": "off_topic",
        "direct_answer": message,
        "top_park": None,
        "best_day": None,
        "reason": "",
        "species_highlights": [],
        "species_chart_data": [],
        "weather_note": None,
        "rankings": [],
        "chart_data": [],
    }


async def classify_query(query: str) -> str:
    """LLM classifier returning one of: BIRDING, PROFANE, VIOLENT, OFFTOPIC."""
    try:
        llm = ChatVertexAI(
            model=GEMINI_MODEL, project=GCP_PROJECT, location="us-central1"
        )
        response = await llm.ainvoke([
            HumanMessage(content=(
                "Analyze this user query and respond with exactly one word:\n\n"
                "BIRDING - if it's about birds, birding, or NYC parks\n"
                "PROFANE - if it contains profanity or offensive language\n"
                "VIOLENT - if it expresses intent to harm birds or animals\n"
                "OFFTOPIC - if it's unrelated to birding\n\n"
                f"Query: {query}\n\n"
                "Respond with exactly one word only."
            ))
        ])
        label = response.content.strip().upper().split()[0] if response.content.strip() else "BIRDING"
        label = re.sub(r"[^A-Z]", "", label)
        if label in {"BIRDING", "PROFANE", "VIOLENT", "OFFTOPIC"}:
            return label
        return "BIRDING"
    except Exception as e:
        print(f"LLM classify failed: {e}")
        return "BIRDING"


def validate_hypothesis_output(hypothesis: dict, raw_sightings: list) -> dict:
    real_species = set()
    if raw_sightings:
        for s in raw_sightings:
            name = s.get("comName", "")
            if name:
                real_species.add(name.lower())

    if hypothesis.get("species_highlights"):
        validated_highlights = []
        for species in hypothesis["species_highlights"]:
            if species.lower() in real_species or len(real_species) == 0:
                validated_highlights.append(species)
            else:
                print(
                    f"VALIDATION: removed hallucinated species '{species}' "
                    "not in data"
                )
        hypothesis["species_highlights"] = validated_highlights

    if hypothesis.get("top_park") and hypothesis["top_park"] not in VALID_PARKS:
        print(
            f"VALIDATION: invalid park name '{hypothesis['top_park']}' — clearing"
        )
        hypothesis["top_park"] = None

    required_fields = [
        "response_type", "direct_answer",
        "top_park", "best_day", "reason",
        "species_highlights", "species_chart_data",
        "weather_note", "rankings", "chart_data",
    ]
    list_fields = {"species_highlights", "species_chart_data", "rankings", "chart_data"}
    none_fields = {"top_park", "best_day", "weather_note"}
    str_fields = {"direct_answer", "reason", "response_type"}
    for field in required_fields:
        if field not in hypothesis:
            if field in list_fields:
                hypothesis[field] = []
            elif field in none_fields:
                hypothesis[field] = None
            elif field in str_fields:
                hypothesis[field] = ""
            else:
                hypothesis[field] = None

    return hypothesis


@app.get("/health")
def health():
    return {"status": "NYC Bird Analyst running"}



# NEGATIVE CONTROLS — things this assistant must NOT do.
# Enforced by oos_backstop (pre-LLM) and post_llm_backstop (post-LLM).
# 1. Must NOT answer non-birding questions (food, shopping, directions,politics, finance, general trivia, etc.).
# 2. Must NOT recommend a park, species, or weather day for off-topic queries.
# 3. Must NOT invent bird species that are not present in the raw eBird data.
# 4. Must NOT name parks outside the VALID_PARKS allow-list.
# 5. Must NOT answer about fictional creatures (dragon, pokemon, unicorn…).
# 6. Must NOT return a confident recommendation when the user's query slipped past the pre-LLM gate but the model produced no grounded evidence.
# 7. Must NOT answer violent / hunting / killing intents targeting birds ("kill", "shoot", "hunt", "poison", "trap"...).
# 8. Must NOT answer consumption intents ("eat", "cook", "recipe"...).
# 9. Must NOT engage with profanity or curse words.
# 10. Must NOT answer nonsense / repeated-token queries ("bird bird bird").


OOS_HELP_MESSAGE = (
    "I'm Pidgey AI, your NYC birding expert! "
    "I only answer questions about birds, birding, and NYC parks. "
    "Here's what I can help with:\n"
    "• 'Best park for birding this weekend?'\n"
    "• 'Where can I see a Bald Eagle in NYC?'\n"
    "• 'Which park has the most warblers?'\n"
    "• 'What birds are at Prospect Park?'"
)


NONSENSE_PATTERNS = [
    r"^\s*(\w+)(\s+\1){1,}\s*[\?\.!]*\s*$",  # "booby booby", "bird bird bird"
]

REFUSAL_VIOLENCE = (
    "I'm all about appreciating birds, not harming them! 🐦 "
    "Try asking me about spotting them instead."
)

REFUSAL_PROFANITY = (
    "Let's keep it friendly! 🐦 I'm here to help with NYC birding. "
    "Try asking about the best park for birding this weekend."
)

REFUSAL_NONSENSE = (
    "I didn't catch a clear question there. "
    "Try something like: 'Best park for birding this weekend?' "
    "or 'Where can I see a Bald Eagle in NYC?'"
)


def check_nonsense(query: str) -> dict | None:
    """Cheap pre-LLM check for nonsense repetition (e.g. 'booby booby')."""
    q = (query or "").lower().strip()
    for pattern in NONSENSE_PATTERNS:
        if re.match(pattern, q):
            return build_oos_response(REFUSAL_NONSENSE)
    return None


KNOWN_PARK_TOKENS = [
    "ramble", "reservoir", "inwood", "fort tryon", "tryon",
    "morningside", "prospect", "green-wood", "greenwood",
    "green wood", "bryant", "central park",
]

UNKNOWN_PARK_MESSAGE = (
    "I love birding but haven't been there just yet, will let you know after I visit!"
)


GENERIC_PARK_MODIFIERS = {
    "best", "a", "an", "the", "any", "which", "what", "some",
    "this", "that", "every", "favorite", "favourite", "good",
    "great", "nearest", "closest", "local", "nearby", "top",
    "better", "recommended", "my", "your", "our", "city",
    "state", "national", "manhattan", "brooklyn", "queens",
    "bronx", "nyc", "new", "york", "to", "for", "at", "in",
    "of", "on", "no", "other", "another", "each",
}


def check_unknown_park_query(query: str) -> dict | None:
    """If the user names a SPECIFIC park/cemetery/garden that is not in our
    hotspot list, return the friendly 'haven't been there yet' response.

    Generic references like 'best park', 'any park', 'which park' must NOT
    trigger this — the user is asking our system to pick, which is in scope.
    Only proper-noun-style names (e.g. 'Madison Square Park') fire it.
    """
    q = (query or "").lower()
    if any(tok in q for tok in KNOWN_PARK_TOKENS):
        return None
    matches = re.findall(
        r"\b([a-z][a-z\-'\.]+(?:\s+[a-z][a-z\-'\.]+){0,3})\s+(park|cemetery|garden|gardens)\b",
        q,
    )
    for name, _ in matches:
        tokens = name.split()
        if any(t not in GENERIC_PARK_MODIFIERS for t in tokens):
            return build_oos_response(UNKNOWN_PARK_MESSAGE)
    return None


async def oos_backstop(query: str) -> dict | None:
    """Out-of-scope backstop. Single chokepoint that catches any query not
    about birds/birding/NYC parks and returns a canned OOS response.

    Three layers, in order:
      1. Length guard — too-short or empty queries.
      2. Fictional-term deny-list — dragons, pokemon, etc.
      3. Topic classifier — strong birding keywords allow-list; anything
         that misses the allow-list is sent to a Gemini yes/no classifier
         as the final safety net.

    Returns the OOS response dict if the query is out of scope, else None
    (meaning the caller should proceed with the normal pipeline).
    """
    q = (query or "").lower().strip()

    if len(q) < 3:
        return build_oos_response(
            "Great question for a birder! I specialize in birds and birding "
            "across NYC parks. For example, try: "
            "'Best park for birding this weekend?'"
        )

    if any(term in q for term in FICTIONAL_TERMS):
        return build_oos_response(
            "I specialize in real NYC birds! Try: "
            "'What birds can I see in Prospect Park?' "
            "or 'Where can I see a Bald Eagle in NYC?'"
        )

    nonsense = check_nonsense(query)
    if nonsense is not None:
        return nonsense

    unknown_park = check_unknown_park_query(query)
    if unknown_park is not None:
        return unknown_park

    label = await classify_query(query)
    if label == "PROFANE":
        return build_oos_response(REFUSAL_PROFANITY)
    if label == "VIOLENT":
        return build_oos_response(REFUSAL_VIOLENCE)
    if label == "OFFTOPIC":
        return build_oos_response(OOS_HELP_MESSAGE)
    return None


def post_llm_backstop(query: str, hypothesis: dict, raw_sightings: list) -> dict:
    """Post-LLM OOS backstop. Second line of defense that inspects the
    generated hypothesis and overrides it with an OOS response if any
    NEGATIVE CONTROL is violated:

      - top_park is set but is not in VALID_PARKS (hallucinated park).
      - Hypothesis claims species highlights but there is zero eBird data
        backing them (hallucinated recommendation on an empty pipeline).
      - Query contains no birding signal AND the pipeline returned no
        sightings — treat as a query that slipped past the pre-LLM gate.
    Returns a safe hypothesis dict (either the original or an OOS response).
    """
    q = (query or "").lower()

    top_park = hypothesis.get("top_park")
    if top_park and top_park not in VALID_PARKS:
        print(f"POST-LLM BACKSTOP: invalid park '{top_park}' — returning OOS")
        return build_oos_response(OOS_HELP_MESSAGE)

    strong_birding_hit = any(kw in q for kw in BIRDING_KEYWORDS)
    pipeline_empty = not raw_sightings
    claims_recommendation = bool(top_park) or bool(hypothesis.get("species_highlights"))

    if pipeline_empty and claims_recommendation and not strong_birding_hit:
        print("POST-LLM BACKSTOP: recommendation on empty pipeline with no birding signal — returning OOS")
        return build_oos_response(OOS_HELP_MESSAGE)

    if any(term in q for term in FICTIONAL_TERMS):
        print("POST-LLM BACKSTOP: fictional term leaked past pre-LLM gate — returning OOS")
        return build_oos_response(OOS_HELP_MESSAGE)

    return hypothesis


@app.post("/analyze")
async def analyze(request: QueryRequest):
    oos = await oos_backstop(request.query)
    if oos is not None:
        return oos

    date_filter = parse_date_filter(request.query)
    result = await graph.ainvoke({
        "user_query": request.query,
        "date_filter": date_filter,
    })
    hypothesis = result.get("hypothesis", {})
    raw_sightings = result.get("raw_sightings", [])
    hypothesis = validate_hypothesis_output(hypothesis, raw_sightings)
    hypothesis = post_llm_backstop(request.query, hypothesis, raw_sightings)
    return hypothesis
