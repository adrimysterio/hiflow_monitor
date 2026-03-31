import requests
import time
import json
from datetime import datetime
from bs4 import BeautifulSoup

# ============================================================
#  CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = "8621167866:AAEzwgq2nQiBjKftLmxbjqUgcZal-dKssMQ"
TELEGRAM_CHAT_ID = "-5099081999"

HIFLOW_COOKIE = "conveyor_session_id=CONVEYOR_27170_c1c8d3b39587ae99f649b21ba9261ff26f3b5a4ce73a0f941114814962b75418"
HIFLOW_AUTHOR_ID = "27170"

CONVOICAR_URL = "https://web.convoicar.fr/d/rides"
CONVOICAR_COOKIE = "_ga=GA1.1.717503229.1750778451; _ga_T0R12Z97Q9=GS2.2.s1751646099$o13$g1$t1751646104$j55$l0$h0; _ga_0KW2L0C87L=GS2.1.s1751656253$o14$g0$t1751656253$j60$l0$h0; remember_user_token=eyJfcmFpbHMiOnsibWVzc2FnZSI6Ilcxc3lOekV4WFN3aUpESmhKREV4SkdkelMyWm1VUzh6WXpjdk1FNWxTWFl6Um1wd1FuVWlMQ0l4TnpjME5EYzBNVEUxTGpRek1EVTVPRE1pWFE9PSIsImV4cCI6IjIwMjYtMDQtMDhUMjA6Mjg6MzUuNDMwWiIsInB1ciI6bnVsbH19--7bb014f4669bb5045c6ab21b0dbd4f332f94e200; _argon_session=N0NFTTdXczZVYS96ZjU3enljenpnQWhKemo3WVdTbjZobzBuQ1ZYZm4wVDVrUkNPdUo5VW85M1ZkT1ZTd1FYMlg0UmJMallJOVBGMDV1eHJDOFRDZDU0RHoybW95K0JaQlhsV1R0N2s4elZwamNxcXJkbUlyTHVwaDdTTkk1Z0J2RmdtdGc1NHJJNXMveklMZTMwNEZWL0dseE5FMGw0bXEzdFlxOW9hOHNtSTJ5dTF0UU9jZEtROEkvL1M0dnAxTnMwa29TMVd5SzFRdHlaYlVZVG1WRXVpT3Exc1Y1UjdqTE1xcElreG9Xa2Z0RklQeTl3TWNYOElQN1dEOW44dDNyT3FPdFgraDVhRTZIbkJ0TzgrNmxrVnVLL1VOd2FOdXlNcW9xYStYcEIxRURyYXdTZ3BVUnZjdUhiTm56UFZIQlgveW9tcGhnM3p3QVVMU010a2RadXlyTGY1RE41cDNwOU5LcU16OGJ3PS0tdVo0Z3hMOWhmSjVCczMrS1FUdEE0QT09--0c8f8dc9be2f08069331b973f2c1a8bd56dfa4bc"

CHECK_INTERVAL = 60

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
        "name": "Oise Depart",
        "department_start": "60",
        "active_always": True,
        "min_distance_km": 200,
    },
    {
        "name": "Oise Arrivee",
        "department_end": "60",
        "active_always": True,
        "min_distance_km": 200,
    },

]

seen_hiflow_ids = set()
seen_convoicar_ids = set()
convoicar_first_run = True


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
        "order_by": "date_end",
        "sort": "asc",
        "omnisearch": "",
        "id_conveyor": HIFLOW_AUTHOR_ID,
        "with_tag": "1",
        "limit": "0,50",
        "extra_info": "tableJourneyList_1",
    }
    if "region_start" in zone:
        params["region_start"] = zone["region_start"]
    if "region_end" in zone:
        params["region_end"] = zone["region_end"]
    if "department_start" in zone:
        params["department_start"] = zone["department_start"]
    if "department_end" in zone:
        params["department_end"] = zone["department_end"]
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base}?{query}"


