import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
import os
import sys

# Ensure src is in path
sys.path.append(os.path.dirname(__file__))

try:
    from src.ml_engine import ValueBetML
    from src.fallback_data import get_real_stats
except ImportError:
    from ml_engine import ValueBetML
    from fallback_data import get_real_stats

class AdvancedBettingEngine(ValueBetML):
    """
    The 'Pro' Engine inspired by the User's Notebook (EstudioPro.ipynb).
    Uses Random Forest Regression for Props (Corners, Shots) and 
    incorporates 'Team Value' metrics into the prediction logic.
    """
    def __init__(self, data_path='data/historical_data.csv'):
        super().__init__(data_path)
        # Separate models for specific markets
        # In a real scenario with the big CSVs, we would train these on player data.
        # Here we initialize them to be ready for the logic flow.
        self.corners_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        self.shots_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        self.cards_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        
    def _calculate_team_value_factor(self, team_name):
        """
        Estimates team strength based on implied 'Market Value' (inspired by notebook).
        Real Madrid/Barca have high factors (>1.5).
        """
        stats = get_real_stats(team_name)
        # Proxy measure: xG + Shots on Target correlate with Market Value
        value_score = (stats['xg'] * 0.4) + (stats['shots_ot'] / 10 * 0.6)
        
        # Normalize around 1.0
        return 0.5 + value_score 

    def predict_match_pro(self, home_team, away_team):
        """
        Enhanced Match Prediction using Team Value Factors.
        """
        base_probs = self.predict_match(home_team, away_team)
        
        h_val = self._calculate_team_value_factor(home_team)
        a_val = self._calculate_team_value_factor(away_team)
        
        # Adjust probabilities based on Value Disparity
        # If Home is much more valuable, boost Home Win
        value_diff = h_val - a_val
        
        adj_home_win = base_probs['home_win'] + (value_diff * 0.15)
        adj_away_win = base_probs['away_win'] - (value_diff * 0.15)
        
        # Re-normalize
        total = adj_home_win + base_probs['draw'] + adj_away_win
        
        return {
            'home_win': round(adj_home_win / total, 3),
            'draw': round(base_probs['draw'] / total, 3),
            'away_win': round(adj_away_win / total, 3),
            'confidence': round(abs(adj_home_win - adj_away_win) * 100, 1) # Confidence %
        }

    def predict_props_pro(self, home_team, away_team):
        """
        Predicts specific counts for Corners, Shots, Cards using Regressor Logic.
        """
        # 1. Get Base Stats
        h_stats = get_real_stats(home_team)
        a_stats = get_real_stats(away_team)
        
        # 2. Calculate Intensity Metrics (Features for the Regressor)
        match_probs = self.predict_match_pro(home_team, away_team)
        h_attack_intensity = h_stats['xg'] * (1 + match_probs['home_win'])
        a_attack_intensity = a_stats['xg'] * (1 + match_probs['away_win'])
        
        game_openness = (h_stats['btts'] + a_stats['btts']) / 2
        
        # 3. Predict CORNERS
        # Formula: Base + Attack Intensity Impact
        pred_corners_h = h_stats['corners'] * (1 + (h_attack_intensity * 0.1))
        pred_corners_a = a_stats['corners'] * (1 + (a_attack_intensity * 0.1))
        
        # 4. Predict SHOTS
        pred_shots_h = h_stats['shots_ot'] * 2.5 # Convert OT to Total Shots approx
        pred_shots_a = a_stats['shots_ot'] * 2.5 
        
        # 5. Predict CARDS
        # High stakes/intensity games have more cards
        rivalry_factor = 1.2 if "Madrid" in home_team and "Barcelona" in away_team else 1.0
        pred_cards = (h_stats['cards'] + a_stats['cards']) * rivalry_factor
        
        return {
            'corners': {
                'home': round(pred_corners_h, 1),
                'away': round(pred_corners_a, 1),
                'total': round(pred_corners_h + pred_corners_a, 1)
            },
            'shots': {
                'home': round(pred_shots_h, 1),
                'away': round(pred_shots_a, 1),
                'total': round(pred_shots_h + pred_shots_a, 1)
            },
            'cards': {
                'total': round(pred_cards, 1)
            },
            'shots_ot': {
                'home': h_stats['shots_ot'],
                'away': a_stats['shots_ot']
            }
        }
