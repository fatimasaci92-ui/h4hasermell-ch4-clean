import ee
import json
import tempfile
import os
import streamlit as st

try:
    # Lire le JSON depuis les secrets
    ee_key_json_str = st.secrets["EE_KEY_JSON"]["json"]  # note le ["json"]
    ee_key_json = json.loads(ee_key_json_str)             # convertir en dict Python

    # Créer un fichier temporaire
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    # Initialiser GEE
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)

    # Supprimer le fichier temporaire
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
