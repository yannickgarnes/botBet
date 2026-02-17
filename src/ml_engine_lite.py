import random
import os
import sys

# Ensure src is in path
sys.path.append(os.path.dirname(__file__))

class ValueBetML_Lite:
    """
    A lightweight version of the ML Engine that uses heuristics instead of heavy Sklearn models.
    Designed for low-memory environments or fallback.
    """
    def __init__(self, data_path='data/historical_data.csv'):
        self.data_path = data_path
        
    def train(self):
        pass

    def predict_match(self, home_team, away_team):
        """
        Predicts win probabilities based on 'Real Data' strength (fallback_data).
        """
        try:
            from src.fallback_data import get_real_stats
        except ImportError:
            from fallback_data import get_real_stats

        h_stats = get_real_stats(home_team)
        a_stats = get_real_stats(away_team)
        
        # Calculate Strength Score
        h_score = (h_stats['poss'] * 0.5) + (h_stats['shots_ot'] * 3) + (h_stats['corners'] * 2)
        a_score = (a_stats['poss'] * 0.5) + (a_stats['shots_ot'] * 3) + (a_stats['corners'] * 2)
        
        # Home Advantage
        h_score *= 1.15
        
        total_score = h_score + a_score
        
        h_prob = h_score / total_score
        a_prob = a_score / total_score
        draw_prob = 0.25
        
        h_prob = h_prob * (1 - draw_prob)
        a_prob = a_prob * (1 - draw_prob)
        
        return {
            'home_win': round(h_prob, 3),
            'draw': round(draw_prob, 3), 
            'away_win': round(a_prob, 3)
        }

    def predict_advanced_stats(self, home_team, away_team):
        """
        Estimates advanced stats (Corners, Shots, Cards, Fouls, BTTS).
        """
        try:
            from src.fallback_data import get_real_stats
        except ImportError:
            from fallback_data import get_real_stats
        
        probs = self.predict_match(home_team, away_team)
        
        h_stats = get_real_stats(home_team)
        a_stats = get_real_stats(away_team)
        
        # DOMINANCE FACTOR
        h_dominance = probs['home_win'] - 0.33 
        a_dominance = probs['away_win'] - 0.33
        
        # Corners & Shots
        projected_corners_h = h_stats['corners'] * (1 + (h_dominance * 0.5))
        projected_corners_a = a_stats['corners'] * (1 + (a_dominance * 0.5))
        
        projected_shots_h = h_stats['shots_ot'] * (1 + (h_dominance * 0.6))
        projected_shots_a = a_stats['shots_ot'] * (1 + (a_dominance * 0.6))
        
        # FOULS & CARDS Logic
        # Draw probability increases game intensity/fouls
        game_intensity = probs['draw'] * 4.0 
        
        projected_fouls_h = h_stats.get('fouls', 12.0) + (game_intensity * 0.5)
        projected_fouls_a = a_stats.get('fouls', 12.0) + (game_intensity * 0.5)
        
        projected_cards_h = h_stats['cards'] + (game_intensity * 0.1)
        projected_cards_a = a_stats['cards'] + (game_intensity * 0.1)
        
        # BTTS Logic
        mismatch = abs(probs['home_win'] - probs['away_win'])
        base_btts = (h_stats.get('btts', 0.5) + a_stats.get('btts', 0.5)) / 2
        projected_btts = base_btts - (mismatch * 0.2)
        
        # Goals Projection (xG)
        proj_goals_h = h_stats.get('xg', 1.2) * (1 + h_dominance)
        proj_goals_a = a_stats.get('xg', 1.2) * (1 + a_dominance)
        
        return {
            'corners': {
                'home': round(projected_corners_h, 1), 
                'away': round(projected_corners_a, 1), 
                'total': round(projected_corners_h + projected_corners_a, 1)
            },
            'shots_ot': {
                'home': round(projected_shots_h, 1), 
                'away': round(projected_shots_a, 1), 
                'total': round(projected_shots_h + projected_shots_a, 1)
            },
            'cards': {
                'home': round(projected_cards_h, 1), 
                'away': round(projected_cards_a, 1), 
                'total': round(projected_cards_h + projected_cards_a, 1)
            },
            'fouls': {
                'home': round(projected_fouls_h, 1),
                'away': round(projected_fouls_a, 1),
                'total': round(projected_fouls_h + projected_fouls_a, 1)
            },
            # Return raw values for dashboard to display
            'goals': {
                'home': round(proj_goals_h, 1),
                'away': round(proj_goals_a, 1),
                'btts_prob': round(projected_btts, 2)
            }
        }
