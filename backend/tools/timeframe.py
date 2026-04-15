from datetime import date, timedelta


def parse_timeframe(query: str, today: date | None = None) -> dict:
    q = (query or "").lower()
    today = today or date.today()

    extended = any(
        k in q for k in ["16 day", "16-day", "two week", "2 week", "next two",
                         "extended", "long-range", "long range", "full forecast"]
    )

    weekend = any(k in q for k in ["weekend", "saturday", "sunday", "sat ", " sat", "sun "])
    this_week = "this week" in q or "next 7" in q or "seven day" in q

    if extended:
        kind, days, label = "extended", 16, "next 16 days"
    elif weekend:
        kind, days, label = "weekend", 7, "this weekend"
    elif this_week:
        kind, days, label = "week", 7, "this week"
    else:
        kind, days, label = "week", 7, "this week"

    allowed_dates: set[str] | None = None
    if kind == "weekend":
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0 and today.weekday() == 6:
            days_until_sat = 6
        sat = today + timedelta(days=days_until_sat)
        sun = sat + timedelta(days=1)
        allowed_dates = {sat.isoformat(), sun.isoformat()}

    return {
        "kind": kind,
        "days": days,
        "label": label,
        "allowed_dates": sorted(allowed_dates) if allowed_dates else None,
    }
