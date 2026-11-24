import sqlite3
import glob
import json
import pandas as pd

def build_profiles():
    db_files = glob.glob("Data/Historical/*.db")
    all_grouped = []

    for db in db_files:
        print(f"Sampling {db}...")
        conn = sqlite3.connect(db)
        try:
            table_name = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0]
            
            # Sample 500,000 rows per day so it finishes in ~2 seconds instead of scanning 30M rows
            query = f"""
            SELECT 
                route_id,
                CAST(strftime('%w', timestamp, 'unixepoch', '+5 hours', '+30 minutes') AS INTEGER) IN (0, 6) AS is_weekend,
                CAST(strftime('%H', timestamp, 'unixepoch', '+5 hours', '+30 minutes') AS INTEGER) AS hour,
                AVG(speed) AS avg_speed,
                COUNT(*) AS cnt
            FROM (
                SELECT route_id, timestamp, speed 
                FROM {table_name} 
                WHERE speed >= 0 AND speed <= 70
                LIMIT 500000
            )
            GROUP BY route_id, is_weekend, hour
            """
            df = pd.read_sql_query(query, conn)
            all_grouped.append(df)
        except Exception as e:
            print(f"Skipping {db}: {e}")
        finally:
            conn.close()

    if not all_grouped:
        print("No data loaded.")
        return

    combined = pd.concat(all_grouped, ignore_index=True)
    combined['weighted_speed'] = combined['avg_speed'] * combined['cnt']

    final = combined.groupby(['route_id', 'is_weekend', 'hour']).agg(
        total_weighted=('weighted_speed', 'sum'),
        total_cnt=('cnt', 'sum')
    ).reset_index()
    final['speed'] = final['total_weighted'] / final['total_cnt']

    profiles = {}
    for _, row in final.iterrows():
        key = f"{row['route_id']}|{int(row['is_weekend'])}|{int(row['hour'])}"
        profiles[key] = max(round(float(row['speed']), 2), 8.0)

    hourly_fallback = final.groupby('hour')['speed'].mean().to_dict()
    profiles['fallback_hourly'] = {str(k): max(round(float(v), 2), 10.0) for k, v in hourly_fallback.items()}

    with open("speed_profiles.json", "w") as f:
        json.dump(profiles, f)
    print("Saved speed_profiles.json successfully!")

if __name__ == "__main__":
    build_profiles()