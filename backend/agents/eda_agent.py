import json
import pandas as pd
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage
from constants import GCP_PROJECT, GEMINI_MODEL, GCP_REGION

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

GENERIC_BIRD_TYPES = [
    "warbler", "hawk", "owl", "duck", "sparrow",
    "finch", "woodpecker", "thrush", "flycatcher",
    "vireo", "tanager", "heron", "egret", "gull",
    "tern", "sandpiper", "plover", "rail", "swift",
    "swallow", "wren", "nuthatch", "kinglet", "jay",
    "blackbird", "oriole", "grosbeak", "bunting",
    "towhee", "junco", "falcon", "eagle", "raptor",
]


SPECIES_QUERY_INTENT_WORDS = (
    "where", "see", "spot", "find", "watch", "sight", "bird", "species"
)


async def _detect_species_query(user_query: str, df: pd.DataFrame) -> str | None:
    if not user_query:
        return None
    query_lower = user_query.lower()

    rarity_ranking_markers = ("most rare", "rarity", "most unusual", "rarest")
    if any(m in query_lower for m in rarity_ranking_markers):
        return None

    for bird_type in GENERIC_BIRD_TYPES:
        if bird_type in query_lower:
            return bird_type

    all_species = df["comName"].str.lower().tolist()
    words = query_lower.split()
    for i in range(len(words)):
        if i + 2 < len(words):
            three = f"{words[i]} {words[i+1]} {words[i+2]}"
            if any(three in s for s in all_species):
                return three
        if i + 1 < len(words):
            two = f"{words[i]} {words[i+1]}"
            if any(two in s for s in all_species):
                return two

    if not any(w in query_lower for w in SPECIES_QUERY_INTENT_WORDS):
        return None

    try:
        llm = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_REGION)
        extract_response = await llm.ainvoke([
            HumanMessage(content=(
                "Extract the bird species name from this query. "
                "Return ONLY the bird name in lowercase, nothing else. "
                "If no bird is mentioned return 'none'.\n"
                f"Query: {user_query}"
            ))
        ])
        extracted = extract_response.content.strip().lower().strip(".'\"")
        if extracted and extracted != "none" and len(extracted) > 2:
            print(f"EDA: extracted species '{extracted}' from query via LLM")
            return extracted
    except Exception as e:
        print(f"EDA: LLM species extraction failed: {e}")
    return None


