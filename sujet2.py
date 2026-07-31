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
def resample_pour_affichage(serie):
    """Réduit le nombre de points affichés selon la durée de la période, pour garder le graphique lisible."""
    duree_jours = (serie.index.max() - serie.index.min()).days + 1
    if duree_jours <= 3:
        return serie
    elif duree_jours <= 14:
        return serie.resample("2h").mean()
    elif duree_jours <= 60:
        return serie.resample("1D").mean()
    elif duree_jours <= 200:
        return serie.resample("3D").mean()
    else:
        return serie.resample("1W").mean()
    
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

def charger_courbe_w(fichier):
    nom_fichier = getattr(fichier, "name", str(fichier))
    if nom_fichier.lower().endswith(".csv"):
        df_c = pd.read_csv(fichier, sep=None, engine="python")
    else:
        df_c = pd.read_excel(fichier)
    df_c = df_c.iloc[:, :2].copy()
    df_c.columns = ["timestamp", "value_W"]

    if pd.api.types.is_datetime64_any_dtype(df_c["timestamp"]):
        df_c["timestamp"] = pd.to_datetime(df_c["timestamp"])
    else:
        ts = pd.to_datetime(df_c["timestamp"], format="ISO8601", utc=True, errors="coerce")
        if ts.isna().mean() > 0.5:
            ts = pd.to_datetime(df_c["timestamp"], dayfirst=True, utc=True, errors="coerce")
        if isinstance(ts.dtype, pd.DatetimeTZDtype):
            ts = ts.dt.tz_localize(None)
        df_c["timestamp"] = ts

    if not pd.api.types.is_numeric_dtype(df_c["value_W"]):
        df_c["value_W"] = df_c["value_W"].astype(str).str.replace(",", ".", regex=False)
    df_c["value_W"] = pd.to_numeric(df_c["value_W"], errors="coerce")

    df_c = df_c.dropna(subset=["timestamp", "value_W"])
    df_c = df_c.drop_duplicates(subset=["timestamp"], keep="first")  # anomalies d'export (date non incrémentée)
    df_c = df_c.set_index("timestamp").sort_index()
    serie = df_c["value_W"]
    pas_natif = serie.index.to_series().diff().median()
    if pd.notna(pas_natif) and pas_natif != pd.Timedelta(minutes=30):
        if pas_natif < pd.Timedelta(minutes=30):
            serie = serie.resample("30min").mean()
        else:
            serie = serie.resample("30min").ffill()
    return serie

def sommer_courbes(fichiers):
    series_list = [charger_courbe_w(f).rename(f.name) for f in fichiers]
    df_toutes = pd.concat(series_list, axis=1)
    return df_toutes.sum(axis=1, skipna=True)

def charger_toutes_courbes(fichiers):
    """Charge chaque fichier individuellement. Retourne (dict {nom: série}, série totale sommée)."""
    courbes = {}
    for f in fichiers:
        courbes[f.name] = charger_courbe_w(f)
    df_toutes = pd.concat(courbes.values(), axis=1, keys=courbes.keys())
    somme = df_toutes.sum(axis=1, skipna=True)
    return courbes, somme

# ==========================================================
# BARRE LATÉRALE — IMPORT ET RÉGLAGES
# ==========================================================
st.sidebar.header("Données — Prix")
fichier = st.sidebar.file_uploader("Fichier Excel — Règlement des Écarts", type=["xlsx"])

if fichier is None:
    st.title("Analyse des Prix Négatifs et des Coupures")
    st.info("Merci d'importer le fichier Excel du Règlement des Écarts (colonnes : Heure de début/fin, "
            "Déséquilibre, Tendance, Prix de Règlements des Écarts Positifs/Négatifs) pour commencer.")
    st.stop()

df_complet = charger_donnees(fichier)
date_min, date_max = df_complet.index.min().date(), df_complet.index.max().date()
date_debut, date_fin = date_min, date_max

