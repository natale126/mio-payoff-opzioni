import streamlit as st
import numpy as np
import plotly.graph_objects as go

# QUESTO DEVE ESSERE IL PRIMO COMANDO IN ASSOLUTO DOPO GLI IMPORT
st.set_page_config(page_title="Empiric Payoff", layout="tight")

st.title("📈 Real Payoff Simulator")
st.subheader("Principio della Matrice Empirica")

# --- 1. CONFIGURAZIONE GAMBE ---
st.sidebar.header("Configurazione Strategia")
if 'legs' not in st.session_state:
    st.session_state.legs = [
        {"qty": -1, "strike": 750, "type": "CALL", "dte": 3, "entry": 1.58},
        {"qty": -1, "strike": 758, "type": "CALL", "dte": 3, "entry": 0.08},
        {"qty": 1, "strike": 754, "type": "CALL", "dte": 4, "entry": 0.91},
        {"qty": 1, "strike": 755, "type": "CALL", "dte": 4, "entry": 0.68},
    ]

if st.sidebar.button("➕ Aggiungi Gamba"):
    st.session_state.legs.append({"qty": 1, "strike": 745, "type": "CALL", "dte": 3, "entry": 1.0})

for i, leg in enumerate(st.session_state.legs):
    with st.sidebar.expander(f"Gamba {i+1}: {leg['type']} {leg['strike']}"):
        leg['qty'] = st.number_input("Quantità (-1 corta, +1 lunga)", value=leg['qty'], key=f"q_{i}")
        leg['strike'] = st.number_input("Strike", value=leg['strike'], key=f"s_{i}")
        leg['dte'] = st.number_input("Original DTE", value=leg['dte'], key=f"d_{i}")
        leg['entry'] = st.number_input("Prezzo di Carico", value=leg['entry'], key=f"e_{i}")

# --- 2. CURSORI ---
st.markdown("### 🎛️ Pannello di Controllo")
col1, col2 = st.columns(2)
with col1:
    giorni_avanti = st.slider("⏳ Giorni in Avanti (Cursore Tempo)", 0, 4, 0)
with col2:
    s_attuale = st.slider("💵 Prezzo SPY Attuale", 720, 780, 746)

# --- 3. MOTORE DI CALCOLO EMPIRICO ---
def get_simulated_market_price(target_dte, target_strike, current_underlying):
    distance = abs(target_strike - current_underlying)
    time_factor = np.sqrt(max(0.1, target_dte) / 4)
    sim_price = max(0.05, (2.5 - (distance * 0.4)) * time_factor)
    return sim_price

prezzi_asse_x = np.arange(730, 770, 0.5)
pnl_profilo = []

for S_simulated in prezzi_asse_x:
    total_pnl = 0.0
    for leg in st.session_state.legs:
        current_dte = leg['dte'] - giorni_avanti
        
        if current_dte <= 0:
            valore_opzione = max(0, S_simulated - leg['strike']) if leg['type'] == "CALL" else max(0, leg['strike'] - S_simulated)
        else:
            moneyness_offset = leg['strike'] - S_simulated
            mirror_strike = round(s_attuale + moneyness_offset)
            valore_opzione = get_simulated_market_price(current_dte, mirror_strike, s_attuale)
            
        leg_pnl = (valore_opzione - leg['entry']) * leg['qty'] * 100
        total_pnl += leg_pnl
    pnl_profilo.append(total_pnl)

# --- 4. GRAFICO ---
fig = go.Figure()
fig.add_trace(go.Scatter(x=prezzi_asse_x, y=pnl_profilo, name="Vero Payoff Empirico", line=dict(color="#00FFFF", width=3)))
fig.add_vline(x=s_attuale, line_dash="dash", line_color="white", annotation_text="Prezzo Spot")
fig.update_layout(template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Prezzo Sottostante", yaxis_title="Profitto / Perdita ($)")
st.plotly_chart(fig, use_container_width=True)
