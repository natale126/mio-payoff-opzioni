import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm
import yfinance as yf
from datetime import datetime, date

# --- FORMULA DI BLACK-SCHOLES (Aggiornata per Call e Put) ---
def black_scholes(S, K, T, r, sigma, is_call=True):
    if T <= 0:
        return max(0.0, S - K) if is_call else max(0.0, K - S)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if is_call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

# --- CONFIGURAZIONE APPLICAZIONE ---
st.set_page_config(page_title="Simulatore Live Opzioni", layout="wide")
st.title("Simulatore Opzioni Live (Dati Reali di Mercato)")
st.write("Connesso a Yahoo Finance (ritardo 15 min). Il software scarica in automatico Premi e IV reali.")

# --- SIDEBAR: CONNESSIONE DATI ---
st.sidebar.header("1. Mercato Reale")
simbolo = st.sidebar.text_input("Ticker Sottostante (es. SPY, AAPL, QQQ)", value="SPY").upper()

# Scarico dati del sottostante
ticker = yf.Ticker(simbolo)
try:
    S_attuale = ticker.fast_info['last_price']
    scadenze_disponibili = ticker.options
    if not scadenze_disponibili:
        st.sidebar.error("Nessuna opzione trovata per questo Ticker.")
        st.stop()
except Exception as e:
    st.sidebar.error("Errore nel caricamento del Ticker. Verifica che esista.")
    st.stop()

st.sidebar.metric(f"Prezzo Attuale {simbolo}", f"{S_attuale:.2f} $")
r = st.sidebar.number_input("Tasso d'Interesse (%)", value=4.0) / 100

st.sidebar.markdown("---")
st.sidebar.header("2. Impostazioni Strategia")
num_gambe = st.sidebar.selectbox("Numero di Gambe", [1, 2, 3, 4], index=3)
attiva_matrice = st.sidebar.checkbox("Attiva Matrice (Blocca IV Lunghe)", value=True)

# --- INSERIMENTO GAMBE CON DATI LIVE ---
st.header("Configurazione Live delle Gambe")
colonne_UI = st.columns(num_gambe)
gambe = []

def input_gamba_live(col, id_gamba):
    with col:
        st.subheader(f"Gamba {id_gamba}")
        tipo_azione = st.selectbox(f"Azione", ["VENDUTA (Short)", "COMPRATA (Long)"], key=f"t_az_{id_gamba}")
        tipo_opzione = st.selectbox(f"Tipo", ["Call", "Put"], key=f"t_op_{id_gamba}")
        
        # Scelta Data Reale
        scadenza = st.selectbox(f"Scadenza Reale", scadenze_disponibili, key=f"scad_{id_gamba}")
        
        # Calcolo DTE automatico
        oggi = date.today()
        data_scadenza = datetime.strptime(scadenza, "%Y-%m-%d").date()
        dte_iniziale = (data_scadenza - oggi).days
        if dte_iniziale <= 0: dte_iniziale = 1 # Evita errori alla data di scadenza
        
        # Scarica la Option Chain reale per quella data
        with st.spinner("Scaricamento dati mercato..."):
            chain = ticker.option_chain(scadenza)
            df_opzioni = chain.calls if tipo_opzione == "Call" else chain.puts
        
        # Estrae gli strike disponibili sul mercato e trova il più vicino al prezzo attuale
        strikes = df_opzioni['strike'].tolist()
        strike_default_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - S_attuale))
        strike = st.selectbox(f"Strike", strikes, index=strike_default_idx, key=f"k_{id_gamba}")
        
        # Cattura Premio (Ultimo Prezzo) e IV Reale dal DataFrame di yfinance
        dati_strike = df_opzioni[df_opzioni['strike'] == strike].iloc[0]
        premio_reale = float(dati_strike['lastPrice'])
        iv_reale = float(dati_strike['impliedVolatility'])
        
        st.metric("Premio Mercato (Last)", f"{premio_reale:.2f} $")
        st.metric("IV Mercato (Reale)", f"{iv_reale*100:.2f} %")
        
        gambe.append({
            "id": id_gamba,
            "tipo_testo": "Short" if "VENDUTA" in tipo_azione else "Long",
            "tipo": -1 if "VENDUTA" in tipo_azione else 1,
            "is_call": True if tipo_opzione == "Call" else False,
            "strike": strike,
            "dte_iniziale": dte_iniziale,
            "premio_apertura": premio_reale,
            "iv_iniziale": iv_reale
        })

for i in range(num_gambe):
    input_gamba_live(colonne_UI[i], i+1)

min_dte = min([g["dte_iniziale"] for g in gambe])

