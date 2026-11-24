import csv
import json
import math
from collections import defaultdict
from datetime import datetime

# Load GTFS static files using standard csv (fast & lightweight for Vercel)
stops_list = []
stops_by_id = {}
with open("data/gtfs/stops.txt", mode="r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        s = {
            "stop_id": row["stop_id"],
            "stop_name": row["stop_name"],
            "stop_lat": float(row["stop_lat"]),
            "stop_lon": float(row["stop_lon"]),
        }
        stops_list.append(s)
        stops_by_id[s["stop_id"]] = s

routes_by_id = {}
with open("data/gtfs/routes.txt", mode="r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        routes_by_id[row["route_id"]] = row.get("route_short_name") or row["route_id"]

sample_trip_to_route = {}
with open("data/gtfs/trips.txt", mode="r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        r_id = row["route_id"]
        if r_id not in sample_trip_to_route.values():
            sample_trip_to_route[row["trip_id"]] = r_id

# Build route_stops[route_id] = sorted list of stop dicts
raw_route_stops = defaultdict(list)
with open("data/gtfs/stop_times_compact.csv", mode="r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        t_id = row["trip_id"]
        if t_id in sample_trip_to_route:
            r_id = sample_trip_to_route[t_id]
            s_info = stops_by_id.get(row["stop_id"])
            if s_info:
                raw_route_stops[r_id].append({
                    "stop_id": row["stop_id"],
                    "stop_sequence": int(row["stop_sequence"]),
                    "stop_name": s_info["stop_name"],
                    "stop_lat": s_info["stop_lat"],
                    "stop_lon": s_info["stop_lon"],
                })

route_stops = {}
stop_to_routes = defaultdict(list)
for r_id, seq_list in raw_route_stops.items():
    seq_list.sort(key=lambda x: x["stop_sequence"])
    route_stops[r_id] = seq_list
    for idx, item in enumerate(seq_list):
        stop_to_routes[item["stop_id"]].append((r_id, idx))

with open("speed_profiles.json", "r", encoding="utf-8") as f:
    speed_profiles = json.load(f)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def resolve_location(query_str):
    if "," in query_str:
        parts = query_str.split(",")
        return float(parts[0].strip()), float(parts[1].strip())
    q = query_str.lower()
    for s in stops_list:
        if q in s["stop_name"].lower():
            return s["stop_lat"], s["stop_lon"]
    raise ValueError(f"Stop not found: {query_str}")


def get_nearby_stops(lat, lon, radius_km=1.0):
    nearby = []
    for s in stops_list:
        d = haversine_km(lat, lon, s["stop_lat"], s["stop_lon"])
        if d <= radius_km:
            nearby.append((d, s))
    nearby.sort(key=lambda x: x[0])
    return nearby[:5]


def get_predicted_speed(route_id, is_weekend, hour):
    key = f"{route_id}|{int(is_weekend)}|{hour}"
    if key in speed_profiles:
        return speed_profiles[key]
    default_speed = 26.0 if (hour >= 22 or hour <= 5) else 16.0
    return speed_profiles.get("fallback_hourly", {}).get(str(hour), default_speed)


def plan_journeys(origin_str, dest_str, depart_iso):
    orig_lat, orig_lon = resolve_location(origin_str)
    dest_lat, dest_lon = resolve_location(dest_str)

    dt = datetime.fromisoformat(depart_iso)
    hour = dt.hour
    is_weekend = dt.weekday() >= 5

    orig_stops = get_nearby_stops(orig_lat, orig_lon)
    dest_stops = get_nearby_stops(dest_lat, dest_lon)

    options = []
    seen_routes = set()

    for o_dist, o_stop in orig_stops:
        o_routes = {r_id: idx for r_id, idx in stop_to_routes[o_stop["stop_id"]]}
        for d_dist, d_stop in dest_stops:
            for r_id, d_idx in stop_to_routes[d_stop["stop_id"]]:
                if r_id in o_routes and o_routes[r_id] < d_idx and r_id not in seen_routes:
                    seen_routes.add(r_id)
                    o_idx = o_routes[r_id]
                    seg = route_stops[r_id][o_idx : d_idx + 1]

                    road_km = 0.0
                    for i in range(len(seg) - 1):
                        road_km += haversine_km(
                            seg[i]["stop_lat"], seg[i]["stop_lon"],
                            seg[i + 1]["stop_lat"], seg[i + 1]["stop_lon"]
                        )
                    road_km = max(road_km, 0.5)

                    walk_to_min = round((o_dist / 5.0) * 60, 1)
                    walk_from_min = round((d_dist / 5.0) * 60, 1)

                    speed_now = get_predicted_speed(r_id, is_weekend, hour)
                    speed_quiet = get_predicted_speed(r_id, is_weekend, 23)

                    bus_time_min = round((road_km / speed_now) * 60, 1)
                    quiet_bus_min = round((road_km / speed_quiet) * 60, 1)
                    total_min = round(walk_to_min + bus_time_min + walk_from_min, 1)
                    quiet_total_min = round(walk_to_min + quiet_bus_min + walk_from_min, 1)

                    options.append({
                        "route": str(routes_by_id.get(r_id, r_id)),
                        "boarding_stop": o_stop["stop_name"],
                        "alighting_stop": d_stop["stop_name"],
                        "walk_to_stop_min": walk_to_min,
                        "bus_ride_min": bus_time_min,
                        "walk_to_dest_min": walk_from_min,
                        "total_time_min": total_min,
                        "quiet_hour_total_min": quiet_total_min,
                        "predicted_speed_kmph": speed_now,
                        "transfers": 0,
                    })

    options.sort(key=lambda x: x["total_time_min"])
    return options[:3]