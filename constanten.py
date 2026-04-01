"""Gedeelde constanten voor het Action Portal Dashboard."""

import os

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

# ---------- Refresh ----------

REFRESH_INTERVAL = 600  # Seconden (10 minuten) tussen live data-refreshes

# ---------- Elho branding ----------

ELHO_GROEN = "#76a73a"
ELHO_DONKER = "#0a4a2f"
ROOD = "#e74c3c"
GRIJS = "#95a5a6"
ORANJE = "#e67e22"
