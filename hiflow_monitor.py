import requests
import time
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup

# ============================================================
#  CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = "8621167866:AAEzwgq2nQiBjKftLmxbjqUgcZal-dKssMQ"
TELEGRAM_CHAT_ID = "-5099081999"

HIFLOW_COOKIE = os.environ.get("HIFLOW_COOKIE", "")
HIFLOW_AUTHOR_ID = "27170"

CHECK_INTERVAL = 60

ZONES = [
    {"name": "IDF Depart", "region_start": "Ile-de-france", "active_always": True, "min_distance_km": 200},
    {"name": "IDF Arrivee", "region_end": "Ile-de-france", "active_always": True, "min_distance_km": 200},
    {"name": "Oise Depart", "department_start": "60", "active_always": True, "min_distance_km": 200},
    {"name": "Oise Arrivee", "department_end": "60", "active_always": True, "min_distance_km": 200},
]

seen_hiflow_ids = set()
cookie_expired_notif_sent = False


# ============================================================
#  TELEGRAM
# ============================================================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


# ============================================================
#  HIFLOW
# ============================================================

def build_hiflow_url(zone):
    base = "https://partenaire.expedicar.com/api/getJourneysOpenToConveyorBooking/"
    params = {
        "order_by": "date_end", "sort": "asc", "omnisearch": "",
        "id_conveyor": HIFLOW_AUTHOR_ID, "with_tag": "1",
        "limit": "0,50", "extra_info": "tableJourneyList_1",
    }
    if "region_start" in zone: params["region_start"] = zone["region_start"]
    if "region_end" in zone: params["region_end"] = zone["region_end"]
    if "department_start" in zone: params["department_start"] = zone["department_start"]
    if "department_end" in zone: params["department_end"] = zone["department_end"]
    return f"{base}?" + "&".join(f"{k}={v}" for k, v in params.items())


def fetch_hiflow_missions(zone):
    global cookie_expired_notif_sent
    cookie = os.environ.get("HIFLOW_COOKIE", HIFLOW_COOKIE)
    if not cookie:
        print("[HIFLOW] Pas de cookie")
        return None
    headers = {
        "Cookie": cookie, "Author-Id": HIFLOW_AUTHOR_ID,
        "Author-Type": "conveyor",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://partenaire.expedicar.com/journey/list",
    }
    try:
        r = requests.get(build_hiflow_url(zone), headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "response" in data:
            cookie_expired_notif_sent = False
            return data
        else:
            raise ValueError("Reponse invalide")
    except Exception as e:
        print(f"[HIFLOW ERROR] {zone['name']} : {e}")
        if not cookie_expired_notif_sent:
            send_telegram("⚠️ Cookie Hiflow expiré ! Merci de le renouveler sur Railway → Variables → HIFLOW_COOKIE")
            cookie_expired_notif_sent = True
        return None


def format_hiflow_mission(mission):
    try:
        stations = mission.get("stations", {})
        depart = stations.get("start", {}).get("address", {}).get("city", "?").title()
        arrivee = stations.get("end", {}).get("address", {}).get("city", "?").title()
        date_raw = mission.get("dates", {}).get("start", "")
        date = f"{date_raw[6:8]}/{date_raw[4:6]}/{date_raw[0:4]}" if len(date_raw) >= 8 else "?"
        distance = mission.get("distance_km", "?")
        prix_instant = mission.get("pricing", {}).get("instant_booking_cost", None)
        prix_base = mission.get("pricing", {}).get("conveyor_price", "?")
        prix_str = f"{prix_instant} EUR" if prix_instant else f"{prix_base} EUR"
        return f"{depart} -> {arrivee} | {date} | {distance} km | {prix_str}"
    except:
        return "Nouvelle mission Hiflow disponible !"


def check_hiflow():
    global seen_hiflow_ids
    new_found = 0
    for zone in ZONES:
        if not zone.get("active_always"):
            continue
        print(f"[CHECK] Hiflow {zone['name']} a {datetime.now().strftime('%H:%M:%S')}")
        data = fetch_hiflow_missions(zone)
        if not data:
            continue
        missions = data["response"].get("journeys", []) if isinstance(data, dict) and "response" in data else []
        print(f"  -> {len(missions)} mission(s)")
        for mission in missions:
            mid = str(mission.get("id_journey") or "")
            if not mid or mid in seen_hiflow_ids:
                continue
            distance = int(mission.get("distance_km") or 0)
            if distance < zone.get("min_distance_km", 0):
                print(f"  [SKIP] #{mid} : {distance} km")
                continue
            seen_hiflow_ids.add(mid)
            msg = format_hiflow_mission(mission)
            msg += f" | {zone['name']}"
            if distance >= 400:
                msg = "🔥 " + msg
            send_telegram(msg)
            print(f"  OK #{mid} ({distance} km)")
            new_found += 1
    if new_found == 0:
        print("  Aucune nouvelle mission.")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    print("Hiflow Monitor demarre !")
    send_telegram("Monitor demarre !\n- Hiflow IDF depart+arrivee >= 200km 🔥 si +400km\n- Hiflow Oise (60) >= 200km\n- Notif automatique si cookie expire ✅")
    while True:
        try:
            check_hiflow()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)
