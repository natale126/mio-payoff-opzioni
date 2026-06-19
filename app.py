import numpy as np

class EmpiricPayoffEngine:
    def __init__(self, current_underlying_price, full_option_chain):
        """
        full_option_chain: Un dizionario o DataFrame contenente i prezzi reali di OGGI.
        Struttura ideale: { DTE: { STRIKE: { 'call_bid': X, 'call_ask': Y, 'put_bid': W, ... } } }
        """
        self.S0 = current_underlying_price
        self.chain = full_option_chain
        self.legs = []

    def add_leg(self, quantity, strike, option_type, original_dte, entry_price):
        """Permette all'utente di inserire N gambe a piacimento"""
        self.legs.append({
            'qty': quantity,          # +1 per lunghe, -1 per corte
            'strike': strike,
            'type': option_type.upper(), # 'CALL' o 'PUT'
            'orig_dte': original_dte, # DTE al momento dell'apertura
            'entry': entry_price
        })

    def get_market_price_mirror(self, target_dte, target_strike, option_type):
        """
        IL CUORE DEL SOFTWARE: Cerca nella chain di oggi il prezzo specchio.
        Se non trova l'esatto DTE o lo Strike, effettua un'interpolazione lineare.
        """
        try:
            # Estrae la chain per il DTE simulato
            dte_data = self.chain[target_dte]
            
            # Prende il prezzo medio (Mid Price) per evitare distorsioni da mercato chiuso
            opt_data = dte_data[target_strike]
            if option_type == 'CALL':
                return (opt_data['call_bid'] + opt_data['call_ask']) / 2
            else:
                return (opt_data['put_bid'] + opt_data['put_ask']) / 2
        except KeyError:
            # Se il mercato non ha quell'esatto strike/DTE oggi, restituisce una stima di sicurezza
            # o applica un'approssimazione (Interpolazione)
            return 0.0

    def calculate_payoff_matrix(self, days_forward, price_range):
        """
        Calcola il vero profitto/perdita muovendo il cursore del tempo e dei prezzi
        """
        pnl_profile = []

        for S_simulated in price_range:
            total_pnl = 0.0
            
            for leg in self.legs:
                current_dte = leg['orig_dte'] - days_forward
                
                if current_dte <= 0:
                    # CASO A: L'opzione è scaduta -> Valore Intrinseco Puro
                    if leg['type'] == 'CALL':
                        value_at_t = max(0, S_simulated - leg['strike'])
                    else:
                        value_at_t = max(0, leg['strike'] - S_simulated)
                else:
                    # CASO B: L'opzione è viva -> Applichiamo il Principio dello Specchio
                    # Calcoliamo la distanza dallo strike (Moneyness) per replicarla sulla chain di oggi
                    moneyness_offset = leg['strike'] - S_simulated
                    mirror_strike = round(self.S0 + moneyness_offset)
                    
                    # Estraiamo il prezzo reale di oggi per quell'assetto temporale/prezzo
                    value_at_t = self.get_market_price_mirror(current_dte, mirror_strike, leg['type'])
                
                # Calcolo del PnL della singola gamba
                leg_pnl = (value_at_t - leg['entry']) * leg['qty'] * 100 # Moltiplicatore opzioni
                total_pnl += leg_pnl
                
            pnl_profile.append(total_pnl)
            
        return pnl_profile
