# =====================================================================
#  heizung.py – plant die Standheizung (DEFA WarmUp) für MORGEN
#
#  Läuft jeden Abend (22 Uhr) über GitHub Actions und:
#    1. schaut nach, wann du morgen losfährst
#       (Uni-Beginn minus 45 min, plus ggf. Busfahrt um 6:45)
#    2. holt die Wettervorhersage für diese Uhrzeit
#    3. rechnet aus, wie lange vorher geheizt werden muss
#       (DEFA-Handbuch, Diagramm D14)
#    4. programmiert der Tuya-Steckdose die Ein-/Aus-Timer
#
#  Die Steckdose schaltet danach selbstständig – es muss nachts
#  kein Computer laufen.
# =====================================================================

import json
import os
from datetime import date, datetime, timedelta

import requests
import tinytuya

# ---------------------------------------------------------------------
#  EINSTELLUNGEN – hier kannst du alles anpassen
# ---------------------------------------------------------------------

# Nur Plan ausgeben, nichts an die Steckdose schicken (zum Testen)
TROCKENLAUF = True

# Wo das Auto nachts steht (für die Wettervorhersage) – hier: Heide
BREITENGRAD = 54.196
LAENGENGRAD = 9.093

# So viele Minuten vor Uni-Beginn fährst du los
VORLAUF_UNI = 45

# Busfahrten um 6:45 – nur werktags (Mo–Fr) in diesem Zeitraum
BUS_ABFAHRT = "06:45"
BUS_VON = date(2026, 11, 9)
BUS_BIS = date(2026, 11, 27)

# Ab wann du nach der Busfahrt wieder zu Hause bist (Auto eingesteckt)
ZURUECK_ZUHAUSE = "07:15"

# Datei mit dem ersten Uni-Termin pro Tag, z. B. {"2026-11-09": "10:00"}
# (wird vom Stundenplan-Skript build.py erzeugt)
TERMINE_DATEI = "termine.json"

# Heizdauer nach Außentemperatur (DEFA-Handbuch, Diagramm D14):
#   bei   0 °C  ->  90 min vor Abfahrt einschalten
#   bei -17 °C  -> 195 min (mehr als das bringt nichts)
#   wärmer als +10 °C -> gar nicht heizen
# Dazwischen wird gerade Linie gerechnet: pro Grad kälter ca. 6 min länger.
NICHT_HEIZEN_AB = 10
MAX_MINUTEN = 195

# Zugangsdaten für die Tuya-Cloud (kommen aus den GitHub-Secrets)
TUYA_KEY = os.environ.get("TUYA_KEY", "")
TUYA_SECRET = os.environ.get("TUYA_SECRET", "")
TUYA_GERAET = os.environ.get("TUYA_GERAET", "")


# ---------------------------------------------------------------------
#  1. Wann fahre ich morgen los?
# ---------------------------------------------------------------------

morgen = date.today() + timedelta(days=1)
abfahrten = []   # Liste von Uhrzeiten (datetime)

# Busfahrt?
ist_werktag = morgen.weekday() < 5          # 0 = Montag ... 4 = Freitag
busfahrt = ist_werktag and BUS_VON <= morgen <= BUS_BIS
if busfahrt:
    abfahrten.append(datetime.combine(morgen, datetime.strptime(BUS_ABFAHRT, "%H:%M").time()))

# Uni?
if os.path.exists(TERMINE_DATEI):
    with open(TERMINE_DATEI, encoding="utf-8") as f:
        termine = json.load(f)
    beginn = termine.get(morgen.isoformat())
    if beginn:
        uni_beginn = datetime.combine(morgen, datetime.strptime(beginn, "%H:%M").time())
        abfahrten.append(uni_beginn - timedelta(minutes=VORLAUF_UNI))
else:
    print(f"Hinweis: {TERMINE_DATEI} fehlt – Uni-Zeiten werden ignoriert.")

