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

HIFLOW_EMAIL = os.environ.get("HIFLOW_EMAIL", "adrien.hurdubae@gmail.com")
HIFLOW_PASSWORD = os.environ.get("HIFLOW_PASSWORD", "joogi705po")
HIFLOW_AUTHOR_ID = "27170"

CHECK_INTERVAL = 60
COOKIE_REFRESH_INTERVAL = 3600  # renouvelle le cookie toutes les heures

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
hiflow_cookie = None
last_cookie_refresh = 0


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
#  CONNEXION HIFLOW — renouvellement auto du cookie
# ============================================================

def login_hiflow():
    global hiflow_cookie, last_cookie_refresh
    print(f"[LOGIN] Connexion Hiflow en cours...")
    
    session = requests.Session()
    
    # Page de login pour récupérer le token CSRF
    try:
        r = session.get("https://partenaire.expedicar.com/conveyor/sign_in", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf = soup.find("input", {"name": "authenticity_token"})
        if not csrf:
            print("[LOGIN ERROR] Token CSRF introuvable")
            return False
        csrf_token = csrf["value"]
    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return False

    # Connexion
    try:
        payload = {
            "conveyor[email]": HIFLOW_EMAIL,
            "conveyor[password]": HIFLOW_PASSWORD,
            "authenticity_token": csrf_token,
        }
        r = session.post(
            "https://partenaire.expedicar.com/conveyor/sign_in",
            data=payload,
            timeout=15,
            allow_redirects=True
        )
        
        # Récupère le cookie de session
        cookie_val = session.cookies.get("conveyor_session_id")
        if cookie_val:
            hiflow_cookie = f"conveyor_session_id={cookie_val}"
            last_cookie_refresh = time.time()
            print(f"[LOGIN] Cookie renouvelé avec succès !")
            return True
        else:
            print("[LOGIN ERROR] Pas de cookie dans la réponse — identifiants incorrects ?")
            return False
    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return False


def get_hiflow_cookie():
    global hiflow_cookie, last_cookie_refresh
    # Renouvelle si pas de cookie ou si plus d'1 heure
    if not hiflow_cookie or (time.time() - last_cookie_refresh) > COOKIE_REFRESH_INTERVAL:
        login_hiflow()
    return hiflow_cookie


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
    cookie = get_hiflow_cookie()
    if not cookie:
        print(f"[HIFLOW] Pas de cookie disponible")
        return None
    
    url = build_hiflow_url(zone)
    headers = {
        "Cookie": cookie,
        "Author-Id": HIFLOW_AUTHOR_ID,
        "Author-Type": "conveyor",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://partenaire.expedicar.com/journey/list",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        # Si réponse invalide, forcer un nouveau login
        if not isinstance(data, dict) or "response" not in data:
            print(f"[HIFLOW] Réponse inattendue, renouvellement cookie...")
            login_hiflow()
            return None
        return data
    except Exception as e:
        print(f"[HIFLOW ERROR] {zone['name']} : {e}")
        login_hiflow()
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
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    print("Hiflow Monitor demarre !")
    
    # Connexion initiale
    if login_hiflow():
        send_telegram("Monitor demarre !\n- Hiflow IDF depart+arrivee >= 200km 🔥 si +400km\n- Hiflow Oise (60) depart+arrivee >= 200km\n- Cookie auto-renouvelé toutes les heures ✅")
    else:
        send_telegram("⚠️ Monitor demarre mais echec de connexion Hiflow !")

    while True:
        try:
            check_hiflow()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)