def fetch_hiflow_missions(zone):
    url = build_hiflow_url(zone)
    headers = {
        "Cookie": HIFLOW_COOKIE,
        "Author-Id": HIFLOW_AUTHOR_ID,
        "Author-Type": "conveyor",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://partenaire.expedicar.com/journey/list",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HIFLOW ERROR] {zone['name']} : {e}")
        return None


def is_zone_active(zone):
    if zone.get("active_always"):
        return True
    if "active_until" in zone:
        today = datetime.now().strftime("%Y-%m-%d")
        return today <= zone["active_until"]
    return True


def format_hiflow_mission(mission):
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
        prix_base = mission.get("pricing", {}).get("conveyor_price", "?")
        prix_instant = mission.get("pricing", {}).get("instant_booking_cost", None)
        prix_str = f"{prix_instant} EUR" if prix_instant else f"{prix_base} EUR"
        return f"{depart} -> {arrivee} | {date} | {distance} km | {prix_str}"
    except Exception:
        return "Nouvelle mission Hiflow disponible !"


def check_hiflow():
    global seen_hiflow_ids
    new_found = 0

    for zone in ZONES:
        if not is_zone_active(zone):
            continue

        print(f"[CHECK] Hiflow {zone['name']} a {datetime.now().strftime('%H:%M:%S')}")
        data = fetch_hiflow_missions(zone)
        if not data:
            continue

        missions = []
        if isinstance(data, dict) and "response" in data:
            missions = data["response"].get("journeys", [])
        elif isinstance(data, list):
            missions = data

        print(f"  -> {len(missions)} mission(s) trouvee(s)")

        for mission in missions:
            mid = str(mission.get("id_journey") or "")
            if not mid or mid in seen_hiflow_ids:
                continue

            distance = int(mission.get("distance_km") or 0)
            date_start = mission.get("dates", {}).get("start", "")

            if "min_distance_km" in zone:
                if distance < zone["min_distance_km"]:
                    print(f"  [SKIP] #{mid} : {distance} km < {zone['min_distance_km']} km")
                    continue

            if "date_filter" in zone:
                if not date_start.startswith(zone["date_filter"]):
                    print(f"  [SKIP] #{mid} : pas le bon jour")
                    continue

            seen_hiflow_ids.add(mid)
            msg = format_hiflow_mission(mission)
            msg += f" | {zone['name']}"
            if distance >= 400:
                msg = "🔥 " + msg
            send_telegram(msg)
            print(f"  OK Notif Hiflow #{mid} ({distance} km)")
            new_found += 1

    if new_found == 0:
        print("  Aucune nouvelle mission Hiflow.")


# ============================================================
#  CONVOICAR
# ============================================================

def check_convoicar():
    global seen_convoicar_ids, convoicar_first_run
    print(f"[CHECK] Convoicar a {datetime.now().strftime('%H:%M:%S')}")

    headers = {
        "Cookie": CONVOICAR_COOKIE,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://web.convoicar.fr/",
    }
    try:
        r = requests.get(CONVOICAR_URL, headers=headers, timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"[CONVOICAR ERROR] {e}")
        return

    soup = BeautifulSoup(html, "html.parser")
    new_found = 0
    seen_hrefs = set()

    links = soup.find_all("a", href=lambda h: h and "/d/rides/" in h)
    print(f"  -> {len(links)} lien(s) missions trouve(s)")

    for link in links:
        href = link.get("href", "")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        mission_id = href.split("/d/rides/")[-1].strip("/").split("?")[0]
        if not mission_id or not mission_id.isdigit():
            continue
        if mission_id in seen_convoicar_ids:
            continue

        # Remonte au bloc parent pour extraire les infos
        parent = link.find_parent("tr") or link.find_parent("div") or link
        text = parent.get_text(separator=" | ", strip=True)[:300]

        # Filtre prix >= 100€
        import re
        prices = re.findall(r"(\d+)[,.]?(\d*)\s*EUR|€", text)
        nums = re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:€|EUR)", text)
        max_price = 0
        for n in nums:
            try:
                val = float(n.replace(",", "."))
                if val > max_price:
                    max_price = val
            except:
                pass

        seen_convoicar_ids.add(mission_id)

        if max_price > 0 and max_price < 100:
            print(f"  [SKIP] Convoicar #{mission_id} : {max_price}EUR < 100EUR")
            continue

        lien = f"https://web.convoicar.fr/d/rides/{mission_id}"
        send_telegram(f"🍑 CONVOICAR | {max_price} EUR\n{text}\n{lien}")
        print(f"  OK Notif Convoicar #{mission_id} ({max_price}EUR)")
        new_found += 1

    convoicar_first_run = False

    if new_found == 0:
        print("  Aucune nouvelle mission Convoicar.")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    # Remise a zero au demarrage pour envoyer toutes les missions existantes
    seen_convoicar_ids.clear()
    print("Hiflow + Convoicar Monitor demarre !")
    send_telegram("Monitor demarre !\n- Hiflow IDF depart+arrivee >= 200km 🔥 si +400km\n- Hiflow Oise (60) depart+arrivee >= 200km\n- Convoicar >= 100EUR 🍑")

    while True:
        try:
            check_hiflow()
            check_convoicar()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)
