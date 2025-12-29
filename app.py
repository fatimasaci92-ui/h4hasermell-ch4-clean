# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import ee
import json
from datetime import datetime
import folium
from streamlit_folium import st_folium
import os
import matplotlib.pyplot as plt
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import smtplib
from email.mime.text import MIMEText

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")
st.info(
    "⚠️ Surveillance régionale du CH₄ basée sur Sentinel-5P. "
    "Ce système ne remplace pas les inspections terrain."
)

import ee
import json
import streamlit as st

# ===================== INITIALISATION GEE =====================
try:
    # Lire la clé directement depuis st.secrets
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    
    # Créer les credentials directement à partir du dict
    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"],
        ee_key_json  # PAS de chemin de fichier, juste le dict
    )
    ee.Initialize(credentials)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ===================== SIDEBAR =====================
st.sidebar.header("📍 Paramètres du site")
latitude = st.sidebar.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.sidebar.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.sidebar.text_input("Nom du site", "Hassi R'mel")

# ===================== MULTI-SITES =====================
sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}
selected_site = st.sidebar.selectbox("Choisir le site pour analyse multi-sites", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    raise ValueError("Aucune colonne CH4 détectée")

# ===================== SESSION STATE =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
    st.session_state.results = {}

# ===================== FUNCTIONS =====================
def get_latest_ch4(lat, lon, days_back=90):
    geom = ee.Geometry.Point([lon, lat]).buffer(3500)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )
    if col.size().getInfo() == 0:
        return None, None
    imgs = col.toList(col.size())
    for i in range(col.size().getInfo()):
        img = ee.Image(imgs.get(i))
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        val = img.reduceRegion(
            ee.Reducer.mean(), geom, 7000, maxPixels=1e9
        ).getInfo().get("CH4_column_volume_mixing_ratio_dry_air")
        if val:
            return val * 1000, date_img
    return None, None

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

def log_hse_alert(site, lat, lon, ch4, z, risk, decision):
    log_path = "alerts_hse.csv"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "datetime_utc": now,
        "site": site,
        "latitude": lat,
        "longitude": lon,
        "ch4_ppb": round(ch4, 2),
        "z_score": round(z, 2),
        "risk": risk,
        "decision": decision
    }
    if os.path.exists(log_path):
        df = pd.read_csv(log_path)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(log_path, index=False)

# ===================== GEE FLARES =====================
def get_active_flares(lat, lon, days_back=7):
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    fires = (
        ee.ImageCollection("NOAA/VIIRS/001/VNP14IMGTDL_NRT")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("Bright_ti4")
    )
    def to_point(img):
        return img.gt(330).selfMask().reduceToVectors(
            geometry=geom,
            scale=375,
            geometryType="centroid",
            maxPixels=1e9
        )
    flares = fires.map(to_point).flatten()
    return flares

def attribute_ch4_source(lat, lon):
    flares = get_active_flares(lat, lon)
    result = {"flares": flares, "n_flares": 0, "source": "", "icon": ""}
    def cb(n):
        result["n_flares"] = n
        if n > 0:
            result["source"] = "Torches détectées"
            result["icon"] = "🔥"
        else:
            result["source"] = "Aucune torche détectée"
            result["icon"] = "❓"
    flares.size().evaluate(cb)
    return result
