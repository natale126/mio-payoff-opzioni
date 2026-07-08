import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm
from scipy.interpolate import interp1d
import yfinance as yf
from datetime import datetime, date

# --- FORMULA DI BLACK-SCHOLES ---
def black_scholes(S, K, T, r, sigma, is_call=True):
    if T <= 0:
        return max(0.0, S - K) if is_call else max(0.0, K - S)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if is_call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

# --- COSTRUZIONE STRUTTURA A TERMINE (IL 100% DELLA MATRICE) ---
@st.cache_data(ttl=900, show_spinner=False)
def costruisci_curva_volatilita(simbolo, S_attuale, scadenze):
    dte_list = []
    iv_list = []
    tk = yf.Ticker(simbolo)
    oggi = date.today()
    
    # Scarica le prime 15 scadenze per costruire la curva di mercato reale
    for scad in scadenze[:15]:
        try:
            chain = tk.option_chain(scad)
            calls = chain.calls
            # Trova l'opzione At-The-Money (più vicina al prezzo attuale)
            idx = (calls['strike'] - S_attuale).abs().argmin()
            iv = float(calls.iloc[idx]['impliedVolatility'])
            dte = max(1, (datetime.strptime(scad, "%Y-%m-%d").date() - oggi).days)
            
            if dte not in dte_list and iv > 0:
                dte_list.append(dte)
                iv_list.append(iv)
        except:
            continue
            
    if len(dte_list) > 1:
        # Ordina e crea la funzione matematica che collega tutti i punti (interpolazione)
        coppie = sorted(zip(dte_list, iv_list))
        dte_ordinati = [p[0] for p in coppie]
        iv_ordinate = [p[1] for p in coppie]
        return interp1d(dte_ordinati, iv_ordinate, kind='linear', fill_value="extrapolate")
    return None

# --- CONFIGURAZIONE APPLICAZIONE ---
st.set_page_config(page_title="Simulatore Opzioni PRO", layout="wide")
st.title("Terminale Quantitativo (Matrice 100% Reale)")
st.write("Versione definitiva: Calcolo istituzionale su Mid Price e Struttura a Termine.")

# --- SIDEBAR: CONNESSIONE DATI ---
st.sidebar.header("1. Mercato Reale")
simbolo = st.sidebar.text_input("Ticker Sottostante", value="SPY").upper()

ticker = yf.Ticker(simbolo)
try:
    S_attuale = ticker.fast_info['last_price']
    scadenze_disponibili = ticker.options
    if not scadenze_disponibili:
        st.stop()
except:
    st.sidebar.error("Errore nel caricamento del Ticker.")
    st.stop()

st.sidebar.metric(f"Prezzo {simbolo}", f"{S_attuale:.2f} $")
r = st.sidebar.number_input("Tasso d'Interesse (%)", value=4.0) / 100

st.sidebar.markdown("---")
st.sidebar.header("2. Setup Strategia")
num_gambe = st.sidebar.selectbox("Numero di Gambe", [1, 2, 3, 4], index=3)
attiva_matrice = st.sidebar.checkbox("Attiva Matrice 100% (Usa Term Structure Reale)", value=True, help="Disattivalo per usare il calcolo stupido dei classici broker.")

# Inizializzazione della Curva di Volatilità in background
curva_iv = None
if attiva_matrice:
    with st.spinner("Estrazione Term Structure dal mercato in corso..."):
        curva_iv = costruisci_curva_volatilita(simbolo, S_attuale, scadenze_disponibili)

# --- INSERIMENTO GAMBE CON DATI LIVE ---
st.header("Configurazione Gambe")
colonne_UI = st.columns(num_gambe)
gambe = []

