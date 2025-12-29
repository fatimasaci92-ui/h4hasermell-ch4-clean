import ee
import tempfile
import os
import streamlit as st

try:
    ee_key_json = st.secrets["EE_KEY_JSON"]  # récupéré directement comme dict

    # Crée un fichier temporaire avec la clé pour EE
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        import json
        json.dump(ee_key_json, f)
        key_path = f.name

    # Initialise GEE
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)
    st.success("✅ Google Earth Engine initialisé correctement")

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
