import httpx
from constants import EBIRD_KEY, EBIRD_DAYS

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
