"""
Demo-dag generator voor de Vandaag-pagina.

Schrijft een voorbeeldbestand met 20 ritten (verschillende statussen) naar
data/AppointmentReport_today.xlsx, zodat je collega's kunt laten zien hoe het
live-overzicht werkt op dagen zonder echte ritten.

Tijden zijn relatief aan "nu", dus draai dit script vlak voor de demo opnieuw
voor een verse, kloppende mix:

    py maak_demo_dag.py

Let op: de echte scraper (--quick) overschrijft dit bestand weer. Op Streamlit
Cloud draait de scraper niet, dus daar blijft het demo-bestand staan tot de
volgende push.
"""

from datetime import datetime, timedelta, time as dtime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
TODAY_BESTAND = DATA_DIR / "AppointmentReport_today.xlsx"

# DC -> (DC code, Zone code) — realistische waarden uit de echte portal
DC_INFO = {
    "Moissy":      ("9003", "DCZONE-9003-1A"),
    "Verrières":   ("8997", "DCZONE-8997-1A"),
    "Zwaagdijk":   ("9000", "DCZONE-9000-1A"),
    "Echt":        ("9002", "DCZONE-9002-1A"),
    "Ensues":      ("8995", "DCZONE-8995-1A"),
    "Belleville":  ("8998", "DCZONE-8998-1A"),
    "Peine":       ("9001", "DCZONE-9001-1A"),
    "Illescas":    ("8999", "DCZONE-8999-1A"),
    "Onnaing":     ("9004", "DCZONE-9004-1A"),
    "Ferentino":   ("9005", "DCZONE-9005-1A"),
}

OWNERS = {
    "Good(s)Factory": "1001634",
    "ID Freight Netherlands B.V.": "1002050",
}

KOLOMMEN = [
    "Owner code", "Owner", "Ship ID", "Ship ref", "PO NO", "Order type",
    "Purch group", "Inbound state", "DC code", "DC", "Zone code", "Zone",
    "Pallets", "Pallet return", "Appointment", "Time label", "Arrival",
    "Start unloading", "Finished unloading", "Too late (min)", "Waiting (min)",
    "Unloading (min)", "Refusal reason", "Reported issue", "Cancelled by",
    "Cancel date", "Comment",
]


