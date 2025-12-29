import streamlit as st
import ee
import json

# Charger la clé depuis st.secrets
ee_key_json = st.secrets["EE_KEY_JSON"]

# Convertir en JSON string pour ServiceAccountCredentials
ee_credentials = ee.ServiceAccountCredentials(
    ee_key_json["client_email"],
    key_data=json.dumps(ee_key_json)
)

# Initialiser Earth Engine
try:
    ee.Initialize(ee_credentials)
    st.success("✅ Google Earth Engine initialisé avec succès !")
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de GEE : {e}")
