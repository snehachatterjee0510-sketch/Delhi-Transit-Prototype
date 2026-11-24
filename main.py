from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from planner import plan_journeys

app = FastAPI(title="Delhi Bus Traffic & Journey Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_ui():
    return FileResponse("index.html")

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