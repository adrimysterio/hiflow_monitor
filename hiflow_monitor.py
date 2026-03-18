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
        "name": "IDF Depart",
        "region_start": "Ile-de-france",
        "active_always": True,
        "min_distance_km": 200,
    },
    {
        "name": "IDF Arrivee",
        "region_end": "Ile-de-france",
        "active_always": True,
        "min_distance_km": 200,
    },
    {
        "name": "Toulouse",
        "region_start": "occitanie",
        "active_until": "2026-03-22",
        "date_filter": "20260320",
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
    if "region_start" in zone:
        params["region_start"] = zone["region_start"]
    if "region_end" in zone:
        params["region_end"] = zone["region_end"]
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
            check_convoicar()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)


# ============================================================
#  CONVOICAR — SCRAPING HTML
# ============================================================

from bs4 import BeautifulSoup

CONVOICAR_URL = "https://web.convoicar.fr/d/rides"
CONVOICAR_COOKIE = "_ga=GA1.1.717503229.1750778451; remember_user_token=eyJfcmFpbHMiOnsibWVzc2FnZSI6Ilcxc3lOekV4WFN3aUpESmhKREV4SkdkelMyWm1VUzh6WXpjdk1FNWxTWFl6Um1wd1FuVWlMQ0l4Tnpjek1qVXpORGc0TGpJM016TTROeUpkIiwiZXhwIjoiMjAyNi0wMy0yNVQxODoyNDo0OC4yNzNaIiwicHVyIjpudWxsfX0%3D--516c78051777cc71cdbc81cb2469010f1eba6048; _argon_session=bVlUSjVWcm85Tk1Kcit2UDIxV3lFMDJ1VWlrdHVZc1pjNGMwUEdIM0FRWmlLTXBSdnlCemZ0bDNlVi9CaklmcmQvRXg3YXRVYjRub3d4bG1WN1dXYWh4QWVwaytyMEU3blkzOGRuMDMxVVBaNzVRZ21ZcXBINjdhb0dFWCtGSlRJM3A3dk4rdFVYb2FkQ2VGODVQWkN1ekNZMWM0Uk9zaFhRcjU0TmF4SlhkcGZPVm5Cc2lpS1NJQzN2NUxKREw3N3pSWmlrNUthU3F0bEtjSFIxT29ockFKK0xwN1Y4ZFFLYkh5WlBQVTFwd2dBMW1hcDZtTWRtNVUzU1JRVU1OK1hZRlVzUzhLc1l6Vk1tR1hjT1hGWVVFb2FEUXFTOTM2czNOaG5QTUJGMG53TjZQKzM3enF0Z2pudkQ5Um1ubFlJZzhhbXVEUHRadTFqMEV2TWFIdit0QU5vd0RTejR6VXl0RStTWE1aVE0wPS0tRHJLMlp4c1dyUXJNRDhBbWU3bnhvQT09--4dcac2e6a15c05e473f97dfc8b7047af6ecbc549"

seen_convoicar_ids = set()


def fetch_convoicar_missions():
    headers = {
        "Cookie": CONVOICAR_COOKIE,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://web.convoicar.fr/",
    }
    try:
        r = requests.get(CONVOICAR_URL, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[CONVOICAR ERROR] {e}")
        return None


def parse_convoicar_missions(html):
    soup = BeautifulSoup(html, "html.parser")
    missions = []
    # Cherche les blocs de missions
    cards = soup.find_all("div", class_=lambda c: c and "ride" in c.lower())
    if not cards:
        # Fallback: cherche les liens avec /d/rides/
        cards = soup.find_all("a", href=lambda h: h and "/d/rides/" in h)
    for card in cards:
        text = card.get_text(separator=" ", strip=True)
        href = card.get("href", "") if card.name == "a" else ""
        mission_id = href.split("/d/rides/")[-1].split("?")[0] if "/d/rides/" in href else None
        if text and len(text) > 10:
            missions.append({"id": mission_id, "text": text, "raw": card})
    return missions


def check_convoicar():
    global seen_convoicar_ids
    print(f"[CHECK] Convoicar a {datetime.now().strftime('%H:%M:%S')}")
    html = fetch_convoicar_missions()
    if not html:
        return

    soup = BeautifulSoup(html, "html.parser")
    new_found = 0

    # Cherche tous les liens de missions
    links = soup.find_all("a", href=lambda h: h and "/d/rides/" in h)
    seen_hrefs = set()

    for link in links:
        href = link.get("href", "")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        mission_id = href.split("/d/rides/")[-1].strip("/").split("?")[0]
        if not mission_id or mission_id in seen_convoicar_ids:
            continue

        # Remonte au bloc parent pour extraire les infos
        parent = link.find_parent("div") or link
        text = parent.get_text(separator=" | ", strip=True)

        seen_convoicar_ids.add(mission_id)
        msg = f"CONVOICAR\n{text[:300]}"
        send_telegram(msg)
        print(f"  OK Notif Convoicar #{mission_id}")
        new_found += 1

    if new_found == 0:
        print("  Aucune nouvelle mission Convoicar.")


