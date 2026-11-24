import json
import math
import pandas as pd
from datetime import datetime


stops_df = pd.read_csv("Data/gtfs/stops.txt")
routes_df = pd.read_csv("Data/gtfs/routes.txt")
trips_df = pd.read_csv("Data/gtfs/trips.txt")
stop_times_df = pd.read_csv("Data/gtfs/stop_times_compact.csv")

with open("speed_profiles.json", "r") as f:
    speed_profiles = json.load(f)


sample_trips = trips_df.drop_duplicates(subset=['route_id'])[['route_id', 'trip_id']]
route_stops = pd.merge(sample_trips, stop_times_df, on='trip_id').sort_values(['route_id', 'stop_sequence'])
route_stops = pd.merge(route_stops, stops_df[['stop_id', 'stop_name', 'stop_lat', 'stop_lon']], on='stop_id')

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def resolve_location(query_str):
    if "," in query_str:
        parts = query_str.split(",")
        return float(parts[0].strip()), float(parts[1].strip())
    matches = stops_df[stops_df['stop_name'].str.contains(query_str, case=False, na=False)]
    if matches.empty:
        raise ValueError(f"Stop not found: {query_str}")
    row = matches.iloc[0]
    return float(row['stop_lat']), float(row['stop_lon'])

def get_nearby_stops(lat, lon, radius_km=1.0):
    stops_copy = stops_df.copy()
    stops_copy['dist_km'] = stops_copy.apply(
        lambda r: haversine_km(lat, lon, r['stop_lat'], r['stop_lon']), axis=1
    )
    return stops_copy[stops_copy['dist_km'] <= radius_km].sort_values('dist_km').head(5)

def get_predicted_speed(route_id, is_weekend, hour):
    key = f"{route_id}|{int(is_weekend)}|{hour}"
    if key in speed_profiles:
        return speed_profiles[key]
    # Realistic fallback: 26 km/h at night (11 PM - 5 AM), 16 km/h during daytime traffic
    default_speed = 26.0 if (hour >= 22 or hour <= 5) else 16.0
    return speed_profiles.get('fallback_hourly', {}).get(str(hour), default_speed)

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

    for _, o_stop in orig_stops.iterrows():
        for _, d_stop in dest_stops.iterrows():
            o_routes = route_stops[route_stops['stop_id'] == o_stop['stop_id']]
            d_routes = route_stops[route_stops['stop_id'] == d_stop['stop_id']]
            common = pd.merge(o_routes, d_routes, on='route_id', suffixes=('_o', '_d'))
            valid = common[common['stop_sequence_o'] < common['stop_sequence_d']]

            for _, match in valid.iterrows():
                r_id = match['route_id']
                if r_id in seen_routes:
                    continue
                seen_routes.add(r_id)

                seg = route_stops[
                    (route_stops['route_id'] == r_id) &
                    (route_stops['stop_sequence'] >= match['stop_sequence_o']) &
                    (route_stops['stop_sequence'] <= match['stop_sequence_d'])
                ]
                road_km = 0.0
                coords = list(zip(seg['stop_lat'], seg['stop_lon']))
                for i in range(len(coords) - 1):
                    road_km += haversine_km(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
                road_km = max(road_km, 0.5)

                
                walk_to_min = round((o_stop['dist_km'] / 5.0) * 60, 1)
                walk_from_min = round((d_stop['dist_km'] / 5.0) * 60, 1)

                
                speed_now = get_predicted_speed(r_id, is_weekend, hour)
                speed_quiet = get_predicted_speed(r_id, is_weekend, 23)

                bus_time_min = round((road_km / speed_now) * 60, 1)
                quiet_bus_min = round((road_km / speed_quiet) * 60, 1)
                total_min = round(walk_to_min + bus_time_min + walk_from_min, 1)
                quiet_total_min = round(walk_to_min + quiet_bus_min + walk_from_min, 1)

                route_name = routes_df[routes_df['route_id'] == r_id]['route_short_name'].values
                r_label = str(route_name[0]) if len(route_name) > 0 else str(r_id)

                options.append({
                    "route": r_label,
                    "boarding_stop": o_stop['stop_name'],
                    "alighting_stop": d_stop['stop_name'],
                    "walk_to_stop_min": walk_to_min,
                    "bus_ride_min": bus_time_min,
                    "walk_to_dest_min": walk_from_min,
                    "total_time_min": total_min,
                    "quiet_hour_total_min": quiet_total_min,
                    "predicted_speed_kmph": speed_now,
                    "transfers": 0
                })

    options.sort(key=lambda x: x['total_time_min'])
    return options[:3]
print(plan_journeys("Rohini Sec 22 Terminal","Rithala Village","2026-11-24T08:00:00"))