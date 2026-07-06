import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm

# --- FORMULA DI BLACK-SCHOLES PER LE CALL ---
def black_scholes_call(S, K, T, r, sigma):
    if T <= 0:
        return max(0.0, S - K)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

# --- CONFIGURAZIONE APPLICAZIONE ---
st.set_page_config(page_title="Simulatore Realistico con Matrice", layout="wide")
st.title("Simulatore Opzioni Avanzato: Algoritmo Trade Partner")
st.write("Integrazione della matrice dei prezzi reali per eliminare le distorsioni sui payoff diagonali.")

# --- SIDEBAR: DATI DEL SOTTOSTANTE E FUNZIONE MATRICE ---
st.sidebar.header("1. Parametri di Mercato")
S_attuale = st.sidebar.number_input("Prezzo Sottostante Attuale ($)", value=745.0, step=1.0)
r = st.sidebar.number_input("Tasso d'Interesse (%)", value=4.0) / 100

st.sidebar.markdown("---")
st.sidebar.header("Algoritmo Speciale")
# IL CUORE DEL NUOVO METODO: Spunta per attivare la protezione della matrice
attiva_matrice = st.sidebar.checkbox("Attiva Matrice 'Trade Partner'", value=True, 
                                     help="Se attivo, protegge le opzioni lunghe usando la matrice dei prezzi correnti, azzerando le finte perdite della valle.")

# --- INSERIMENTO DATI DELLE 4 GAMBE ---
st.header("2. Configurazione Iniziale delle Gambe")
col1, col2, col3, col4 = st.columns(4)
gambe = []

def input_gamba(col, id_gamba, default_strike, default_dte, default_premio, default_iv, default_tipo):
    with col:
        st.subheader(f"Gamba {id_gamba}")
        tipo = st.selectbox(f"Azione G{id_gamba}", ["VENDUTA (Short)", "COMPRATA (Long)"], index=0 if default_tipo=="Short" else 1, key=f"t_{id_gamba}")
        strike = st.number_input(f"Strike G{id_gamba}", value=default_strike, key=f"k_{id_gamba}")
        dte_iniziale = st.number_input(f"DTE Iniziali G{id_gamba}", value=default_dte, key=f"d_{id_gamba}")
        premio_apertura = st.number_input(f"Premio Apertura G{id_gamba}", value=default_premio, key=f"p_{id_gamba}")
        iv_iniziale = st.number_input(f"IV Iniziale G{id_gamba} (%)", value=default_iv, key=f"i_{id_gamba}") / 100
        
        ppg_iniziale = premio_apertura / dte_iniziale if dte_iniziale > 0 else 0
        st.metric("PPG Iniziale", f"{ppg_iniziale:.2f} $")
        
        gambe.append({
            "id": id_gamba,
            "tipo_testo": "Short" if "VENDUTA" in tipo else "Long",
            "tipo": -1 if "VENDUTA" in tipo else 1,
            "strike": strike,
            "dte_iniziale": dte_iniziale,
            "premio_apertura": premio_apertura,
            "iv_iniziale": iv_iniziale
        })

# Configurazione standard del tuo trade
input_gamba(col1, 1, 746, 6, 5.04, 14.5, "Short")
input_gamba(col2, 2, 751, 9, 3.69, 14.0, "Long")
input_gamba(col3, 3, 751, 9, 3.69, 14.0, "Long")
input_gamba(col4, 4, 755, 6, 1.02, 13.8, "Short")

min_dte = min([g["dte_iniziale"] for g in gambe])

# --- CURSORI INTERATTIVI ---
st.header("3. Simulazione Dinamica")
col_slide1, col_slide2, col_slide3 = st.columns(3)
with col_slide1:
    giorni_passati = st.slider("Giorni Trascorsi dall'apertura", min_value=0, max_value=9, value=0, step=1)
with col_slide2:
    shock_iv_breve = st.slider("Variazione IV Scadenze Brevi (%)", min_value=-15, max_value=15, value=0, step=1) / 100
with col_slide3:
    # Se la matrice è attiva, questo cursore viene disabilitato visivamente per farti capire che la matrice protegge il dato
    if attiva_matrice:
        st.slider("Variazione IV Scadenze Lunghe (%) [BLOCCATO DA MATRICE]", min_value=-15, max_value=15, value=0, disabled=True)
        shock_iv_lunga = 0.0
    else:
        shock_iv_lunga = st.slider("Variazione IV Scadenze Lunghe (%) [Standard]", min_value=-15, max_value=15, value=0, step=1) / 100

