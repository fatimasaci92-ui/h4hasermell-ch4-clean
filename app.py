import ee
import json
import tempfile
import os
import streamlit as st

try:
    # Récupérer la chaîne JSON du secret
    ee_key_json_str = st.secrets["EE_KEY_JSON"]["json"]
    ee_key_json = json.loads(ee_key_json_str)

    # Créer un fichier temporaire pour l'initialisation
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
