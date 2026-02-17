import json
import os
import time
import pandas as pd
from datetime import datetime

class BetTracker:
    def __init__(self, file_path='data/bet_history.json'):
        self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
        self.history = self.load_history()
        # Active slip (in-memory only, for building parleys in UI)
        self.slip = [] 

    def load_history(self):
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except:
            return []

    def save_history(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, 'w') as f:
            json.dump(self.history, f, indent=4)

    def add_to_slip(self, match, selection, odds, fair_prob, stake=10, type="Single"):
        """
        Adds a bet to the temporary slip.
        match: "Real Madrid vs Barcelona"
        """
        bet = {
            "id": int(time.time() * 1000), # Simple ID
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "match": match,
            "selection": selection,
            "odds": float(odds),
            "fair_prob": float(fair_prob),
            "stake": float(stake),
            "type": type,
            "status": "PENDING", # PENDING, WON, LOST
            "return": 0
        }
        self.slip.append(bet)
        return bet

    def clear_slip(self):
        self.slip = []

    def confirm_slip_as_singles(self):
        """Saves all bets in slip as individual bets."""
        for bet in self.slip:
            self.history.append(bet)
        self.save_history()
        self.clear_slip()

    def confirm_slip_as_parley(self, stake=10):
        """Combines all bets in slip into one Parley."""
        if not self.slip: return
        
        total_odds = 1.0
        combined_prob = 1.0
        matches = []
        selections = []
        
        for bet in self.slip:
            total_odds *= bet['odds']
            combined_prob *= bet['fair_prob']
            matches.append(bet['match'])
            selections.append(f"{bet['selection']} ({bet['match']})")
        
        parley_bet = {
            "id": int(time.time() * 1000),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "match": " + ".join(matches[:2]) + ("..." if len(matches) > 2 else ""), 
            "selection": "PARLEY: " + " | ".join(selections),
            "odds": round(total_odds, 2),
            "fair_prob": round(combined_prob, 3),
            "stake": float(stake),
            "type": f"Parley ({len(self.slip)} legs)",
            "status": "PENDING",
            "return": 0,
            "legs": self.slip # Store legs for reference
        }
        
        self.history.append(parley_bet)
        self.save_history()
        self.clear_slip()

    def update_result(self, bet_id, result):
        """result: 'WON' or 'LOST'"""
        for bet in self.history:
            if bet['id'] == bet_id:
                bet['status'] = result
                if result == 'WON':
                    bet['return'] = bet['stake'] * bet['odds']
                else:
                    bet['return'] = 0
                break
        self.save_history()

    def get_stats(self):
        df = pd.DataFrame(self.history)
        if df.empty:
            return {"roi": 0, "profit": 0, "win_rate": 0, "count": 0}
        
        resolved = df[df['status'] != 'PENDING']
        if resolved.empty:
            return {"roi": 0, "profit": 0, "win_rate": 0, "count": len(df)}
        
        total_stake = resolved['stake'].sum()
        total_return = resolved['return'].sum()
        profit = total_return - total_stake
        roi = (profit / total_stake) * 100 if total_stake > 0 else 0
        
        wins = len(resolved[resolved['status'] == 'WON'])
        win_rate = (wins / len(resolved)) * 100
        
        return {
            "roi": roi,
            "profit": profit,
            "win_rate": win_rate,
            "count": len(df),
            "resolved_count": len(resolved)
        }