def _build_species_search_results(df: pd.DataFrame, species_query: str, all_park_names: list[str]) -> dict:
    mask = df["comName"].str.lower().str.contains(species_query, na=False)
    matching = df[mask].copy()
    is_generic = species_query in GENERIC_BIRD_TYPES
    if matching.empty:
        return {
            "searched_species": species_query,
            "is_generic_type": is_generic,
            "not_found": True,
            "found_in_parks": [],
            "not_found_in_parks": list(all_park_names),
            "total_individuals": 0,
            "total_unique_species": 0,
            "grouped_chart_data": [],
            "top_species_names": [],
            "park_totals": [],
        }

    matching["howMany"] = pd.to_numeric(
        matching["howMany"], errors="coerce"
    ).fillna(1)

    if is_generic:
        grouped = matching.groupby(["park_name", "comName"])["howMany"].sum().reset_index()
        grouped.columns = ["park", "species", "count"]

        top_species = (
            grouped.groupby("species")["count"].sum()
            .sort_values(ascending=False)
            .head(5)
            .index.tolist()
        )
        grouped_top = grouped[grouped["species"].isin(top_species)]

        parks_in_data = grouped_top["park"].unique().tolist()
        grouped_chart_data = []
        for park in parks_in_data:
            park_row = {"park": park}
            park_data = grouped_top[grouped_top["park"] == park]
            for species in top_species:
                species_row = park_data[park_data["species"] == species]
                park_row[species] = (
                    int(species_row["count"].sum()) if len(species_row) > 0 else 0
                )
            grouped_chart_data.append(park_row)

        park_totals = grouped.groupby("park").agg(
            total_count=("count", "sum"),
            unique_species=("species", "nunique"),
        ).reset_index().sort_values("total_count", ascending=False)

        found_in_parks = [
            {
                "park": row["park"],
                "sighting_count": int(row["total_count"]),
                "unique_species": int(row["unique_species"]),
                "species_list": grouped[grouped["park"] == row["park"]]
                    .sort_values("count", ascending=False)["species"]
                    .head(5)
                    .tolist(),
            }
            for _, row in park_totals.iterrows()
        ]

        found_parks = set(park_totals["park"].tolist())
        return {
            "searched_species": species_query,
            "is_generic_type": True,
            "top_species_names": top_species,
            "grouped_chart_data": grouped_chart_data,
            "park_totals": park_totals.to_dict("records"),
            "total_individuals": int(matching["howMany"].sum()),
            "total_unique_species": int(matching["comName"].nunique()),
            "found_in_parks": found_in_parks,
            "not_found_in_parks": [p for p in all_park_names if p not in found_parks],
        }

    hits = matching.groupby("park_name").agg(
        individuals_counted=("howMany", "sum"),
        report_count=("comName", "count"),
        unique_species=("comName", "nunique"),
        last_seen=("obsDt", "max"),
        species_list=("comName", lambda x: list(x.value_counts().head(5).index)),
    ).reset_index().sort_values("individuals_counted", ascending=False)
    found_parks = set(hits["park_name"].tolist())
    found_in_parks = [
        {
            "park": row["park_name"],
            "sighting_count": int(row["individuals_counted"]),
            "report_count": int(row["report_count"]),
            "unique_species": int(row["unique_species"]),
            "last_seen": str(row["last_seen"]),
            "top_species": list(row["species_list"]),
        }
        for _, row in hits.iterrows()
    ]
    return {
        "searched_species": species_query,
        "is_generic_type": False,
        "found_in_parks": found_in_parks,
        "not_found_in_parks": [p for p in all_park_names if p not in found_parks],
        "total_individuals": int(matching["howMany"].sum()),
        "total_unique_species": int(matching["comName"].nunique()),
        "grouped_chart_data": [],
        "top_species_names": [],
    }