st.sidebar.markdown("---")
st.sidebar.header("Seuil de coupure")
seuil_coupure = st.sidebar.number_input(
    "Prix de Règlement des Écarts Positifs (€/MWh)", min_value=-500.0, max_value=0.0,
    value=-3.0, step=0.5, key="seuil_coupure_input",
    help="Un pas de 15 min est considéré en coupure si le Prix de Règlement des Écarts Positifs "
         "descend à ce seuil ou en dessous. Recalculé dynamiquement — le seuil d'origine du fichier "
         "Excel est -3 €/MWh."
)

st.sidebar.markdown("---")
st.sidebar.header("Données — Production / Consommation")
st.sidebar.caption("Optionnel — nécessaire uniquement pour l'onglet « Impact Production/Consommation ». "
                    "Colonnes attendues : timestamp, value (en W).")
fichiers_prod = st.sidebar.file_uploader("Courbes de production (une ou plusieurs)", type=["xlsx", "csv"],
    accept_multiple_files=True, key="fichiers_prod_uploader")
fichiers_conso = st.sidebar.file_uploader("Courbes de consommation (une ou plusieurs)", type=["xlsx", "csv"],
    accept_multiple_files=True, key="fichiers_conso_uploader")

types_conso = {}
if fichiers_conso:
    st.sidebar.caption("Type de raccordement, par site de consommation :")
    for f in fichiers_conso:
        types_conso[f.name] = st.sidebar.radio(f.name, ["ACI", "ACC"],
            horizontal=True, key=f"type_conso_{f.name}",
            help="ACI = Autoconsommation Individuelle (le site consomme uniquement sa propre production "
                 "dédiée). ACC = Autoconsommation Collective (le site fait partie de la boucle partagée "
                 "avec les autres sites).")

df = df_complet.loc[str(date_debut):str(date_fin)].copy()
if df.empty:
    st.warning("Aucune donnée sur la période sélectionnée.")
    st.stop()

df["Temps_Coupure"] = np.where(df["Prix_Positifs"] <= seuil_coupure, 0.25, 0.0)
dt_h = 0.25  # pas de temps natif du fichier (15 min)

st.title("Analyse des Prix Négatifs et des Coupures")
st.caption(f"Période analysée : du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')} "
           f"— seuil de coupure appliqué : {fmt_fr(seuil_coupure, 1)} €/MWh")