def input_gamba_live(col, id_gamba):
    with col:
        st.subheader(f"Gamba {id_gamba}")
        tipo_azione = st.selectbox(f"Azione", ["VENDUTA (Short)", "COMPRATA (Long)"], key=f"t_az_{id_gamba}")
        tipo_opzione = st.selectbox(f"Tipo", ["Call", "Put"], key=f"t_op_{id_gamba}")
        scadenza = st.selectbox(f"Scadenza", scadenze_disponibili, key=f"scad_{id_gamba}")
        
        oggi = date.today()
        data_scadenza = datetime.strptime(scadenza, "%Y-%m-%d").date()
        dte_iniziale = max(1, (data_scadenza - oggi).days)
        
        chain = ticker.option_chain(scadenza)
        df_opzioni = chain.calls if tipo_opzione == "Call" else chain.puts
        
        strikes = df_opzioni['strike'].tolist()
        strike_default_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - S_attuale))
        strike = st.selectbox(f"Strike", strikes, index=strike_default_idx, key=f"k_{id_gamba}")
        
        dati_strike = df_opzioni[df_opzioni['strike'] == strike].iloc[0]
        
        # NUOVO BLOCCO: CALCOLO DEL MID PRICE AL POSTO DEL LAST PRICE
        bid = float(dati_strike['bid'])
        ask = float(dati_strike['ask'])
        # Se c'è un errore nei dati e mancano bid/ask, usa il last price come rete di sicurezza
        if bid == 0.0 and ask == 0.0:
            premio_reale = float(dati_strike['lastPrice'])
        else:
            premio_reale = (bid + ask) / 2
            
        iv_reale = float(dati_strike['impliedVolatility'])
        
        st.metric("Premio (Mid)", f"{premio_reale:.2f} $")
        st.metric("IV Reale", f"{iv_reale*100:.2f} %")
        
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
st.header("Macchina del Tempo & Stress Test")
col_slide1, col_slide2, col_slide3 = st.columns(3)
with col_slide1:
    giorni_passati = st.slider("Giorni Trascorsi", min_value=0, max_value=int(max([g["dte_iniziale"] for g in gambe])), value=0, step=1)
with col_slide2:
    shock_iv_breve = st.slider("Shock IV Scadenze Brevi (%)", min_value=-20, max_value=20, value=0, step=1) / 100
with col_slide3:
    if attiva_matrice:
        st.slider("Shock IV Scadenze Lunghe (%)", value=0, disabled=True, help="Lucchetto Matrice: Le lunghe seguono la curva naturale del mercato.")
        shock_iv_lunga = 0.0
    else:
        shock_iv_lunga = st.slider("Shock IV Scadenze Lunghe (%)", min_value=-20, max_value=20, value=0, step=1) / 100

# --- MOTORE DI CALCOLO 100% REALE ---
prezzi_target = np.linspace(S_attuale * 0.90, S_attuale * 1.10, 200)
pnl_simulato = []
dati_tabella = []
ppg_netto_simulato = 0.0

for g in gambe:
    dte_rimanenti = max(0.001, g["dte_iniziale"] - giorni_passati)
    t_rimanente = dte_rimanenti / 365.0
    
    if attiva_matrice and curva_iv is not None:
        iv_base_iniziale = float(curva_iv(g["dte_iniziale"]))
        spread_volatilita = g["iv_iniziale"] - iv_base_iniziale
        nuova_iv_base = float(curva_iv(dte_rimanenti))
        iv_strutturale = nuova_iv_base + spread_volatilita
        iv_simulata = max(0.01, iv_strutturale + shock_iv_breve) if g["dte_iniziale"] == min_dte else max(0.01, iv_strutturale)
    else:
        iv_simulata = max(0.01, g["iv_iniziale"] + (shock_iv_breve if g["dte_iniziale"] == min_dte else shock_iv_lunga))
    
    prezzo_teorico = black_scholes(S_attuale, g["strike"], t_rimanente, r, iv_simulata, g["is_call"])
    ppg_dinamico = prezzo_teorico / dte_rimanenti
    ppg_netto_simulato += ppg_dinamico * (-g["tipo"])
    pnl_gamba = (prezzo_teorico - g["premio_apertura"]) * g["tipo"] * 100
    
    dati_tabella.append({
        "Gamba": f"G{g['id']} ({g['tipo_testo']} { 'Call' if g['is_call'] else 'Put' })",
        "DTE Residui": int(dte_rimanenti),
        "IV Usata (%)": round(iv_simulata * 100, 2),
        "Valore ($)": round(prezzo_teorico, 2),
        "P&L ($)": round(pnl_gamba, 2)
    })

# Calcolo curva grafico
for S_sim in prezzi_target:
    pnl_totale_nodo = 0
    for g in gambe:
        dte_rimanenti = max(0.001, g["dte_iniziale"] - giorni_passati)
        t_rimanente = dte_rimanenti / 365.0
        
        if attiva_matrice and curva_iv is not None:
            iv_base_iniziale = float(curva_iv(g["dte_iniziale"]))
            spread_volatilita = g["iv_iniziale"] - iv_base_iniziale
            nuova_iv_base = float(curva_iv(dte_rimanenti))
            iv_strutturale = nuova_iv_base + spread_volatilita
            iv_simulata = max(0.01, iv_strutturale + shock_iv_breve) if g["dte_iniziale"] == min_dte else max(0.01, iv_strutturale)
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
