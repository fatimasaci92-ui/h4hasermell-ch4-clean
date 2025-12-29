import ee
import json
import tempfile
import os
import streamlit as st

try:
    # Charger la clé depuis les secrets
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    
    # Créer un fichier temporaire pour GEE
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    # Initialiser GEE avec la clé
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)

    # Supprimer le fichier temporaire
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