tab1, tab2, tab3, tab4 = st.tabs(["Vue d'ensemble", "Analyse des Prix Négatifs", "Analyse des Coupures",
    "Impact Production/Consommation"])

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
    nb_pas_coupure = (df["Prix_Positifs"] <= seuil_coupure).sum()
    pct_coupure_pas = nb_pas_coupure / nb_pas * 100 if nb_pas > 0 else 0
    prix_moyen_pos = df["Prix_Positifs"].mean()
    prix_min = df["Prix_Positifs"].min()
    date_prix_min = df["Prix_Positifs"].idxmin()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(carte_indicateur("Temps de coupure total", f"{fmt_fr(temps_coupure_total)} h",
            "#FFEBEE", "#C62828",
            aide=f"Seuil : {fmt_fr(seuil_coupure, 1)} €/MWh. Soit {fmt_fr(temps_coupure_total/24, 1)} "
                 f"jours équivalents, {fmt_fr(pct_coupure, 1)} % du temps."),
            unsafe_allow_html=True)
    with col2:
        st.markdown(carte_indicateur("Pas en coupure", f"{fmt_fr(nb_pas_coupure)}",
            "#FFEBEE", "#C62828",
            aide=f"{fmt_fr(pct_coupure_pas, 1)} % des pas, au seuil de {fmt_fr(seuil_coupure, 1)} €/MWh "
                 f"(réglable dans la barre latérale)."),
            unsafe_allow_html=True)
    with col3:
        st.markdown(carte_indicateur("Pas à prix négatif", f"{fmt_fr(nb_pas_negatif)}",
            "#FFF3E0", "#E65100",
            aide=f"{fmt_fr(pct_negatif, 1)} % des pas. Tout prix < 0 €/MWh — critère plus large que le "
                 f"seuil de coupure ci-contre."),
            unsafe_allow_html=True)
    with col4:
        st.markdown(carte_indicateur("Prix moyen (Écarts Positifs)", f"{fmt_fr(prix_moyen_pos, 2)} €/MWh",
            "#E3F2FD", "#1565C0",
            aide="Moyenne du Prix de Règlement des Écarts Positifs sur toute la période — le prix "
                 "auquel votre surplus de production serait valorisé, en moyenne."), unsafe_allow_html=True)
    with col5:
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
    nb_pas = len(df)
    df_neg = df[df["Prix_Positifs"] < 0]
    df_coupure_t2 = df[df["Prix_Positifs"] <= seuil_coupure]
    st.subheader("Distribution et dynamique des prix")
    df_neg = df[df["Prix_Positifs"] < 0]
    df_coupure_t2 = df[df["Prix_Positifs"] <= seuil_coupure]
    col_n1, col_n2, col_n3, col_n4 = st.columns(4)
    with col_n1:
        st.markdown(carte_indicateur("Pas en coupure", f"{fmt_fr(len(df_coupure_t2))}",
            "#FFEBEE", "#C62828",
            aide=f"{fmt_fr(len(df_coupure_t2)/nb_pas*100, 1)} % de la période, au seuil de "
                 f"{fmt_fr(seuil_coupure, 1)} €/MWh."), unsafe_allow_html=True)
    with col_n2:
        st.markdown(carte_indicateur("Pas à prix négatif", f"{fmt_fr(len(df_neg))}",
            "#FFF3E0", "#E65100",
            aide=f"{fmt_fr(len(df_neg)/nb_pas*100, 1)} % de la période. Tout prix < 0 €/MWh — critère "
                 f"plus large que le seuil de coupure ci-contre."), unsafe_allow_html=True)
    with col_n3:
        st.markdown(carte_indicateur("Prix négatif moyen", f"{fmt_fr(df_neg['Prix_Positifs'].mean(), 2)} €/MWh"
            if len(df_neg) > 0 else "N/A", "#FFF3E0", "#E65100",
            aide="Moyenne calculée uniquement sur les pas à prix négatif (< 0 €/MWh) — le coût moyen "
                 "d'injecter du surplus lors de ces épisodes."), unsafe_allow_html=True)
    with col_n4:
        st.markdown(carte_indicateur("Prix maximum atteint", f"{fmt_fr(df['Prix_Positifs'].max(), 2)} €/MWh",
            "#E3F2FD", "#1565C0",
            aide="La valeur la plus haute atteinte par le Prix de Règlement des Écarts Positifs sur "
                 "la période — le meilleur cas pour la valorisation du surplus."), unsafe_allow_html=True)

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
        st.caption("Pour chaque niveau de prix, le nombre de pas de 15 min de l'année où ce prix a été "
                   "observé (Prix de Règlement des Écarts Positifs). La grande majorité du temps se "
                   "concentre autour de 0-100 €/MWh ; les quelques barres qui s'étirent très loin vers "
                   "la gauche sont les rares épisodes extrêmes (comme celui du 30 mars).")
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


