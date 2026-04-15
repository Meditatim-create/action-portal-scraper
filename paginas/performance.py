"""Performance — historische shipment analyse."""

import streamlit as st

from app import render_dashboard, _render_filters, _pas_filters_toe

# Streamlit page entry point
df = st.session_state.get("df_action")
if df is not None and not df.empty:
    # Debug info (tijdelijk)
    with st.expander("🔧 Debug info"):
        st.write(f"Kolommen: {list(df.columns)}")
        st.write(f"Rijen: {len(df)}")
        st.write(f"Carrier in kolommen: {'Carrier' in df.columns}")
        if "Carrier" in df.columns:
            st.write(f"Carrier waarden: {df['Carrier'].value_counts().to_dict()}")
    render_dashboard(df)
else:
    st.warning("Geen data beschikbaar. Controleer of het rapport is gesynchroniseerd.")
