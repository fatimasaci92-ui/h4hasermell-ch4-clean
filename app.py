# ===================== INITIALISATION GEE =====================
import ee
import json
import tempfile
import os
import streamlit as st

try:
    # Charger la clé depuis les secrets Streamlit
    ee_key_json = json.loads(st.secrets["EE"]["EE_KEY_JSON"])

    # Créer un fichier temporaire pour la clé
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    # Initialiser GEE avec la clé de service
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)

    # Supprimer le fichier temporaire pour sécurité
    os.remove(key_path)

    st.success("✅ Google Earth Engine initialisé avec succès")

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()
