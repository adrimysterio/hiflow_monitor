import requests
import time
import json
from datetime import datetime

# ============================================================
#  CONFIGURATION — modifie ces valeurs si besoin
# ============================================================

TELEGRAM_TOKEN = "8621167866:AAEzwgq2nQiBjKftLmxbjqUgcZal-dKssMQ"
TELEGRAM_CHAT_ID = "7411656885"

COOKIE = "conveyor_session_id=CONVEYOR_27170_be9360b41089014a3669fc1b701b4e217442694e57e1e9395c8751912a18c861"
AUTHOR_ID = "27170"

# Intervalle de vérification en secondes (60 = toutes les minutes)
CHECK_INTERVAL = 60

# Date limite pour Toulouse (format YYYY-MM-DD)
TOULOUSE_DATE_LIMIT = "2026-03-22"

# ============================================================
#  ZONES À SURVEILLER
# ============================================================

ZONES = [
    {
        "name": "Paris / Île-de-France",
        "region_end": "Ile-de-france",
        "active_always": True,
    },
    {
        "name": "Toulouse",
        "region_start": "occitanie",  # missions au départ de Toulouse
        "active_until": TOULOUSE_DATE_LIMIT,
    },
]

# ============================================================
#  FONCTIONS
# ============================================================

seen_mission_ids = set()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
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
        # Le site renvoie du HTML ou du JSON selon l'état de session
        try:
            data = r.json()
            return data
        except Exception:
            print(f"[WARN] Réponse non-JSON pour zone {zone['name']} — session expirée ?")
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
        depart = mission.get("city_start") or mission.get("department_start") or "?"
        arrivee = mission.get("city_end") or mission.get("department_end") or "?"
        date = mission.get("date_start") or mission.get("date_end") or "?"
        prix = mission.get("price") or mission.get("amount") or "?"
        mission_id = mission.get("id") or mission.get("id_journey") or "?"
        return (
            f"🚗 <b>Nouvelle mission !</b>\n"
            f"📍 {depart} → {arrivee}\n"
            f"📅 {date}\n"
            f"💶 {prix} €\n"
            f"🆔 Mission #{mission_id}"
        )
    except Exception:
        return f"🚗 Nouvelle mission disponible !\n{json.dumps(mission, ensure_ascii=False)[:300]}"


def check_all_zones():
    global seen_mission_ids
    new_found = 0

    for zone in ZONES:
        if not is_zone_active(zone):
            print(f"[SKIP] Zone {zone['name']} inactive aujourd'hui")
            continue

        print(f"[CHECK] {zone['name']} à {datetime.now().strftime('%H:%M:%S')}")
        data = fetch_missions(zone)

        if not data:
            continue

        # Cherche les missions dans la réponse (structure variable)
        missions = []
        if isinstance(data, list):
            missions = data
        elif isinstance(data, dict):
            for key in ["journeys", "data", "results", "items"]:
                if key in data and isinstance(data[key], list):
                    missions = data[key]
                    break
            if not missions:
                # Cherche récursivement une liste
                for v in data.values():
                    if isinstance(v, list) and len(v) > 0:
                        missions = v
                        break

        print(f"  → {len(missions)} mission(s) trouvée(s)")

        for mission in missions:
            mid = str(mission.get("id") or mission.get("id_journey") or "")
            if mid and mid not in seen_mission_ids:
                seen_mission_ids.add(mid)
                msg = format_mission(mission)
                msg += f"\n🗺️ Zone : {zone['name']}"
                send_telegram(msg)
                print(f"  ✅ Notif envoyée pour mission #{mid}")
                new_found += 1

    if new_found == 0:
        print(f"  Aucune nouvelle mission.")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    print("🚀 Hiflow Monitor démarré !")
    print(f"   Vérification toutes les {CHECK_INTERVAL} secondes")
    send_telegram("✅ <b>Hiflow Monitor démarré !</b>\nJe surveille les nouvelles missions et t'enverrai une notification dès qu'une apparaît.")

    while True:
        try:
            check_all_zones()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)
