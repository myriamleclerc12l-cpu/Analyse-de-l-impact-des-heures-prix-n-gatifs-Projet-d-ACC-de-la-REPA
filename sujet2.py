# -*- coding: utf-8 -*-
"""
Created on Wed Jul 29 16:19:54 2026

@author: stagiaire
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Analyse Prix Négatifs & Coupures", layout="wide")

# ==========================================================
# FONCTIONS UTILITAIRES
# ==========================================================

def fmt_fr(x, decimales=0):
    if pd.isna(x):
        return ""
    s = f"{x:,.{decimales}f}"
    s = s.replace(",", " ")
    return s

def carte_indicateur(titre, valeur, couleur_fond, couleur_accent, taille_titre=14, taille_valeur=28, aide=None):
    aide_html = f'<span title="{aide}" style="cursor: help; opacity: 0.55;"> ⓘ</span>' if aide else ""
    return f"""
    <div style="background-color:{couleur_fond}; border-left:5px solid {couleur_accent};
                border-radius:10px; padding:14px 18px; margin-bottom:8px;">
        <div style="font-size:{taille_titre}px; color:#555; margin-bottom:4px;">{titre}{aide_html}</div>
        <div style="font-size:{taille_valeur}px; font-weight:700; color:{couleur_accent};">{valeur}</div>
    </div>
    """

COL_PRIX_POS = "Prix de Règlements des Ecarts Positifs (Euros/MWh)"
COL_PRIX_NEG = "Prix de Règlements des Ecarts Négatifs (Euros/MWh)"
COL_DESEQ = "Déséquilibre(MWh)"

@st.cache_data
def charger_donnees(fichier):
    df = pd.read_excel(fichier, sheet_name=0)
    df = df[df["Heure de début"] != "Total"].copy()
    df = df.dropna(subset=["Heure de début"])
    df["Heure de début"] = pd.to_datetime(df["Heure de début"])
    df = df.rename(columns={
        COL_PRIX_POS: "Prix_Positifs",
        COL_PRIX_NEG: "Prix_Negatifs",
        COL_DESEQ: "Desequilibre",
        "Temps Coupure": "Temps_Coupure_Fichier",
    })
    df = df.set_index("Heure de début").sort_index()
    return df[["Desequilibre", "Tendance", "Prix_Positifs", "Prix_Negatifs", "Temps_Coupure_Fichier"]]

@st.cache_data
def detecter_episodes(df_periode, colonne_coupure):
    en_coupure = df_periode[colonne_coupure] > 0
    if not en_coupure.any():
        return pd.DataFrame(columns=["Début", "Fin", "Durée (h)"])
    groupe = (en_coupure != en_coupure.shift()).cumsum()
    episodes = df_periode[en_coupure].groupby(groupe[en_coupure]).agg(
        **{
            "Début": (colonne_coupure, lambda x: x.index.min()),
            "Fin": (colonne_coupure, lambda x: x.index.max() + pd.Timedelta(minutes=15)),
            "Durée (h)": (colonne_coupure, "sum"),
        }
    )
    return episodes.sort_values("Durée (h)", ascending=False).reset_index(drop=True)

# ==========================================================
# BARRE LATÉRALE — IMPORT ET RÉGLAGES
# ==========================================================

st.sidebar.header("Données")
fichier = st.sidebar.file_uploader("Fichier Excel — Règlement des Écarts", type=["xlsx"])

if fichier is None:
    st.title("Analyse des Prix Négatifs et des Coupures")
    st.info("Merci d'importer le fichier Excel du Règlement des Écarts (colonnes : Heure de début/fin, "
            "Déséquilibre, Tendance, Prix de Règlements des Écarts Positifs/Négatifs) pour commencer.")
    st.stop()

df_complet = charger_donnees(fichier)

st.sidebar.markdown("---")
st.sidebar.header("Période d'analyse")
date_min, date_max = df_complet.index.min().date(), df_complet.index.max().date()
col_d1, col_d2 = st.sidebar.columns(2)
date_debut = col_d1.date_input("Début", value=date_min, min_value=date_min, max_value=date_max)
date_fin = col_d2.date_input("Fin", value=date_max, min_value=date_min, max_value=date_max)

st.sidebar.markdown("---")
st.sidebar.header("Seuil de coupure")
seuil_coupure = st.sidebar.number_input(
    "Prix de Règlement des Écarts Positifs (€/MWh)", min_value=-500.0, max_value=0.0,
    value=-3.0, step=0.5, key="seuil_coupure_input",
    help="Un pas de 15 min est considéré en coupure si le Prix de Règlement des Écarts Positifs "
         "descend à ce seuil ou en dessous. Recalculé dynamiquement — le seuil d'origine du fichier "
         "Excel est -3 €/MWh."
)

df = df_complet.loc[str(date_debut):str(date_fin)].copy()
if df.empty:
    st.warning("Aucune donnée sur la période sélectionnée.")
    st.stop()

df["Temps_Coupure"] = np.where(df["Prix_Positifs"] <= seuil_coupure, 0.25, 0.0)
dt_h = 0.25  # pas de temps natif du fichier (15 min)

st.title("Analyse des Prix Négatifs et des Coupures")
st.caption(f"Période analysée : du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')} "
           f"— seuil de coupure appliqué : {fmt_fr(seuil_coupure, 1)} €/MWh")

tab1, tab2, tab3 = st.tabs(["Vue d'ensemble", "Analyse des Prix Négatifs", "Analyse des Coupures"])

# ==========================================================
# ONGLET 1 : VUE D'ENSEMBLE
# ==========================================================
with tab1:
    nb_pas = len(df)
    nb_jours = (date_fin - date_debut).days + 1
    temps_coupure_total = df["Temps_Coupure"].sum()
    pct_coupure = temps_coupure_total / (nb_pas * dt_h) * 100 if nb_pas > 0 else 0
    nb_pas_negatif = (df["Prix_Positifs"] < 0).sum()
    pct_negatif = nb_pas_negatif / nb_pas * 100 if nb_pas > 0 else 0
    prix_moyen_pos = df["Prix_Positifs"].mean()
    prix_min = df["Prix_Positifs"].min()
    date_prix_min = df["Prix_Positifs"].idxmin()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(carte_indicateur("Temps de coupure total", f"{fmt_fr(temps_coupure_total)} h",
            "#FFEBEE", "#C62828",
            aide=f"Soit {fmt_fr(temps_coupure_total/24, 1)} jours équivalents, {fmt_fr(pct_coupure, 1)} % du temps."),
            unsafe_allow_html=True)
    with col2:
        st.markdown(carte_indicateur("Pas de temps à prix négatif", f"{fmt_fr(nb_pas_negatif)}",
            "#FFF3E0", "#E65100", aide=f"{fmt_fr(pct_negatif, 1)} % des {fmt_fr(nb_pas)} pas de 15 min analysés."),
            unsafe_allow_html=True)
    with col3:
        st.markdown(carte_indicateur("Prix moyen (Écarts Positifs)", f"{fmt_fr(prix_moyen_pos, 2)} €/MWh",
            "#E3F2FD", "#1565C0"), unsafe_allow_html=True)
    with col4:
        st.markdown(carte_indicateur("Prix le plus négatif atteint", f"{fmt_fr(prix_min, 2)} €/MWh",
            "#F3E5F5", "#6A1B9A", aide=f"Atteint le {date_prix_min.strftime('%d/%m/%Y à %Hh%M')}."),
            unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Vue mensuelle — coupures et prix négatifs")

    df_mensuel = df.copy()
    df_mensuel["mois"] = df_mensuel.index.to_period("M").astype(str)
    agg_mensuel = df_mensuel.groupby("mois").agg(
        temps_coupure=("Temps_Coupure", "sum"),
        pct_negatif=("Prix_Positifs", lambda x: (x < 0).mean() * 100),
    ).reset_index()

    fig_overview = make_subplots(specs=[[{"secondary_y": True}]])
    fig_overview.add_trace(go.Bar(x=agg_mensuel["mois"], y=agg_mensuel["temps_coupure"],
        name="Temps de coupure (h)", marker_color="#C62828"), secondary_y=False)
    fig_overview.add_trace(go.Scatter(x=agg_mensuel["mois"], y=agg_mensuel["pct_negatif"],
        name="Part du temps à prix négatif (%)", mode="lines+markers",
        line=dict(color="#1565C0", width=3)), secondary_y=True)
    fig_overview.update_layout(title="Temps de coupure et fréquence des prix négatifs, par mois",
        hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
    fig_overview.update_yaxes(title_text="Temps de coupure (h)", secondary_y=False)
    fig_overview.update_yaxes(title_text="Part du temps à prix négatif (%)", secondary_y=True)
    st.plotly_chart(fig_overview, use_container_width=True)

# ==========================================================
# ONGLET 2 : ANALYSE DES PRIX NÉGATIFS
# ==========================================================
with tab2:
    st.subheader("Distribution et dynamique des prix")

    df_neg = df[df["Prix_Positifs"] < 0]
    col_n1, col_n2, col_n3, col_n4 = st.columns(4)
    with col_n1:
        st.markdown(carte_indicateur("Pas à prix négatif", f"{fmt_fr(len(df_neg))}",
            "#FFF3E0", "#E65100", aide=f"{fmt_fr(len(df_neg)/nb_pas*100, 1)} % de la période."),
            unsafe_allow_html=True)
    with col_n2:
        st.markdown(carte_indicateur("Prix négatif moyen", f"{fmt_fr(df_neg['Prix_Positifs'].mean(), 2)} €/MWh"
            if len(df_neg) > 0 else "N/A", "#FFF3E0", "#E65100"), unsafe_allow_html=True)
    with col_n3:
        st.markdown(carte_indicateur("Écart Positifs vs Négatifs (moyenne)",
            f"{fmt_fr((df['Prix_Negatifs']-df['Prix_Positifs']).mean(), 2)} €/MWh",
            "#E8F5E9", "#2E7D32",
            aide="Écart moyen entre le Prix de Règlement des Écarts Négatifs et Positifs sur la période."),
            unsafe_allow_html=True)
    with col_n4:
        st.markdown(carte_indicateur("Prix maximum atteint", f"{fmt_fr(df['Prix_Positifs'].max(), 2)} €/MWh",
            "#E3F2FD", "#1565C0"), unsafe_allow_html=True)

    st.markdown("---")
    fig_ts = go.Figure()
    fig_ts.add_trace(go.Scatter(x=df.index, y=df["Prix_Positifs"], mode="lines",
        name="Prix Écarts Positifs", line=dict(color="#1565C0", width=1.2)))
    fig_ts.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_ts.add_hline(y=seuil_coupure, line_dash="dash", line_color="#C62828",
        annotation_text=f"Seuil de coupure ({fmt_fr(seuil_coupure,1)} €/MWh)")
    fig_ts.update_layout(title="Évolution du Prix de Règlement des Écarts Positifs sur la période",
        xaxis_title="Date", yaxis_title="€/MWh", hovermode="x unified")
    st.plotly_chart(fig_ts, use_container_width=True)

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Prix_Positifs"], nbinsx=80, marker_color="#1565C0"))
        fig_hist.add_vline(x=0, line_dash="dot", line_color="gray")
        fig_hist.update_layout(title="Distribution du prix (Écarts Positifs)",
            xaxis_title="€/MWh", yaxis_title="Nombre de pas de 15 min")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_h2:
        df_heat = df.copy()
        df_heat["heure"] = df_heat.index.hour
        df_heat["jour_semaine"] = df_heat.index.dayofweek
        jours_labels = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        pivot_neg = df_heat.pivot_table(index="jour_semaine", columns="heure",
            values="Prix_Positifs", aggfunc=lambda x: (x < 0).mean() * 100)
        fig_heat = go.Figure(data=go.Heatmap(
            z=pivot_neg.values, x=pivot_neg.columns, y=[jours_labels[i] for i in pivot_neg.index],
            colorscale="Reds", colorbar=dict(title="% négatif")))
        fig_heat.update_layout(title="Fréquence des prix négatifs par heure et jour de la semaine",
            xaxis_title="Heure de la journée", yaxis_title="")
        st.plotly_chart(fig_heat, use_container_width=True)

    st.subheader("Événements de prix les plus extrêmes")
    top_negatifs = df.nsmallest(10, "Prix_Positifs")[["Prix_Positifs", "Prix_Negatifs", "Desequilibre", "Tendance"]]
    top_negatifs.index.name = "Date"
    st.dataframe(top_negatifs.style.format({
        "Prix_Positifs": lambda x: f"{fmt_fr(x, 2)} €/MWh",
        "Prix_Negatifs": lambda x: f"{fmt_fr(x, 2)} €/MWh",
        "Desequilibre": lambda x: f"{fmt_fr(x, 1)} MWh",
    }), use_container_width=True)

# ==========================================================
# ONGLET 3 : ANALYSE DES COUPURES
# ==========================================================
with tab3:
    episodes = detecter_episodes(df, "Temps_Coupure")

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        st.markdown(carte_indicateur("Temps de coupure total", f"{fmt_fr(temps_coupure_total)} h",
            "#FFEBEE", "#C62828"), unsafe_allow_html=True)
    with col_c2:
        st.markdown(carte_indicateur("Nombre d'épisodes", f"{fmt_fr(len(episodes))}",
            "#FFEBEE", "#C62828"), unsafe_allow_html=True)
    with col_c3:
        duree_moy = episodes["Durée (h)"].mean() if len(episodes) > 0 else 0
        st.markdown(carte_indicateur("Durée moyenne d'un épisode", f"{fmt_fr(duree_moy, 2)} h",
            "#FFF3E0", "#E65100"), unsafe_allow_html=True)
    with col_c4:
        duree_max = episodes["Durée (h)"].max() if len(episodes) > 0 else 0
        st.markdown(carte_indicateur("Épisode le plus long", f"{fmt_fr(duree_max, 2)} h",
            "#F3E5F5", "#6A1B9A"), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Répartition mensuelle du temps de coupure")
    df_mois_c = df.copy()
    df_mois_c["mois"] = df_mois_c.index.to_period("M").astype(str)
    coupure_mensuelle = df_mois_c.groupby("mois")["Temps_Coupure"].sum().reset_index()
    fig_mensuel_c = go.Figure(go.Bar(x=coupure_mensuelle["mois"], y=coupure_mensuelle["Temps_Coupure"],
        marker_color="#C62828"))
    fig_mensuel_c.update_layout(title="Temps de coupure par mois", xaxis_title="Mois",
        yaxis_title="Heures de coupure")
    st.plotly_chart(fig_mensuel_c, use_container_width=True)

    col_hc1, col_hc2 = st.columns(2)
    with col_hc1:
        df_heat_c = df.copy()
        df_heat_c["heure"] = df_heat_c.index.hour
        df_heat_c["jour_semaine"] = df_heat_c.index.dayofweek
        jours_labels = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        pivot_c = df_heat_c.pivot_table(index="jour_semaine", columns="heure",
            values="Temps_Coupure", aggfunc="sum")
        fig_heat_c = go.Figure(data=go.Heatmap(
            z=pivot_c.values, x=pivot_c.columns, y=[jours_labels[i] for i in pivot_c.index],
            colorscale="Reds", colorbar=dict(title="Heures")))
        fig_heat_c.update_layout(title="Temps de coupure cumulé par heure et jour de la semaine",
            xaxis_title="Heure de la journée", yaxis_title="")
        st.plotly_chart(fig_heat_c, use_container_width=True)

    with col_hc2:
        st.markdown("**Sensibilité au seuil de coupure**")
        seuils_test = list(range(0, -55, -5))
        heures_par_seuil = [(df["Prix_Positifs"] <= s).sum() * dt_h for s in seuils_test]
        fig_sensib = go.Figure(go.Scatter(x=seuils_test, y=heures_par_seuil, mode="lines+markers",
            line=dict(color="#6A1B9A", width=3)))
        fig_sensib.add_vline(x=seuil_coupure, line_dash="dash", line_color="#C62828",
            annotation_text="Seuil actuel")
        fig_sensib.update_layout(title="Temps de coupure total selon le seuil retenu",
            xaxis_title="Seuil de coupure (€/MWh)", yaxis_title="Heures de coupure sur la période")
        st.plotly_chart(fig_sensib, use_container_width=True)

    st.subheader("Épisodes de coupure les plus longs")
    if len(episodes) > 0:
        top_episodes = episodes.head(15).copy()
        top_episodes["Début"] = top_episodes["Début"].dt.strftime("%d/%m/%Y %H:%M")
        top_episodes["Fin"] = top_episodes["Fin"].dt.strftime("%d/%m/%Y %H:%M")
        st.dataframe(top_episodes.style.format({"Durée (h)": lambda x: fmt_fr(x, 2)}),
            use_container_width=True, hide_index=True)
    else:
        st.info("Aucun épisode de coupure sur la période et le seuil sélectionnés.")