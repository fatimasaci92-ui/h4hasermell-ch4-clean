import streamlit as st
import ee
import tempfile
import json
import os

try:
    ee_key_json = st.secrets["EE_KEY_JSON"]  # déjà un dict
    # Crée un fichier temporaire avec la clé
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    # Initialise GEE
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"],
        key_path
    )
    ee.Initialize(credentials)

    # Supprime le fichier temporaire
    os.remove(key_path)
    st.success("✅ Google Earth Engine initialisé correctement")

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