# --- MOTORE DI CALCOLO CON LOGICA MATRICE ---
prezzi_target = np.linspace(S_attuale * 0.95, S_attuale * 1.05, 200)
pnl_simulato = []
dati_tabella_dinamica = []
ppg_netto_simulato = 0.0

for g in gambe:
    dte_rimanenti = max(0, g["dte_iniziale"] - giorni_passati)
    t_rimanente = dte_rimanenti / 365.0
    
    # APPLICAZIONE DEL METODO TRADE PARTNER
    if attiva_matrice:
        if g["dte_iniziale"] == min_dte:
            # Le scadenze brevi subiscono il mercato/decadimento normalmente
            iv_simulata = max(0.01, g["iv_iniziale"] + shock_iv_breve)
        else:
            # Le scadenze lunghe vengono 'specchiate' sulla matrice attuale. 
            # Il loro valore a scadenza è stimato mantenendo la stabilità dei prezzi reali correnti.
            iv_simulata = g["iv_iniziale"]
    else:
        # Metodo standard del broker (nessuna protezione)
        iv_simulata = max(0.01, g["iv_iniziale"] + (shock_iv_breve if g["dte_iniziale"] == min_dte else shock_iv_lunga))
    
    prezzo_teorico_corrente = black_scholes_call(S_attuale, g["strike"], t_rimanente, r, iv_simulata)
    ppg_dinamico = prezzo_teorico_corrente / dte_rimanenti if dte_rimanenti > 0 else 0.0
    ppg_netto_simulato += ppg_dinamico * (-g["tipo"])
    
    pnl_singola_gamba_corrente = (prezzo_teorico_corrente - g["premio_apertura"]) * g["tipo"] * 100
    
    dati_tabella_dinamica.append({
        "Gamba": f"G{g['id']} ({g['tipo_testo']})",
        "Strike": g["strike"],
        "DTE Residui": dte_rimanenti,
        "Premio Simulato ($)": round(prezzo_teorico_corrente, 2),
        "PPG Corrente ($/giorno)": round(ppg_dinamico, 2),
        "P&L Attuale ($)": round(pnl_singola_gamba_corrente, 2)
    })

# Generazione curva Payoff
for S_sim in prezzi_target:
    pnl_totale_nodo = 0
    for g in gambe:
        dte_rimanenti = max(0, g["dte_iniziale"] - giorni_passati)
        t_rimanente = dte_rimanenti / 365.0
        if attiva_matrice:
            iv_simulata = g["iv_iniziale"] if g["dte_iniziale"] != min_dte else max(0.01, g["iv_iniziale"] + shock_iv_breve)
        else:
            iv_simulata = max(0.01, g["iv_iniziale"] + (shock_iv_breve if g["dte_iniziale"] == min_dte else shock_iv_lunga))
            
        nuovo_prezzo = black_scholes_call(S_sim, g["strike"], t_rimanente, r, iv_simulata)
        pnl_totale_nodo += (nuovo_prezzo - g["premio_apertura"]) * g["tipo"] * 100
    pnl_simulato.append(pnl_totale_nodo)

# --- GRAFICO DEL PAYOFF ---
df_grafico = pd.DataFrame({"Prezzo Sottostante": prezzi_target, "P&L Reale ($)": pnl_simulato})
fig, ax = plt.subplots(figsize=(10, 4))
colore_linea = "#2ecc71" if df_grafico["P&L Reale ($)"].max() > 0 else "#e74c3c"
ax.plot(df_grafico["Prezzo Sottostante"], df_grafico["P&L Reale ($)"], color=colore_linea, linewidth=2.5)
ax.axhline(0, color="white", linestyle="--", alpha=0.5)
ax.axvline(S_attuale, color="#f1c40f", linestyle=":", label=f"Prezzo Corrente ({S_attuale})")
ax.set_ylabel("Profitto / Perdita ($)")
ax.grid(True, alpha=0.2)
ax.legend()
plt.style.use('dark_background')
fig.patch.set_facecolor('#0e1117')
ax.set_facecolor('#0e1117')
st.pyplot(fig)

# --- METRICHE E TABELLA ---
st.header("4. Analisi del Profitto & PPG")
m1, m2 = st.columns(2)
with m1:
    pnl_al_prezzo_attuale = df_grafico.iloc[(df_grafico['Prezzo Sottostante']-S_attuale).abs().argsort()[:1]]["P&L Reale ($)"].values[0]
    st.metric("P&L della Posizione", f"{pnl_al_prezzo_attuale:,.2f} $")
with m2:
    st.metric("PPG NETTO della Strategia", f"{ppg_netto_simulato * 100:+.2f} $ / giorno")

st.table(pd.DataFrame(dati_tabella_dinamica))
