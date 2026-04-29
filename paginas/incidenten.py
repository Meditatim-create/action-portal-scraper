"""Analyse Incidenten — log oorzaken voor Cancelled/NoShow/Refused/Removed."""

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from constanten import (
    DATA_PAD,
    DATUM_KOLOMMEN,
    ELHO_DONKER,
    ELHO_GROEN,
    GRIJS,
    INCIDENT_CATEGORIEEN,
    INCIDENT_STATES,
    NUMERIEKE_KOLOMMEN,
    ORANJE,
    ROOD,
)
from incident_storage import laad_reasons, sla_reason_op

LATEST_BESTAND = os.path.join(DATA_PAD, "AppointmentReport_latest.xlsx")

STATE_KLEUREN = {
    "Cancelled": ROOD,
    "NoShow": ROOD,
    "Refused": ORANJE,
    "Removed": GRIJS,
}


# ---------- Data ----------

def _laad_data() -> pd.DataFrame | None:
    if not os.path.exists(LATEST_BESTAND):
        return None
    df = pd.read_excel(LATEST_BESTAND, engine="openpyxl")
    df.columns = df.columns.str.strip()
    for col in DATUM_KOLOMMEN:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in NUMERIEKE_KOLOMMEN:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Ship ID normaliseren naar string zonder ".0"
    if "Ship ID" in df.columns:
        df["Ship ID"] = (
            df["Ship ID"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        )
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def _is_zinvol(waarde) -> bool:
    """Check of een waarde echt content is (niet NaN of 'nan' string)."""
    if waarde is None or pd.isna(waarde):
        return False
    s = str(waarde).strip().lower()
    return s not in ("", "nan", "none")


# ---------- UI helpers ----------

def _state_badge(state: str) -> str:
    kleur = STATE_KLEUREN.get(state, GRIJS)
    return (
        f'<span style="display:inline-block;background:{kleur}20;color:{kleur};'
        f'padding:2px 10px;border-radius:20px;font-size:0.78rem;font-weight:600;">'
        f'{state}</span>'
    )


def _render_incident_form(rij: pd.Series, bestaande: dict | None):
    ship_id = str(rij["Ship ID"])
    state = str(rij.get("Inbound state", ""))
    apt = rij.get("Appointment")
    apt_str = apt.strftime("%a %d-%m-%Y") if pd.notna(apt) else "?"

    default_cat = bestaande.get("categorie") if bestaande else None
    default_toel = bestaande.get("toelichting", "") if bestaande else ""
    cat_index = (
        INCIDENT_CATEGORIEEN.index(default_cat)
        if default_cat in INCIDENT_CATEGORIEEN else 0
    )

    # Expander-titel
    dc = rij.get("DC", "")
    titel = f"{state} · Ship {ship_id} · {apt_str} · {dc}"
    if bestaande:
        titel = f"✓ {titel} — {bestaande.get('categorie', '')}"

    with st.expander(titel, expanded=not bestaande):
        # Context-kolommen
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Owner**  \n{rij.get('Owner', '—')}")
        c2.markdown(f"**Carrier**  \n{rij.get('Carrier', '—')}")
        pal = int(rij["Pallets"]) if pd.notna(rij.get("Pallets")) else "—"
        c3.markdown(f"**Pallets**  \n{pal}")
        c4.markdown(f"**State**  \n{state}")

        # Bestaande Action-context
        ri = rij.get("Reported issue")
        rr = rij.get("Refusal reason")
        if _is_zinvol(ri):
            st.caption(f"📝 Reported issue (Action): _{ri}_")
        if _is_zinvol(rr):
            st.caption(f"📝 Refusal reason (Action): _{rr}_")

        if bestaande:
            st.caption(
                f"Laatst gelogd door **{bestaande.get('ingevuld_door', '?')}** "
                f"op {bestaande.get('ingevuld_op', '?')[:16].replace('T', ' ')}"
            )

        # Form
        with st.form(f"form_{ship_id}", clear_on_submit=False):
            categorie = st.selectbox(
                "Categorie",
                INCIDENT_CATEGORIEEN,
                index=cat_index,
                key=f"cat_{ship_id}",
            )
            toelichting = st.text_area(
                "Toelichting",
                value=default_toel,
                key=f"toel_{ship_id}",
                placeholder="Wat ging er mis? Wat hebben we hiervan geleerd?",
                height=80,
            )
            opslaan = st.form_submit_button(
                "💾 Bijwerken" if bestaande else "💾 Opslaan",
                type="primary",
            )

            if opslaan:
                if not toelichting.strip():
                    st.error("Toelichting is verplicht — log waarom dit incident plaatsvond.")
                else:
                    gebruiker = st.session_state.get("gebruiker", "onbekend")
                    succes, melding = sla_reason_op(
                        ship_id, gebruiker, categorie, toelichting, state,
                    )
                    if succes:
                        st.success(f"✅ {melding}")
                        st.rerun()
                    else:
                        st.error(f"❌ {melding}")


# ---------- Pagina ----------

def render_incidenten():
    st.markdown(
        f"""
        <h2 style="margin:0;color:{ELHO_DONKER};font-weight:700;letter-spacing:-0.02em;font-size:1.5rem;">
            🔍 analyse incidenten
        </h2>
        <p style="color:{ELHO_DONKER}90;font-size:0.9rem;margin-top:6px;margin-bottom:14px;">
            Log voor elke geannuleerde, no-show, geweigerde of verwijderde rit een oorzaak —
            zo bouwen we een lerende dataset op.
        </p>
        """,
        unsafe_allow_html=True,
    )

    df = _laad_data()
    if df is None or df.empty:
        st.warning("Geen data beschikbaar — controleer of `AppointmentReport_latest.xlsx` aanwezig is.")
        return
    if "Inbound state" not in df.columns:
        st.error("Kolom 'Inbound state' ontbreekt in de dataset.")
        return

    # Filter op incident-states
    df_inc = df[df["Inbound state"].isin(INCIDENT_STATES)].copy()
    if df_inc.empty:
        st.success("🎉 Geen incidenten in de huidige dataset.")
        return

    df_inc = df_inc.sort_values("Appointment", ascending=False, na_position="last")

    # Reasons laden
    reasons = laad_reasons()

    # ---------- Scope-filters (bepalen waar de stats over gaan) ----------
    fcol1, fcol2 = st.columns([1, 1])
    geselecteerde_states = fcol1.multiselect(
        "Filter op state",
        INCIDENT_STATES,
        default=INCIDENT_STATES,
        key="incident_filter_states",
    )

    # Datumfilter (default: laatste 4 weken)
    datum_van = None
    datum_tot = None
    if "Appointment" in df_inc.columns:
        datum_vals = df_inc["Appointment"].dropna()
        if not datum_vals.empty:
            min_d = datum_vals.min().date()
            max_d = datum_vals.max().date()
            default_van = max(max_d - timedelta(days=28), min_d)

            with fcol2:
                dc1, dc2 = st.columns(2)
                datum_van = dc1.date_input(
                    "Van",
                    value=default_van,
                    min_value=min_d,
                    max_value=max_d,
                    key="incident_datum_van",
                )
                datum_tot = dc2.date_input(
                    "Tot",
                    value=max_d,
                    min_value=min_d,
                    max_value=max_d,
                    key="incident_datum_tot",
                )
                if st.button("Toon hele seizoen", key="incident_datum_reset"):
                    st.session_state.incident_datum_van = min_d
                    st.session_state.incident_datum_tot = max_d
                    st.rerun()

    # Filters toepassen
    df_inc = df_inc[df_inc["Inbound state"].isin(geselecteerde_states)]
    if datum_van is not None and datum_tot is not None:
        df_inc = df_inc[
            (df_inc["Appointment"].dt.date >= datum_van)
            & (df_inc["Appointment"].dt.date <= datum_tot)
        ]

    # ---------- Stats over de gefilterde scope ----------
    totaal = len(df_inc)
    gelogd = sum(1 for sid in df_inc["Ship ID"].astype(str) if sid in reasons)
    open_aantal = totaal - gelogd
    pct_gelogd = (gelogd / totaal * 100) if totaal > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incidenten in scope", totaal)
    c2.metric("Gelogd", gelogd)
    c3.metric("Open", open_aantal)
    c4.metric("Voortgang", f"{pct_gelogd:.0f}%")

    st.markdown(
        f"""
        <div style="background:{ELHO_DONKER}12;border-radius:8px;height:8px;overflow:hidden;margin:6px 0 16px;">
            <div style="background:{ELHO_GROEN};width:{pct_gelogd:.0f}%;height:100%;border-radius:8px;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- View-toggle (alleen wat in de lijst getoond wordt) ----------
    toon = st.radio(
        "Tonen",
        ["Alleen open", "Alleen gelogd", "Alles"],
        horizontal=True,
        key="incident_filter_status",
    )

    df_lijst = df_inc.copy()
    if toon == "Alleen open":
        df_lijst = df_lijst[~df_lijst["Ship ID"].astype(str).isin(reasons)]
    elif toon == "Alleen gelogd":
        df_lijst = df_lijst[df_lijst["Ship ID"].astype(str).isin(reasons)]

    st.markdown("---")

    if df_lijst.empty:
        st.info("Geen incidenten matchen de huidige filter.")
    else:
        # Incidenten lijst
        for _, rij in df_lijst.iterrows():
            sid = str(rij["Ship ID"])
            _render_incident_form(rij, reasons.get(sid))

    # Export van gelogde reasons
    if reasons:
        st.markdown("---")
        gelogde_data = []
        for sid, entry in reasons.items():
            gelogde_data.append({"Ship ID": sid, **entry})
        df_export = pd.DataFrame(gelogde_data)
        # Sorteer op datum aflopend
        if "ingevuld_op" in df_export.columns:
            df_export = df_export.sort_values("ingevuld_op", ascending=False)
        st.download_button(
            "📥 Download alle gelogde reasons (CSV)",
            data=df_export.to_csv(index=False).encode("utf-8"),
            file_name=f"incident_reasons_{date.today().isoformat()}.csv",
            mime="text/csv",
        )


# Streamlit page entry
render_incidenten()