def _bouw_ritten(nu: datetime) -> list[dict]:
    """Definieer 20 demo-ritten met een realistische spreiding aan statussen."""
    vandaag = nu.date()

    def klok(uur, minuut=0):
        return datetime.combine(vandaag, dtime(uur, minuut))

    def rel(minuten):
        return nu + timedelta(minutes=minuten)

    # (owner, dc, pallets, state, time_label, appointment, arrival,
    #  start_unload, finish_unload, too_late, waiting, unloading, extra)
    R = []

    # --- 6x Afgerond op tijd (Finished, Early/On time) ---
    afgerond_ok = [
        ("Good(s)Factory", "Moissy",     33, "On time", klok(6, 0)),
        ("Good(s)Factory", "Verrières",  36, "Early",   klok(7, 0)),
        ("ID Freight Netherlands B.V.", "Echt", 37, "On time", klok(8, 0)),
        ("Good(s)Factory", "Belleville", 33, "Early",   klok(9, 0)),
        ("Good(s)Factory", "Ensues",     34, "On time", klok(10, 30)),
        ("Good(s)Factory", "Peine",      35, "Early",   klok(11, 0)),
    ]
    for owner, dc, pal, label, appt in afgerond_ok:
        arrival = appt - timedelta(minutes=20 if label == "Early" else 3)
        start = appt + timedelta(minutes=15)
        finish = start + timedelta(minutes=26)
        R.append(dict(owner=owner, dc=dc, pallets=pal, state="Finished",
                      label=label, appointment=appt, arrival=arrival,
                      start=start, finish=finish, too_late=None,
                      waiting=(appt - arrival).seconds // 60, unloading=26))

    # --- 2x Afgerond maar te laat (Finished, Late) ---
    R.append(dict(owner="Good(s)Factory", dc="Zwaagdijk", pallets=37,
                  state="Finished", label="Late", appointment=klok(7, 30),
                  arrival=klok(8, 8), start=klok(8, 20), finish=klok(8, 47),
                  too_late=38, waiting=12, unloading=27))
    R.append(dict(owner="ID Freight Netherlands B.V.", dc="Onnaing", pallets=35,
                  state="Finished", label="Late - Reported", appointment=klok(12, 30),
                  arrival=klok(13, 31), start=klok(13, 40), finish=klok(14, 10),
                  too_late=61, waiting=9, unloading=30,
                  comment="Vooraf gemeld — file A1"))

    # --- 2x Aangekomen (Arrived, wacht op poort) ---
    for dc, pal, off in [("Illescas", 36, -120), ("Ferentino", 39, -100)]:
        appt = rel(off)
        R.append(dict(owner="Good(s)Factory", dc=dc, pallets=pal, state="Arrived",
                      label="On time", appointment=appt,
                      arrival=appt + timedelta(minutes=4),
                      start=None, finish=None, too_late=None, waiting=None,
                      unloading=None))

    # --- 2x Bezig met lossen (Unloading) ---
    for dc, pal, off in [("Moissy", 34, -140), ("Verrières", 33, -110)]:
        appt = rel(off)
        R.append(dict(owner="Good(s)Factory", dc=dc, pallets=pal, state="Unloading",
                      label="On time", appointment=appt,
                      arrival=appt - timedelta(minutes=6),
                      start=appt + timedelta(minutes=10), finish=None,
                      too_late=None, waiting=16, unloading=None))

    # --- 2x Te laat (Expected, afspraak >30 min verstreken, geen aankomst) ---
    for dc, pal, off in [("Echt", 36, -90), ("Zwaagdijk", 38, -50)]:
        R.append(dict(owner="Good(s)Factory", dc=dc, pallets=pal, state="Expected",
                      label=None, appointment=rel(off), arrival=None,
                      start=None, finish=None, too_late=None, waiting=None,
                      unloading=None))

    # --- 2x Op risico / dreigt te laat (Expected, afspraak net verstreken) ---
    for dc, pal, off in [("Belleville", 33, -18), ("Peine", 35, -6)]:
        R.append(dict(owner="Good(s)Factory", dc=dc, pallets=pal, state="Expected",
                      label=None, appointment=rel(off), arrival=None,
                      start=None, finish=None, too_late=None, waiting=None,
                      unloading=None))

    # --- 2x Verwacht (Expected, afspraak in de toekomst) ---
    for dc, pal, off in [("Ensues", 40, 75), ("Illescas", 34, 150)]:
        R.append(dict(owner="ID Freight Netherlands B.V.", dc=dc, pallets=pal,
                      state="Expected", label=None, appointment=rel(off),
                      arrival=None, start=None, finish=None, too_late=None,
                      waiting=None, unloading=None))

    # --- 1x No-show ---
    R.append(dict(owner="Good(s)Factory", dc="Moissy", pallets=33, state="NoShow",
                  label=None, appointment=klok(9, 0), arrival=None, start=None,
                  finish=None, too_late=None, waiting=None, unloading=None,
                  cancelled_by="Good(s)Factory"))

    # --- 1x Geannuleerd ---
    R.append(dict(owner="Good(s)Factory", dc="Verrières", pallets=32,
                  state="Cancelled", label=None, appointment=klok(10, 30),
                  arrival=None, start=None, finish=None, too_late=None,
                  waiting=None, unloading=None, cancelled_by="Good(s)Factory",
                  cancel_date=klok(8, 12)))

    return R


def _naar_rij(idx: int, r: dict) -> dict:
    dc_code, zone_code = DC_INFO[r["dc"]]
    purch = "GOLD Regular" if idx % 3 else "Gold Allocation"
    return {
        "Owner code": OWNERS[r["owner"]],
        "Owner": r["owner"],
        "Ship ID": str(1990001 + idx),
        "Ship ref": None,
        "PO NO": str(4003010000 + idx * 7),
        "Order type": "Regular order",
        "Purch group": purch,
        "Inbound state": r["state"],
        "DC code": dc_code,
        "DC": r["dc"],
        "Zone code": zone_code,
        "Zone": "Zone 1 Truck",
        "Pallets": r["pallets"],
        "Pallet return": "Yes" if idx % 2 else "No",
        "Appointment": r["appointment"],
        "Time label": r.get("label"),
        "Arrival": r.get("arrival"),
        "Start unloading": r.get("start"),
        "Finished unloading": r.get("finish"),
        "Too late (min)": r.get("too_late"),
        "Waiting (min)": r.get("waiting"),
        "Unloading (min)": r.get("unloading"),
        "Refusal reason": None,
        "Reported issue": None,
        "Cancelled by": r.get("cancelled_by"),
        "Cancel date": r.get("cancel_date"),
        "Comment": r.get("comment"),
    }


def main():
    nu = datetime.now()
    ritten = _bouw_ritten(nu)
    rijen = [_naar_rij(i, r) for i, r in enumerate(ritten)]
    df = pd.DataFrame(rijen, columns=KOLOMMEN)

    DATA_DIR.mkdir(exist_ok=True)
    df.to_excel(TODAY_BESTAND, index=False, engine="openpyxl")

    print(f"Demo-dag weggeschreven: {TODAY_BESTAND}")
    print(f"Datum: {nu.date()}  |  {len(df)} ritten")
    print("\nVerdeling states:")
    print(df["Inbound state"].value_counts().to_string())


if __name__ == "__main__":
    main()
