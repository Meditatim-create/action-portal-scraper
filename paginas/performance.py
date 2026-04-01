"""Performance — historische shipment analyse."""

import streamlit as st

from app import render_dashboard, _render_filters, _pas_filters_toe

# Streamlit page entry point
df = st.session_state.get("df_action")
if df is not None and not df.empty:
    render_dashboard(df)
else:
    st.warning("Geen data beschikbaar. Controleer of het rapport is gesynchroniseerd.")
