import requests
import time
import json
from datetime import datetime

# ============================================================
#  CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = "8621167866:AAEzwgq2nQiBjKftLmxbjqUgcZal-dKssMQ"
TELEGRAM_CHAT_ID = "7411656885"

COOKIE = "conveyor_session_id=CONVEYOR_27170_be9360b41089014a3669fc1b701b4e217442694e57e1e9395c8751912a18c861"
AUTHOR_ID = "27170"

CHECK_INTERVAL = 60  # secondes

# ============================================================
#  ZONES A SURVEILLER
# ============================================================

ZONES = [
    {
        "name": "Paris / Ile-de-France",
        "region_end": "Ile-de-france",
        "active_always": True,
        "min_distance_km": 200,  # missions >= 200 km uniquement
    },
    {
        "name": "Toulouse",
        "region_start": "occitanie",
        "active_until": "2026-03-22",
        "date_filter": "20260320",  # uniquement le 20/03/2026
    },
]

# ============================================================
#  FONCTIONS
# ============================================================

seen_mission_ids = set()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def build_url(zone):
    base = "https://partenaire.expedicar.com/api/getJourneysOpenToConveyorBooking/"
    params = {
        "order_by": "date_end",
        "sort": "asc",
        "omnisearch": "",
        "id_conveyor": AUTHOR_ID,
        "with_tag": "1",
        "limit": "0,50",
        "extra_info": "tableJourneyList_1",
    }
    if "region_end" in zone:
        params["region_end"] = zone["region_end"]
    if "region_start" in zone:
        params["department_start"] = zone["region_start"]
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base}?{query}"


def fetch_missions(zone):
    url = build_url(zone)
    headers = {
        "Cookie": COOKIE,
        "Author-Id": AUTHOR_ID,
        "Author-Type": "conveyor",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://partenaire.expedicar.com/journey/list",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            print(f"[WARN] Reponse non-JSON pour {zone['name']} — session expiree ?")
            return None
    except Exception as e:
        print(f"[FETCH ERROR] {zone['name']} : {e}")
        return None


def is_zone_active(zone):
    if zone.get("active_always"):
        return True
    if "active_until" in zone:
        today = datetime.now().strftime("%Y-%m-%d")
        return today <= zone["active_until"]
    return True


def format_mission(mission):
    try:
        stations = mission.get("stations", {})
        depart = stations.get("start", {}).get("address", {}).get("city", "?").title()
        arrivee = stations.get("end", {}).get("address", {}).get("city", "?").title()
        date_raw = mission.get("dates", {}).get("start", "")
        if date_raw and len(date_raw) >= 8:
            date = f"{date_raw[6:8]}/{date_raw[4:6]}/{date_raw[0:4]}"
        else:
            date = "?"
        distance = mission.get("distance_km", "?")
        return f"{depart} -> {arrivee} | {date} | {distance} km"
    except Exception:
        return "Nouvelle mission disponible !"


def check_all_zones():
    global seen_mission_ids
    new_found = 0

    for zone in ZONES:
        if not is_zone_active(zone):
            print(f"[SKIP] Zone {zone['name']} inactive")
            continue

        print(f"[CHECK] {zone['name']} a {datetime.now().strftime('%H:%M:%S')}")
        data = fetch_missions(zone)
        if not data:
            continue

        # Structure reelle de l'API : data["response"]["journeys"]
        missions = []
        if isinstance(data, dict) and "response" in data:
            missions = data["response"].get("journeys", [])
        elif isinstance(data, list):
            missions = data

        print(f"  -> {len(missions)} mission(s) trouvee(s)")

        for mission in missions:
            mid = str(mission.get("id_journey") or "")
            if not mid or mid in seen_mission_ids:
                continue

            distance = int(mission.get("distance_km") or 0)
            date_start = mission.get("dates", {}).get("start", "")

            # Filtre IDF : >= 200 km
            if "min_distance_km" in zone:
                if distance < zone["min_distance_km"]:
                    print(f"  [SKIP] #{mid} : {distance} km < {zone['min_distance_km']} km")
                    continue

            # Filtre date (ex: Toulouse le 20/03)
            if "date_filter" in zone:
                if not date_start.startswith(zone["date_filter"]):
                    print(f"  [SKIP] #{mid} : pas le bon jour")
                    continue

            seen_mission_ids.add(mid)
            msg = format_mission(mission)
            msg += f"\nZone : {zone['name']}"
            send_telegram(msg)
            print(f"  OK Notif envoyee pour mission #{mid} ({distance} km)")
            new_found += 1

    if new_found == 0:
        print("  Aucune nouvelle mission.")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    print("Hiflow Monitor demarre !")
    print(f"Verification toutes les {CHECK_INTERVAL} secondes")
    send_telegram("Hiflow Monitor demarre !\nJe surveille les nouvelles missions et t'enverrai une notification des qu'une apparait.\n- IDF : missions >= 200 km\n- Toulouse : missions du 20/03/2026")

    while True:
        try:
            check_all_zones()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)