if not abfahrten:
    print(f"{morgen:%a %d.%m.}: keine Fahrt geplant – nichts zu tun.")


# ---------------------------------------------------------------------
#  2. Wettervorhersage holen (Open-Meteo, kostenlos, ohne Anmeldung)
# ---------------------------------------------------------------------

temperatur_pro_stunde = {}
if abfahrten:
    antwort = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": BREITENGRAD,
            "longitude": LAENGENGRAD,
            "hourly": "temperature_2m",
            "timezone": "Europe/Berlin",
            "start_date": morgen.isoformat(),
            "end_date": morgen.isoformat(),
        },
        timeout=30,
    )
    daten = antwort.json()["hourly"]
    for zeit, temp in zip(daten["time"], daten["temperature_2m"]):
        temperatur_pro_stunde[zeit[11:13]] = temp     # "07" -> 2.4


# ---------------------------------------------------------------------
#  3. Heizfenster ausrechnen
# ---------------------------------------------------------------------

heizfenster = []   # Liste von (ein, aus, temperatur)
zuhause_ab = datetime.combine(morgen, datetime.strptime(ZURUECK_ZUHAUSE, "%H:%M").time())

for abfahrt in abfahrten:
    temp = temperatur_pro_stunde[f"{abfahrt.hour:02d}"]

    if temp > NICHT_HEIZEN_AB:
        print(f"Abfahrt {abfahrt:%H:%M}: {temp:.1f} °C – zu warm, kein Heizen.")
        continue

    # Heizdauer: 90 min bei 0 °C, pro Grad kälter ca. 6 min mehr
    minuten = round(90 - temp * 105 / 17)
    minuten = min(minuten, MAX_MINUTEN)

    ein = abfahrt - timedelta(minutes=minuten)

    # Zweite Fahrt nach dem Bus: erst heizen, wenn das Auto wieder da ist
    if busfahrt and abfahrt > zuhause_ab and ein < zuhause_ab:
        ein = zuhause_ab
    if ein >= abfahrt:
        print(f"Abfahrt {abfahrt:%H:%M}: Auto ist noch warm vom Bus-Weg – kein Heizen.")
        continue

    heizfenster.append((ein, abfahrt, temp))
    print(f"Abfahrt {abfahrt:%H:%M} bei {temp:.1f} °C  ->  "
          f"Heizung EIN {ein:%H:%M}, AUS {abfahrt:%H:%M}")


# ---------------------------------------------------------------------
#  4. Timer an die Steckdose schicken
# ---------------------------------------------------------------------

if TROCKENLAUF:
    print("Trockenlauf – es wurde nichts an die Steckdose geschickt.")
else:
    cloud = tinytuya.Cloud(apiRegion="eu", apiKey=TUYA_KEY,
                           apiSecret=TUYA_SECRET, apiDeviceID=TUYA_GERAET)

    # Alte Heizungs-Timer löschen
    cloud.cloudrequest(f"/v1.0/devices/{TUYA_GERAET}/timers/categories/heizung",
                       action="DELETE")

    # Neue Timer anlegen: je einer für EIN und AUS
    befehle = []
    for ein, aus, temp in heizfenster:
        befehle.append({"date": f"{ein:%Y%m%d}", "time": f"{ein:%H:%M}",
                        "functions": [{"code": "switch_1", "value": True}]})
        befehle.append({"date": f"{aus:%Y%m%d}", "time": f"{aus:%H:%M}",
                        "functions": [{"code": "switch_1", "value": False}]})

    if befehle:
        ergebnis = cloud.cloudrequest(
            f"/v1.0/devices/{TUYA_GERAET}/timers",
            action="POST",
            post={"category": "heizung", "loops": "0000000",
                  "timezone_id": "Europe/Berlin", "time_zone": "+01:00",
                  "instruct": befehle},
        )
        print("Antwort der Tuya-Cloud:", ergebnis)
