"""Gedeelde constanten voor het Action Portal Dashboard."""

import os
from datetime import date

# ---------- Nederlandse datum ----------

_DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_MAANDEN = ["", "januari", "februari", "maart", "april", "mei", "juni",
            "juli", "augustus", "september", "oktober", "november", "december"]


def nl_datum(d: date) -> str:
    """Geef datum als 'woensdag 01 april'."""
    return f"{_DAGEN[d.weekday()]} {d.strftime('%d')} {_MAANDEN[d.month]}"

# ---------- Paden ----------

DATA_PAD = os.path.join(os.path.dirname(__file__), "data")
DOWNLOADS_PAD = os.path.join(os.path.dirname(__file__), "downloads")

# ---------- Kolommen ----------

DATUM_KOLOMMEN = [
    "Appointment", "Arrival", "Start unloading", "Finished unloading", "Cancel date",
]

NUMERIEKE_KOLOMMEN = ["Too late (min)", "Waiting (min)", "Unloading (min)", "Pallets"]

TIME_LABEL_GOED = ["Early", "On time"]
TIME_LABEL_SLECHT = ["Late", "Late - Reported"]

ONZE_PERFORMANCE_STATES = ["Finished", "Cancelled", "NoShow"]
SLECHT_STATES = ["Cancelled", "NoShow"]

# Owners die standaard uit de analyse worden gelaten (kan via sidebar toggle weer aan).
STANDAARD_UITGESLOTEN_OWNERS = ["DSV Road sp. z o.o."]

# ---------- Analyse incidenten ----------

# States die als "incident" gelden en dus een reason vereisen
INCIDENT_STATES = ["Cancelled", "NoShow", "Refused", "Removed"]

# Vooraf gedefinieerde categorieën voor lerend systeem
INCIDENT_CATEGORIEEN = [
    "Carrier — te laat onderweg",
    "Carrier — geen capaciteit",
    "Elho — order te laat klaar",
    "Elho — verkeerd ingepland logistics",
    "Elho — verkeerd ingepland team goods",
    "Action — slot teruggetrokken",
    "Action — DC vol",
    "Klantverzoek — verschoven",
    "Goederen niet beschikbaar",
    "Anders (zie toelichting)",
]

REASONS_PAD = os.path.join(DATA_PAD, "reasons.json")

# ---------- Refresh ----------

REFRESH_INTERVAL = 600  # Seconden (10 minuten) tussen live data-refreshes

# ---------- Elho branding ----------

ELHO_GROEN = "#76a73a"
ELHO_DONKER = "#0a4a2f"
ROOD = "#e74c3c"
GRIJS = "#95a5a6"
ORANJE = "#e67e22"
