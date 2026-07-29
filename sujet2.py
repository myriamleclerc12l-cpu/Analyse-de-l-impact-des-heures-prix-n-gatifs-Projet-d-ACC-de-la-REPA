# -*- coding: utf-8 -*-
"""
Created on Wed Jul 29 16:19:54 2026

@author: stagiaire
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import os

# Configuration de la page
st.set_page_config(page_title="Analyse Prix PMO/REPA", layout="wide", page_icon="⚡")

# Titre de l'application
st.title("⚡ Analyse des prix de vente au réseau")
st.markdown("Ce tableau de bord permet d'identifier rapidement les périodes où le prix de vente est **négatif**.")

# Nom du fichier défini en dur selon votre demande
FILE_NAME = "PMO_REPA_AnalyseCoupure.xlsx"

@st.cache_data
def load_data(file_path):
    """Charge les données Excel en cache pour optimiser la vitesse."""
    return pd.read_excel(file_path)

# Vérification de la présence du fichier
if os.path.exists(FILE_NAME):
    try:
        df = load_data(FILE_NAME)
        st.sidebar.success(f"Fichier `{FILE_NAME}` chargé avec succès !")
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")
        st.stop()
else:
    st.error(f"Le fichier `{FILE_NAME}` est introuvable dans le dossier actuel.")
    st.info("Veuillez vous assurer que le fichier Excel se trouve dans le même dossier que ce script (app.py) ou utilisez le module de secours ci-dessous.")
    
    # Solution de secours : upload manuel si le fichier n'est pas trouvé
    uploaded_file = st.file_uploader(f"Chargez {FILE_NAME} manuellement", type=["xlsx", "xls"])
    if uploaded_file is not None:
        df = load_data(uploaded_file)
    else:
        st.stop()

# ==========================================
# CONFIGURATION DES COLONNES (Menu Latéral)
# ==========================================
st.sidebar.header("⚙️ Configuration des données")
st.sidebar.markdown("Sélectionnez les colonnes correspondantes à la date et au prix :")

# Tente de deviner les colonnes par défaut pour faciliter l'utilisation
col_names = df.columns.tolist()
default_date_idx = 0
default_price_idx = 1 if len(col_names) > 1 else 0

date_col = st.sidebar.selectbox("Colonne Date/Heure", col_names, index=default_date_idx)
price_col = st.sidebar.selectbox("Colonne Prix", col_names, index=default_price_idx)

# Nettoyage et préparation des données
try:
    df_clean = df.copy()
    # Conversion de la colonne sélectionnée en format DateTime
    df_clean[date_col] = pd.to_datetime(df_clean[date_col])
    # Tri chronologique
    df_clean = df_clean.sort_values(by=date_col)
    
    # Création d'une catégorie pour gérer les couleurs dans Plotly
    df_clean['Statut du prix'] = df_clean[price_col].apply(lambda x: 'Négatif (<= 0)' if x <= 0 else 'Positif (> 0)')
except Exception as e:
    st.error(f"Erreur lors du traitement des colonnes. Vérifiez que la colonne Date contient bien des dates et la colonne Prix des nombres. Détail : {e}")
    st.stop()

# ==========================================
# AFFICHAGE DES INDICATEURS (KPIs)
# ==========================================
st.header("📊 Résumé des prix")

# Filtre par date (optionnel) pour zoomer sur une période
min_date = df_clean[date_col].min().date()
max_date = df_clean[date_col].max().date()

date_range = st.date_input(
    "Filtrer par période",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Appliquer le filtre si l'utilisateur a sélectionné un début et une fin
if len(date_range) == 2:
    start_date, end_date = date_range
    # Convertir en datetime pour comparer avec la colonne de données
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    
    mask = (df_clean[date_col] >= start_dt) & (df_clean[date_col] <= end_dt)
    df_filtered = df_clean.loc[mask]
else:
    df_filtered = df_clean

# Calcul des métriques sur les données filtrées
nb_total = len(df_filtered)
nb_negative = len(df_filtered[df_filtered[price_col] <= 0])
pct_negative = (nb_negative / nb_total * 100) if nb_total > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Données analysées", f"{nb_total}")
col2.metric("Fréquence prix négatifs", f"{nb_negative}", f"{pct_negative:.1f}% du temps", delta_color="inverse")
col3.metric("Prix Minimum", f"{df_filtered[price_col].min():.2f} €")
col4.metric("Prix Maximum", f"{df_filtered[price_col].max():.2f} €")

# ==========================================
# GRAPHIQUE INTERACTIF
# ==========================================
st.header("📈 Évolution du prix (Visualisation Positif / Négatif)")

# Utilisation d'un graphique en barres (idéal pour voir les passages sous zéro)
fig = px.bar(
    df_filtered,
    x=date_col,
    y=price_col,
    color='Statut du prix',
    color_discrete_map={
        'Positif (> 0)': '#2ecc71', # Vert
        'Négatif (<= 0)': '#e74c3c'  # Rouge
    },
    title="Prix de vente sur le réseau au cours du temps",
    labels={price_col: "Prix (€)", date_col: "Date & Heure"}
)

fig.update_layout(
    xaxis_title="",
    yaxis_title="Prix (€)",
    legend_title="Légende",
    hovermode="x unified",
    bargap=0 # Supprime l'espace entre les barres pour un aspect "courbe pleine"
)

# Ligne horizontale à 0 pour bien marquer la limite
fig.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)

st.plotly_chart(fig, use_container_width=True)

# ==========================================
# TABLEAU DE DONNÉES FILTRÉES
# ==========================================
with st.expander("🔎 Afficher le détail des données brutes"):
    st.dataframe(
        df_filtered.style.applymap(
            lambda x: 'color: red;' if isinstance(x, (int, float)) and x <= 0 else '',
            subset=[price_col]
        ),
        use_container_width=True
    )