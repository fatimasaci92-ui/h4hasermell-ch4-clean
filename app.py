# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import ee
import json
import tempfile
import os
from datetime import datetime
import folium
from streamlit_folium import st_folium
import rasterio
from rasterio.plot import show
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

# ===================== GEE INIT =====================
try:
    key_path = "methane-ai-hse-a85cc13c510a.json"  # JSON local
    credentials = ee.ServiceAccountCredentials(None, key_file=key_path)
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

def generate_hse_pdf(results, site, lat, lon):
    path = f"/tmp/Rapport_CH4_HSE_{site.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("Rapport HSE – Surveillance du Méthane (CH₄)", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Site :</b> {site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Coordonnées :</b> {lat}, {lon}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date des données :</b> {results['date_img']}", styles["Normal"]))
    elements.append(Spacer(1, 12))
    table = Table([
        ["Indicateur", "Valeur"],
        ["CH₄ (ppb)", f"{results['ch4']:.1f}"],
        ["Z-score", f"{results['z']:.2f}"],
        ["Niveau de risque", results["risk"]],
        ["Action recommandée", results["decision"]],
    ], colWidths=[220, 250])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightblue),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "Limites : Données satellitaires à résolution kilométrique. "
        "Validation terrain obligatoire.",
        styles["Italic"]
    ))
    doc.build(elements)
    return path

def send_email_alert(to_email, subject, body):
    try:
        smtp_server = st.secrets["SMTP_SERVER"]
        smtp_port = st.secrets["SMTP_PORT"]
        smtp_user = st.secrets["SMTP_USER"]
        smtp_pass = st.secrets["SMTP_PASS"]
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
    except Exception as e:
        st.warning(f"Impossible d'envoyer email: {e}")

# ===================== GEE Flares =====================
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

# ===================== ANALYSIS =====================
if st.button("🚀 Lancer l’analyse"):
    ch4, date_img = get_latest_ch4(lat_site, lon_site)
    series = get_ch4_series(df_hist)

    if ch4 is None:
        st.warning("Donnée satellite indisponible – utilisation CSV")
        ch4 = series.iloc[-1]
        date_img = "Historique CSV"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk, decision, color = "Critique", "Alerte HSE immédiate", "red"
        log_hse_alert(selected_site, lat_site, lon_site, ch4, z, risk, decision)
    elif z > 2:
        risk, decision, color = "Anomalie", "Inspection terrain requise", "orange"
    else:
        risk, decision, color = "Normal", "Surveillance continue", "green"

    st.session_state.analysis_done = True
    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date_img": date_img,
        "site": selected_site
    }

# ===================== RESULTS =====================
if st.session_state.analysis_done:
    r = st.session_state.results
    if r["risk"] == "Critique":
        st.error("🚨 ALERTE HSE CRITIQUE — ACTION IMMÉDIATE")
    c1, c2 = st.columns(2)
    c1.metric("CH₄ (ppb)", round(r["ch4"], 1))
    c2.metric("Z-score", round(r["z"], 2))
    st.markdown(
        f"<h3 style='color:{r['color']}'>Risque : {r['risk']}</h3>"
        f"<b>Action :</b> {r['decision']}",
        unsafe_allow_html=True
    )
    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)
    folium.Circle([lat_site, lon_site], 3500, color=r["color"], fill=True).add_to(m)
    folium.Marker([lat_site, lon_site], tooltip=selected_site).add_to(m)
    st_folium(m, width=750, height=450)

    # Attribution des torches
    flare_info = attribute_ch4_source(lat_site, lon_site)
    st.markdown(f"### {flare_info['icon']} Attribution de la source")
    st.info(f"{flare_info['source']} — Nombre : {flare_info['n_flares']}")

    # Décision automatique
    if r["z"] > 2 and flare_info["n_flares"] > 0:
        r["decision"] = "Élévation CH₄ probablement liée aux torches"
    elif r["z"] > 2 and flare_info["n_flares"] == 0:
        r["decision"] = "Élévation CH₄ NON expliquée par les torches – suspicion fuite"

    if st.button("📄 Générer le PDF HSE"):
        pdf = generate_hse_pdf(r, selected_site, lat_site, lon_site)
        with open(pdf, "rb") as f:
            st.download_button("⬇️ Télécharger PDF", f, file_name=os.path.basename(pdf))

# ===================== HISTORIQUE DES ALERTES =====================
st.markdown("## 📋 Historique des alertes HSE")
if os.path.exists("alerts_hse.csv"):
    df_alerts = pd.read_csv("alerts_hse.csv")
    st.dataframe(df_alerts, use_container_width=True)
    st.download_button("⬇️ Télécharger le journal des alertes",
                       df_alerts.to_csv(index=False),
                       file_name="alerts_hse.csv",
                       mime="text/csv")
else:
    st.info("Aucune alerte critique enregistrée.")

# ===================== GRAPHIQUE TEMPOREL =====================
st.markdown("## 📈 Évolution CH₄ historique")
ch4_series = get_ch4_series(df_hist)
df_hist_plot = df_hist.copy()
df_hist_plot["CH4_ppb"] = ch4_series
df_hist_plot["date"] = pd.to_datetime(df_hist_plot.iloc[:,0])
fig = px.line(df_hist_plot, x="date", y="CH4_ppb", title=f"Évolution CH₄ – {selected_site}")
fig.add_hline(y=ch4_series.mean(), line_dash="dash", line_color="green", annotation_text="Moyenne")
fig.add_hrect(y0=ch4_series.mean()-2*ch4_series.std(), y1=ch4_series.mean()+2*ch4_series.std(),
              fillcolor="lightgreen", opacity=0.2, line_width=0)
if st.session_state.analysis_done:
    r = st.session_state.results
    fig.add_scatter(
        x=[datetime.utcnow()],
        y=[r["ch4"]],
        mode="markers",
        marker=dict(color="red", size=12),
        name="Analyse du jour"
    )
st.plotly_chart(fig, use_container_width=True)

# ===================== ASSISTANT IA =====================
st.markdown("## 🤖 Assistant HSE / CH₄")
question = st.text_input("Question HSE / CH₄")
if st.button("Analyser la question"):
    if "risque" in question.lower():
        st.info("Le risque est basé sur le z-score de l’anomalie.")
    elif "graphique" in question.lower():
        st.info("Le graphique montre l’évolution historique et la position du dernier point.")
    elif "satellite" in question.lower():
        st.info("Sentinel-5P fournit la surveillance quotidienne régionale.")
    else:
        st.info("Analyse basée sur télédétection, historique CH₄ et règles HSE.")
