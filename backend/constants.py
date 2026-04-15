import os
from dotenv import load_dotenv

load_dotenv()

HOTSPOTS = {
    # Manhattan
    "Central Park — The Ramble":  "L109518", 
    "Inwood Hill Park":           "L684740",  
    "Fort Tryon Park":            "L591127", 
    "Morningside Park":           "L1799559",
    "Central Park — Reservoir":   "L191107", 
    # Brooklyn
    "Prospect Park":              "L109516",
    "Green-Wood Cemetery":        "L285884",
    # Midtown
    "Bryant Park":                "L683555", 
}
EBIRD_KEY = os.getenv("EBIRD_API_KEY")
GCP_PROJECT = "hong-agentic-ai-p1"
GEMINI_MODEL = "gemini-2.0-flash-001"
EBIRD_DAYS = 30
GCP_REGION = "us-central1"

HOTSPOT_COORDS = {
    "Central Park — The Ramble": (40.7761, -73.9700),
    "Central Park — Reservoir":  (40.7857, -73.9623),
    "Inwood Hill Park":          (40.8718, -73.9235),
    "Fort Tryon Park":           (40.8619, -73.9322),
    "Morningside Park":          (40.8042, -73.9591),
    "Prospect Park":             (40.6602, -73.9690),
    "Green-Wood Cemetery":       (40.6527, -73.9913),
    "Bryant Park":               (40.7536, -73.9832),
}
