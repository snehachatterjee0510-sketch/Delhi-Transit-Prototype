import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from planner import plan_journeys, stops_list

app = FastAPI(title="Delhi Bus Traffic & Journey Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    html_path = os.path.join(BASE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/stops")
def search_stops(q: str = Query("", description="Partial stop name")):
    query = q.strip().lower()
    if len(query) < 2:
        return []
    seen = set()
    matches = []
    for s in stops_list:
        name = s["stop_name"]
        if query in name.lower() and name not in seen:
            seen.add(name)
            matches.append(name)
            if len(matches) >= 15:
                break
    return matches

@app.get("/journeys")
def get_journeys(
    from_loc: str = Query(..., alias="from", description="Origin stop name or lat,lon"),
    to_loc: str = Query(..., alias="to", description="Destination stop name or lat,lon"),
    depart: str = Query(..., description="ISO timestamp e.g. 2026-10-15T08:30:00")
):
    try:
        results = plan_journeys(from_loc, to_loc, depart)
        return {
            "origin": from_loc,
            "destination": to_loc,
            "departure": depart,
            "journey_options": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))