# ==========================================================
# ONGLET 3 : ANALYSE DES COUPURES
# ==========================================================
with tab3:
    episodes = detecter_episodes(df, "Temps_Coupure")

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        st.markdown(carte_indicateur("Temps de coupure total", f"{fmt_fr(temps_coupure_total)} h",
            "#FFEBEE", "#C62828",
            aide=f"Nombre d'heures où le prix est descendu au seuil de coupure "
                 f"({fmt_fr(seuil_coupure, 1)} €/MWh) ou en dessous, sur la période."), unsafe_allow_html=True)
    with col_c2:
        st.markdown(carte_indicateur("Nombre d'épisodes", f"{fmt_fr(len(episodes))}",
            "#FFEBEE", "#C62828",
            aide="Un épisode = une séquence continue de pas de 15 min en coupure, sans interruption. "
                 "Deux coupures séparées par un retour à un prix normal comptent comme 2 épisodes distincts."),
            unsafe_allow_html=True)
    with col_c3:
        duree_moy = episodes["Durée (h)"].mean() if len(episodes) > 0 else 0
        st.markdown(carte_indicateur("Durée moyenne d'un épisode", f"{fmt_fr(duree_moy, 2)} h",
            "#FFF3E0", "#E65100",
            aide="Durée moyenne d'une coupure continue, tous épisodes confondus sur la période."),
            unsafe_allow_html=True)
    with col_c4:
        duree_max = episodes["Durée (h)"].max() if len(episodes) > 0 else 0
        st.markdown(carte_indicateur("Épisode le plus long", f"{fmt_fr(duree_max, 2)} h",
            "#F3E5F5", "#6A1B9A",
            aide="La plus longue coupure continue observée sur la période, sans interruption."),
            unsafe_allow_html=True)

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