# --- CURSORI INTERATTIVI ---
st.header("Simulazione Dinamica (Stress Test)")
col_slide1, col_slide2, col_slide3 = st.columns(3)
with col_slide1:
    giorni_passati = st.slider("Giorni Trascorsi", min_value=0, max_value=int(max([g["dte_iniziale"] for g in gambe])), value=0, step=1)
with col_slide2:
    shock_iv_breve = st.slider("Shock IV Scadenze Brevi (%)", min_value=-20, max_value=20, value=0, step=1) / 100
with col_slide3:
    if attiva_matrice:
        st.slider("Shock IV Scadenze Lunghe (%)", min_value=-20, max_value=20, value=0, disabled=True, help="Bloccato dalla Matrice per usare la Volatilità Strutturale")
        shock_iv_lunga = 0.0
    else:
        shock_iv_lunga = st.slider("Shock IV Scadenze Lunghe (%)", min_value=-20, max_value=20, value=0, step=1) / 100

# --- MOTORE DI CALCOLO P&L ---
prezzi_target = np.linspace(S_attuale * 0.90, S_attuale * 1.10, 200)
pnl_simulato = []
dati_tabella = []
ppg_netto_simulato = 0.0

for g in gambe:
    dte_rimanenti = max(0.001, g["dte_iniziale"] - giorni_passati)
    t_rimanente = dte_rimanenti / 365.0
    
    if attiva_matrice:
        iv_simulata = max(0.01, g["iv_iniziale"] + shock_iv_breve) if g["dte_iniziale"] == min_dte else g["iv_iniziale"]
    else:
        iv_simulata = max(0.01, g["iv_iniziale"] + (shock_iv_breve if g["dte_iniziale"] == min_dte else shock_iv_lunga))
    
    prezzo_teorico_corrente = black_scholes(S_attuale, g["strike"], t_rimanente, r, iv_simulata, g["is_call"])
    ppg_dinamico = prezzo_teorico_corrente / dte_rimanenti
    ppg_netto_simulato += ppg_dinamico * (-g["tipo"])
    pnl_gamba = (prezzo_teorico_corrente - g["premio_apertura"]) * g["tipo"] * 100
    
    dati_tabella.append({
        "Gamba": f"G{g['id']} ({g['tipo_testo']} { 'Call' if g['is_call'] else 'Put' })",
        "Strike": g["strike"],
        "DTE Residui": int(dte_rimanenti),
        "Valore Attuale ($)": round(prezzo_teorico_corrente, 2),
        "P&L Gamba ($)": round(pnl_gamba, 2)
    })

for S_sim in prezzi_target:
    pnl_totale_nodo = 0
    for g in gambe:
        dte_rimanenti = max(0.001, g["dte_iniziale"] - giorni_passati)
        t_rimanente = dte_rimanenti / 365.0
        if attiva_matrice:
            iv_simulata = g["iv_iniziale"] if g["dte_iniziale"] != min_dte else max(0.01, g["iv_iniziale"] + shock_iv_breve)
        else:
            iv_simulata = max(0.01, g["iv_iniziale"] + (shock_iv_breve if g["dte_iniziale"] == min_dte else shock_iv_lunga))
            
        nuovo_prezzo = black_scholes(S_sim, g["strike"], t_rimanente, r, iv_simulata, g["is_call"])
        pnl_totale_nodo += (nuovo_prezzo - g["premio_apertura"]) * g["tipo"] * 100
    pnl_simulato.append(pnl_totale_nodo)

# --- GRAFICO E METRICHE ---
df_grafico = pd.DataFrame({"Prezzo": prezzi_target, "P&L": pnl_simulato})
fig, ax = plt.subplots(figsize=(10, 4))
colore_linea = "#2ecc71" if df_grafico["P&L"].max() > 0 else "#e74c3c"
ax.plot(df_grafico["Prezzo"], df_grafico["P&L"], color=colore_linea, linewidth=2.5)
ax.axhline(0, color="white", linestyle="--", alpha=0.5)
ax.axvline(S_attuale, color="#f1c40f", linestyle=":", label=f"Prezzo Attuale ({S_attuale:.2f})")
ax.set_ylabel("Profitto / Perdita ($)")
ax.grid(True, alpha=0.2)
ax.legend()
plt.style.use('dark_background')
fig.patch.set_facecolor('#0e1117')
ax.set_facecolor('#0e1117')
st.pyplot(fig)

m1, m2 = st.columns(2)
with m1:
    idx_attuale = (df_grafico['Prezzo'] - S_attuale).abs().argmin()
    pnl_attuale = df_grafico.iloc[idx_attuale]["P&L"]
    st.metric("P&L Totale Attuale", f"{pnl_attuale:,.2f} $")
with m2:
    st.metric("PPG NETTO", f"{ppg_netto_simulato * 100:+.2f} $ / giorno")

st.table(pd.DataFrame(dati_tabella))