async def run_eda(raw_sightings: list[dict], user_query: str = "") -> dict:
    if not raw_sightings:
        return {"parks_ranked": [], "total_unique_species_across_all_parks": 0,
                "most_notable_sighting": "No data", "chart_data": []}

    df = pd.DataFrame(raw_sightings)
    df["obsDt_raw"] = df["obsDt"].astype(str)
    df["obsDt"] = pd.to_datetime(df["obsDt"], errors="coerce")
    df["date"] = df["obsDt"].dt.date
    df["howMany"] = pd.to_numeric(df.get("howMany"), errors="coerce")
    if "obsReviewed" not in df.columns:
        df["obsReviewed"] = False
    if "subId" not in df.columns:
        df["subId"] = ""

    species_query = await _detect_species_query(user_query, df)
    species_search_results = None
    is_species_query = False
    if species_query:
        is_species_query = True
        all_park_names = df["park_name"].unique().tolist()
        species_search_results = _build_species_search_results(df, species_query, all_park_names)

    global_freq = df.groupby("comName").size()
    rare_threshold = 3
    rare_globally = set(global_freq[global_freq < rare_threshold].index)

    parks_summary = []
    for park, group in df.groupby("park_name"):
        total_sightings = len(group)
        species_agg = group.groupby("comName").agg(
            report_count=("comName", "count"),
            total_counted=("howMany", "sum"),
            max_seen=("howMany", "max"),
            last_seen=("obsDt", "max"),
            ever_reviewed=("obsReviewed", lambda x: bool(x.any())),
        ).reset_index()

        species_agg["total_counted"] = pd.to_numeric(
            species_agg["total_counted"], errors="coerce"
        ).fillna(species_agg["report_count"])
        species_agg = species_agg.sort_values("total_counted", ascending=False)

        species_count = int(species_agg["comName"].nunique())
        total_birds = int(species_agg["total_counted"].sum())
        total_checklists = int(group["subId"].nunique()) if "subId" in group.columns else 0

        top_10 = species_agg.head(10)
        top_10_chart_data = [
            {
                "species": row["comName"],
                "total_counted": int(row["total_counted"]),
                "report_count": int(row["report_count"]),
                "label": (
                    f"{row['comName']} "
                    f"({int(row['total_counted'])} birds, "
                    f"{int(row['report_count'])} reports)"
                ),
            }
            for _, row in top_10.iterrows()
        ]

        rare_mask = (species_agg["report_count"] <= 2) & (species_agg["total_counted"] <= 3)
        rare_species_df = species_agg[rare_mask].copy().sort_values(
            ["ever_reviewed", "total_counted"], ascending=[False, True]
        )
        rare_species_list = [
            {
                "name": row["comName"],
                "total_counted": int(row["total_counted"]),
                "report_count": int(row["report_count"]),
                "last_seen": str(row["last_seen"])[:10],
                "reviewed": bool(row["ever_reviewed"]),
            }
            for _, row in rare_species_df.head(4).iterrows()
        ]

        park_species = set(species_agg["comName"].tolist())
        rare_in_park_global = park_species.intersection(rare_globally)
        rarity_score = (
            round(len(rare_species_df) / len(species_agg) * 100, 1)
            if len(species_agg) > 0 else 0.0
        )
        peak_date = str(group.groupby("date").size().idxmax()) if not group.empty else ""
        short_name = park.replace("Central Park — ", "").replace(" Park", "")

        species_chart_data = [
            {"species": row["comName"], "count": int(row["report_count"])}
            for _, row in species_agg.head(15).iterrows()
        ]

        parks_summary.append({
            "park": park,
            "short_name": short_name,
            "species_count": species_count,
            "total_sightings": int(total_sightings),
            "total_birds_counted": total_birds,
            "total_checklists": total_checklists,
            "rarity_score": rarity_score,
            "notable_species": [r["name"] for r in rare_species_list],
            "species_chart_data": species_chart_data,
            "top_10_chart_data": top_10_chart_data,
            "rare_species_list": rare_species_list,
            "peak_date": peak_date,
        })

    parks_summary.sort(key=lambda x: x["species_count"], reverse=True)

    llm = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_REGION)
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
    raw = response.content
    print(f"eda_agent raw response: {raw!r}")
    text = raw.strip().removeprefix("```json").removesuffix("```").strip()

    summary_by_park = {p["park"]: p for p in parks_summary}

    def _merge_summary(ranked):
        for entry in ranked or []:
            src = summary_by_park.get(entry.get("park"))
            if not src:
                continue
            entry.setdefault("total_birds_counted", src["total_birds_counted"])
            entry.setdefault("total_checklists", src["total_checklists"])
            entry["top_10_chart_data"] = src["top_10_chart_data"]
            entry["rare_species_list"] = src["rare_species_list"]
        return ranked

    try:
        result = json.loads(text)
        result["parks_ranked"] = _merge_summary(result.get("parks_ranked", []))
        if species_search_results:
            result["species_search_results"] = species_search_results
        result["is_species_query"] = is_species_query
        return result
    except Exception as e:
        print(f"eda_agent JSON parse failed: {e}")
        chart_data = [
            {"park": p["park"], "species_count": p["species_count"]}
            for p in parks_summary
        ]
        total_unique = int(df["comName"].nunique())
        return {
            "parks_ranked": [
                {
                    "park": p["park"],
                    "species_count": p["species_count"],
                    "total_sightings": p["total_sightings"],
                    "total_birds_counted": p["total_birds_counted"],
                    "total_checklists": p["total_checklists"],
                    "rarity_score": p["rarity_score"],
                    "notable_species": p["notable_species"],
                    "top_10_chart_data": p["top_10_chart_data"],
                    "rare_species_list": p["rare_species_list"],
                    "peak_date": p["peak_date"],
                    "one_line_summary": "",
                }
                for p in parks_summary
            ],
            "total_unique_species_across_all_parks": total_unique,
            "most_notable_sighting": "",
            "chart_data": chart_data,
            "is_species_query": is_species_query,
            **({"species_search_results": species_search_results} if species_search_results else {}),
        }