# ==========================================================
# ONGLET 4 : IMPACT PRODUCTION / CONSOMMATION
# ==========================================================
with tab4:
    st.subheader("Impact du surplus exposé aux heures à prix négatif")
    st.caption("Croise les heures à prix négatif (période et seuil sélectionnés dans la barre latérale) "
               "avec vos courbes de production et de consommation, pour estimer le volume d'énergie "
               "qui aurait dû être écrêté ou perdue en cas d'arrêt de la centrale, et compare deux offres de Responsable d'Équilibre.")

    if not fichiers_prod or not fichiers_conso:
        st.info("Merci d'importer au moins une courbe de production et une courbe de consommation "
                "dans la barre latérale (section « Données — Production / Consommation ») pour lancer "
                "cette analyse.")
    else:
        courbes_prod, serie_prod = charger_toutes_courbes(fichiers_prod)
        courbes_conso, serie_conso = charger_toutes_courbes(fichiers_conso)

        sites_aci = [nom for nom in courbes_conso if types_conso.get(nom) == "ACI"]
        sites_acc = [nom for nom in courbes_conso if types_conso.get(nom) == "ACC"]

        if len(sites_aci) == 0:
            conso_aci_totale = pd.Series(0.0, index=serie_conso.index)
            st.caption("Aucun site ACI détecté — toute la production est traitée comme exposée en ACC.")
        else:
            conso_aci_totale = sum(courbes_conso[nom] for nom in sites_aci).reindex(serie_conso.index).fillna(0.0)
            st.caption(f"Site(s) en ACI (priorité sur la production) : {', '.join(sites_aci)}. "
                       f"Site(s) en ACC : {', '.join(sites_acc) if sites_acc else 'aucun'}.")

        surplus_expose_acc = np.maximum(0.0, serie_prod.reindex(serie_conso.index).fillna(0.0) - conso_aci_totale)
        
        st.markdown("**Fichiers de production stoppés lors des heures à prix négatif (offre Symphonics)**")
        fichiers_coupables = st.multiselect(
            "Sélectionnez la ou les centrale(s) qui s'arrêtent net dès que le prix passe sous le seuil "
            "— les fichiers non sélectionnés continuent de produire normalement, même sous Symphonics.",
            list(courbes_prod.keys()), key="fichiers_coupables_select")

        en_coupure_30min = (df["Temps_Coupure"] > 0).resample("30min").max().fillna(False).astype(bool)
        en_coupure_aligned = en_coupure_30min.reindex(serie_conso.index).fillna(False)

        prod_coupable = sum(courbes_prod[nom] for nom in fichiers_coupables) if fichiers_coupables else pd.Series(0.0, index=serie_conso.index)
        prod_non_coupable = sum(courbes_prod[nom] for nom in courbes_prod if nom not in fichiers_coupables)

        prod_totale_symphonics = prod_non_coupable + prod_coupable.where(~en_coupure_aligned, 0.0)
        surplus_acc_symphonics = np.maximum(0.0, prod_totale_symphonics - conso_aci_totale)
        energie_perdue_symphonics_kwh = (prod_coupable.where(en_coupure_aligned, 0.0)).sum() * 0.5 / 1000.0

        st.success(f"{len(fichiers_prod)} fichier(s) de production et {len(fichiers_conso)} fichier(s) "
                   f"de consommation chargés et sommés.")
        st.markdown("---")
        st.subheader("Courbes de production et de consommation importées")

        col_v0, col_v1, col_v2 = st.columns([1, 1, 1])
        with col_v0:
            resolution_choisie = st.selectbox("Résolution d'affichage", [
                "Native (pas de 30 min)", "Toutes les 2h (moyenne)", "Journalière (moyenne)",
                "Journalière (pic)", "Hebdomadaire (moyenne)", "Hebdomadaire (pic)"
            ], index=3, key="resolution_affichage_courbes",
               help="« Pic » affiche la valeur maximale de chaque période plutôt que la moyenne — "
                    "recommandé pour la production solaire, dont la moyenne journalière écrase "
                    "fortement les pics de milieu de journée.")
        with col_v1:
            options_prod = list(courbes_prod.keys()) + ["Total (somme)"]
            choix_prod = st.multiselect("Courbes de production à afficher", options_prod,
                default=["Total (somme)"], key="choix_courbes_prod")
        with col_v2:
            options_conso = list(courbes_conso.keys()) + ["Total (somme)"]
            choix_conso = st.multiselect("Courbes de consommation à afficher", options_conso,
                default=["Total (somme)"], key="choix_courbes_conso")

        toutes_series = list(courbes_prod.values()) + list(courbes_conso.values())
        date_min_courbes = min(s.index.min() for s in toutes_series).date()
        date_max_courbes = max(s.index.max() for s in toutes_series).date()
        col_pd1, col_pd2 = st.columns(2)
        with col_pd1:
            date_debut_courbes = st.date_input("Afficher à partir du", value=date_min_courbes,
                min_value=date_min_courbes, max_value=date_max_courbes, key="date_debut_courbes_input")
        with col_pd2:
            date_fin_courbes = st.date_input("Afficher jusqu'au", value=date_max_courbes,
                min_value=date_min_courbes, max_value=date_max_courbes, key="date_fin_courbes_input")

        def appliquer_resolution(serie, choix):
            if choix == "Native (pas de 30 min)":
                return serie
            elif choix == "Toutes les 2h (moyenne)":
                return serie.resample("2h").mean()
            elif choix == "Journalière (moyenne)":
                return serie.resample("1D").mean()
            elif choix == "Journalière (pic)":
                return serie.resample("1D").max()
            elif choix == "Hebdomadaire (moyenne)":
                return serie.resample("1W").mean()
            elif choix == "Hebdomadaire (pic)":
                return serie.resample("1W").max()
            return serie

        if choix_prod or choix_conso:
            fig_courbes = go.Figure()
            palette_prod = ["#2E7D32", "#66BB6A", "#A5D6A7", "#1B5E20", "#43A047", "#00897B"]
            for i, nom in enumerate(choix_prod):
                s = serie_prod if nom == "Total (somme)" else courbes_prod[nom]
                s = s.loc[str(date_debut_courbes):str(date_fin_courbes)]
                s_affichee = appliquer_resolution(s, resolution_choisie)
                fig_courbes.add_trace(go.Scatter(x=s_affichee.index, y=s_affichee / 1000.0, mode="lines",
                    name=f"Prod — {nom}", line=dict(color=palette_prod[i % len(palette_prod)], width=1.3)))
            palette_conso = ["#C62828", "#E57373", "#EF9A9A", "#B71C1C", "#D32F2F", "#F06292"]
            for i, nom in enumerate(choix_conso):
                s = serie_conso if nom == "Total (somme)" else courbes_conso[nom]
                s = s.loc[str(date_debut_courbes):str(date_fin_courbes)]
                s_affichee = appliquer_resolution(s, resolution_choisie)
                fig_courbes.add_trace(go.Scatter(x=s_affichee.index, y=s_affichee / 1000.0, mode="lines",
                    name=f"Conso — {nom}", line=dict(color=palette_conso[i % len(palette_conso)], width=1.3)))
            fig_courbes.update_layout(
                title=f"Courbes de production et de consommation — {resolution_choisie} "
                      f"({date_debut_courbes.strftime('%d/%m/%Y')} au {date_fin_courbes.strftime('%d/%m/%Y')})",
                xaxis_title="Date", yaxis_title="kW", hovermode="x unified",
                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_courbes, use_container_width=True)

        coupure_30min = (df["Temps_Coupure"] > 0).resample("30min").max().fillna(False).astype(bool)
        prix_30min = df["Prix_Positifs"].resample("30min").mean()

        df_impact = pd.DataFrame(index=serie_conso.index)
        df_impact["prod_kW"] = serie_prod.reindex(df_impact.index) / 1000.0
        df_impact["conso_kW"] = serie_conso.reindex(df_impact.index) / 1000.0
        df_impact["en_coupure"] = coupure_30min.reindex(df_impact.index).fillna(False).astype(bool)
        df_impact["prix_eur_mwh"] = prix_30min.reindex(df_impact.index)
        df_impact = df_impact.dropna(subset=["prod_kW", "conso_kW"])

        if df_impact.empty:
            st.warning("Aucun recouvrement temporel entre vos courbes de production/consommation et "
                       "la période de prix négatifs sélectionnée.")
        else:
            df_impact["surplus_kW"] = surplus_expose_acc.reindex(df_impact.index).fillna(0.0) / 1000.0
            df_impact["surplus_kWh"] = df_impact["surplus_kW"] * 0.5

            surplus_expose = df_impact.loc[df_impact["en_coupure"], "surplus_kWh"]
            volume_expose_kwh = surplus_expose.sum()
            volume_expose_mwh = volume_expose_kwh / 1000.0

            col_i1, col_i2 = st.columns(2)
            cout_reel_injection = (df_impact.loc[df_impact["en_coupure"], "surplus_kWh"] *
                                    df_impact.loc[df_impact["en_coupure"], "prix_eur_mwh"] / 1000.0).sum()

            col_i1, col_i2 = st.columns(2)
            with col_i1:
                st.markdown(carte_indicateur("Énergie perdue en cas de coupure",
                    f"{fmt_fr(volume_expose_kwh)} kWh", "#FFEBEE", "#C62828",
                    aide=f"Soit {fmt_fr(volume_expose_mwh, 2)} MWh. C'est la production qui aurait lieu "
                         f"pendant les heures à prix négatif — si la centrale s'arrête à chaque fois "
                         f"(comme sous l'offre Symphonics), c'est exactement cette énergie qui n'est "
                         f"jamais produite."), unsafe_allow_html=True)
            with col_i2:
                st.markdown(carte_indicateur("Coût réel de l'injection à prix négatif",
                    f"{fmt_fr(cout_reel_injection)} €", "#FFF3E0", "#E65100",
                    aide="Somme, pas de 30 min par pas de 30 min, du surplus injecté multiplié par le "
                         "prix réel à cet instant (pas le seuil, ni une moyenne) — le vrai montant "
                         "supporté (ou évité si vous coupez) sur toute la période, d'après le fichier "
                         "de Règlement des Écarts."), unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Courbe de charge des excédents exposés")
            fig_surplus = go.Figure()
            fig_surplus.add_trace(go.Scatter(x=df_impact.index, y=df_impact["surplus_kW"], mode="lines",
                name="Surplus (kW)", line=dict(color="#2E7D32", width=1)))
            surplus_only_coupure = df_impact["surplus_kW"].where(df_impact["en_coupure"])
            fig_surplus.add_trace(go.Scatter(x=df_impact.index, y=surplus_only_coupure, mode="lines",
                name="dont exposé (heures à prix négatif)", line=dict(color="#C62828", width=1.5),
                fill="tozeroy"))
            fig_surplus.update_layout(title="Surplus de production — exposition aux heures à prix négatif en rouge",
                xaxis_title="Date", yaxis_title="kW", hovermode="x unified")
            st.plotly_chart(fig_surplus, use_container_width=True)

            df_impact["mois"] = df_impact.index.to_period("M").astype(str)
            surplus_mensuel = df_impact[df_impact["en_coupure"]].groupby("mois")["surplus_kWh"].sum().reset_index()
            fig_mensuel_surplus = go.Figure(go.Bar(x=surplus_mensuel["mois"], y=surplus_mensuel["surplus_kWh"],
                marker_color="#C62828"))
            fig_mensuel_surplus.update_layout(title="Surplus exposé par mois", xaxis_title="Mois",
                yaxis_title="kWh")
            st.plotly_chart(fig_mensuel_surplus, use_container_width=True)

            st.markdown("---")
            st.subheader("Comparaison des offres de Responsable d'Équilibre")

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("**Offre A — Symphonics (coupure des fichiers sélectionnés ci-dessus)**")
                symphonics_cout_fixe = st.number_input("Coût fixe annuel (€)", min_value=0.0, value=500.0,
                    step=50.0, key="symphonics_cout_fixe")
                symphonics_rachat = st.number_input("Rachat surplus hors coupure (€/MWh)", min_value=0.0,
                    value=5.0, step=0.5, key="symphonics_rachat")
            with col_p2:
                st.markdown("**Offre B — Sunflow (production continue, PRE+)**")
                sunflow_cout_fixe = st.number_input("Coût fixe annuel (€)", min_value=0.0, value=1200.0,
                    step=50.0, key="sunflow_cout_fixe")
                sunflow_rachat_normal = st.number_input("Rachat surplus hors coupure (€/MWh)", min_value=0.0,
                    value=5.0, step=0.5, key="sunflow_rachat_normal")
                sunflow_prix_pre_plus = st.number_input("Valorisation PRE+ pendant les heures à prix négatif (€/MWh)",
                    value=0.0, step=0.5, key="sunflow_prix_pre_plus",
                    help="Tarif négocié avec Sunflow pour l'agrégation PRE+ — à renseigner vous-même "
                         "selon votre contrat, peut être négatif.")

            prix_reel_30min = df["Prix_Positifs"].resample("30min").mean().reindex(serie_conso.index)

            # --- Symphonics ---
            surplus_symphonics_hors_coupure_kwh = (surplus_acc_symphonics.where(~en_coupure_aligned, 0.0)).sum() * 0.5 / 1000.0
            recette_symphonics_hors_coupure = surplus_symphonics_hors_coupure_kwh / 1000.0 * symphonics_rachat
            # Surplus résiduel injecté pendant la coupure (depuis les fichiers non coupés), valorisé au prix réel
            recette_symphonics_coupure = ((surplus_acc_symphonics.where(en_coupure_aligned, 0.0) * 0.5 / 1000.0)
                                            * prix_reel_30min / 1000.0).sum()
            net_symphonics = recette_symphonics_hors_coupure + recette_symphonics_coupure - symphonics_cout_fixe

            # --- Sunflow ---
            surplus_sunflow_hors_coupure_kwh = (surplus_expose_acc.where(~en_coupure_aligned, 0.0)).sum() * 0.5 / 1000.0
            recette_sunflow_hors_coupure = surplus_sunflow_hors_coupure_kwh / 1000.0 * sunflow_rachat_normal
            surplus_sunflow_coupure_kwh = (surplus_expose_acc.where(en_coupure_aligned, 0.0)).sum() * 0.5 / 1000.0
            recette_sunflow_coupure = surplus_sunflow_coupure_kwh / 1000.0 * sunflow_prix_pre_plus
            net_sunflow = recette_sunflow_hors_coupure + recette_sunflow_coupure - sunflow_cout_fixe

            ecart = net_sunflow - net_symphonics

            st.markdown("---")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                st.markdown(carte_indicateur("Énergie perdue si coupure (Symphonics)",
                    f"{fmt_fr(energie_perdue_symphonics_kwh)} kWh", "#FFEBEE", "#C62828",
                    aide="Production des fichiers sélectionnés ci-dessus qui n'a jamais lieu, pendant "
                         "les heures à prix négatif."), unsafe_allow_html=True)
            with col_e2:
                st.markdown(carte_indicateur("Coût réel de l'injection (référence, prix de marché)",
                    f"{fmt_fr(cout_reel_injection)} €", "#FFF3E0", "#E65100",
                    aide="Coût qu'aurait l'injection de TOUT le surplus ACC exposé, valorisé au prix "
                         "réel du marché à chaque instant — donnée de référence, indépendante du tarif "
                         "PRE+ négocié utilisé dans le calcul Sunflow ci-dessous."), unsafe_allow_html=True)

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.markdown(carte_indicateur("Résultat net — Symphonics", f"{fmt_fr(net_symphonics)} €",
                    "#F5F5F5", "#616161",
                    aide="Recette hors coupure + recette du surplus résiduel injecté pendant la coupure "
                         "(depuis les fichiers non coupés, valorisée au prix réel du marché), moins le "
                         "coût fixe annuel."), unsafe_allow_html=True)
            with col_r2:
                st.markdown(carte_indicateur("Résultat net — Sunflow", f"{fmt_fr(net_sunflow)} €",
                    "#F5F5F5", "#616161",
                    aide="Recette hors coupure + recette de tout le surplus exposé pendant la coupure "
                         "(rien n'est coupé), valorisée au tarif PRE+ renseigné ci-dessus, moins le "
                         "coût fixe annuel."), unsafe_allow_html=True)
            with col_r3:
                couleur_ecart = "#2E7D32" if ecart > 0 else "#C62828"
                fond_ecart = "#E8F5E9" if ecart > 0 else "#FFEBEE"
                st.markdown(carte_indicateur("Écart Sunflow − Symphonics", f"{fmt_fr(ecart)} €",
                    fond_ecart, couleur_ecart,
                    aide="Positif = Sunflow plus avantageux. Négatif = Symphonics plus avantageux."),
                    unsafe_allow_html=True)

            


            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.markdown(carte_indicateur("Résultat net — Symphonics", f"{fmt_fr(net_symphonics)} €",
                    "#F5F5F5", "#616161",
                    aide="Recette de rachat du surplus (hors coupure) moins le coût fixe annuel. "
                         "Aucune recette pendant les heures à prix négatif (centrale à l'arrêt)."),
                    unsafe_allow_html=True)
            with col_r2:
                st.markdown(carte_indicateur("Résultat net — Sunflow", f"{fmt_fr(net_sunflow)} €",
                    "#F5F5F5", "#616161",
                    aide="Recette de rachat du surplus (hors coupure) + valorisation PRE+ pendant les "
                         "heures à prix négatif, moins le coût fixe annuel."), unsafe_allow_html=True)
            with col_r3:
                couleur_ecart = "#2E7D32" if ecart > 0 else "#C62828"
                fond_ecart = "#E8F5E9" if ecart > 0 else "#FFEBEE"
                st.markdown(carte_indicateur("Écart Sunflow − Symphonics", f"{fmt_fr(ecart)} €",
                    fond_ecart, couleur_ecart,
                    aide="Positif = Sunflow plus avantageux. Négatif = Symphonics plus avantageux."),
                    unsafe_allow_html=True)

            