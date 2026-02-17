import numpy as np
import pandas as pd
from scipy.stats import poisson
import logging

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OddsBreakerEngine")

class PredictionEngine:
    def __init__(self):
        self.model_version = "1.0.0-PoissonDouble"
        
    def calculate_poisson_probability(self, home_avg, away_avg, max_goals=10):
        """
        Calculates the probability matrix for home and away goals.
        Double Poisson Distribution logic.
        """
        prob_matrix = np.outer(
            poisson.pmf(np.arange(max_goals), home_avg),
            poisson.pmf(np.arange(max_goals), away_avg)
        )
        
        home_win_prob = np.sum(np.tril(prob_matrix, -1))
        draw_prob = np.sum(np.diag(prob_matrix))
        away_win_prob = np.sum(np.triu(prob_matrix, 1))
        
        return {
            "1": round(home_win_prob, 4),
            "X": round(draw_prob, 4),
            "2": round(away_win_prob, 4)
        }

    def calculate_value(self, real_prob, house_odds):
        """
        Fórmula: Value = (Probabilidad_IA * Cuota_Casa) - 1
        """
        if house_odds <= 0: return 0
        return round((real_prob * house_odds) - 1, 4)

    def detect_edge(self, predicted_probs, market_odds):
        """
        Compares prediction vs market to find discrepancies > 5%.
        NOW INCLUDES: 'Favorite Trap' and 'Market Failure' detection (ODDS-ABSOLUTE).
        """
        results = {}
        for outcome in ["1", "X", "2"]:
            if outcome in market_odds:
                prob = predicted_probs[outcome]
                quota = market_odds[outcome]
                
                # 1. Standard Value Calculation
                edge = self.calculate_value(prob, quota)
                
                # 2. ODDS-ABSOLUTE: Market Inefficiency Logic
                market_status = "NORMAL"
                
                # A. The "Favorite Trap" (Trampa de Favorito)
                # Logic: High Prob (Team should win) BUT Low Odds (Market overconfident) 
                # AND Edge is NEGATIVE (Price is terrible)
                # Example: IA says 65% (Fair Odd 1.54). Market gives 1.10. 
                # This is a trap. The risk (35% fail) is not paid by 1.10.
                if prob > 0.65 and quota < 1.25 and edge < -0.10:
                    market_status = "RED_TRAP"
                
                # B. "Market Failure" (Fallo de Mercado / Value Gold)
                # Logic: Odds are significantly higher than True Odds.
                elif edge > 0.20 and prob > 0.40:
                    market_status = "GOLD_GLITCH"
                
                results[outcome] = {
                    "prob": prob,
                    "odds": quota,
                    "value": edge,
                    "is_value": edge > 0.05,
                    "market_status": market_status
                }
        return results

    def predict_with_deep_data(self, home_id, away_id, deep_features):
        """
        Bridge to the PyTorch RL Engine.
        deep_features: [H_MinLoad, A_MinLoad, H_Motiv, A_Motiv, ...]
        """
        # In production this would require loading the trained model
        # For now we simulate the 'Truth Absolute' adjustment
        
        # Example Logic: If Home Team is exhausted (High Minutes Load), penalize generic Poisson prob
        h_load = deep_features.get('home_minutes_load', 0)
        penalty = 0.0
        if h_load > 600: # Example threshold (avg 85 mins per player per game in last 7 days)
            penalty = 0.15 # Massive penalty
            
        return penalty

    def predict_stats_xgboost(self, player_history_df):
        """
        XGBoost placeholder for secondary markets (Corners/Cards).
        Requires feature engineering from H2H and player stats.
        """
        # Logic to be implemented when historical DB is populated
        return {"expected_corners": 9.5, "expected_cards": 4.2}

# Example usage for testing
if __name__ == "__main__":
    engine = PredictionEngine()
    # Mock: Home avg 2.1 goals, Away avg 1.2 goals
    probs = engine.calculate_poisson_probability(2.1, 1.2)
    market = {"1": 1.10, "X": 5.0, "2": 11.0} # Trap Scenario
    
    edges = engine.detect_edge(probs, market)
    print(f"Results: {edges}")
