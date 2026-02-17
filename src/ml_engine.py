"""
ML Engine v2.0 — Anti-Bias Edition (Project Omniscience)

CRITICAL CHANGE: The model NO LONGER uses team names as features.
It uses ONLY numerical statistics. The AI cannot "know" if a team 
is Real Madrid or a Third Division club. It only sees:
- Attack strength, defense strength
- Recent form, goals scored/conceded
- Home advantage factor

This ELIMINATES the "prestige bias" where big clubs get inflated predictions.
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
import os
import sys
import logging

logger = logging.getLogger("OmniscienceML")
sys.path.append(os.path.dirname(__file__))


class ValueBetML:
    def __init__(self, data_path='data/historical_data.csv'):
        self.data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), data_path)
        
        # GradientBoosting > RandomForest for structured sports data
        self.model_res = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        )
        self.is_trained = False
        self.feature_columns = []  # Set during training
        
    def load_and_prep_data(self):
        """Load data and build ANONYMOUS features (no team names)."""
        if not os.path.exists(self.data_path):
            logger.warning(f"No historical data at {self.data_path}, using dummy data")
            return self._generate_dummy_data()
            
        df = pd.read_csv(self.data_path)
        df = df.dropna(subset=['HomeTeam', 'AwayTeam'])
        
        return df

    def _build_anonymous_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        ANTI-BIAS: Converts team names into pure numerical stats.
        The model NEVER sees a team name.
        """
        # Calculate rolling statistics per team
        team_stats = {}
        
        all_teams = pd.concat([df['HomeTeam'], df['AwayTeam']]).unique()
        
        for team in all_teams:
            home_games = df[df['HomeTeam'] == team]
            away_games = df[df['AwayTeam'] == team]
            
            all_games_count = len(home_games) + len(away_games)
            if all_games_count == 0:
                team_stats[team] = {
                    'attack': 1.0, 'defense': 1.0, 'form': 0.33,
                    'home_advantage': 0.45
                }
                continue
            
            # Attack: Goals scored per game
            home_scored = home_games['FTHG'].mean() if len(home_games) > 0 and 'FTHG' in df.columns else 1.2
            away_scored = away_games['FTAG'].mean() if len(away_games) > 0 and 'FTAG' in df.columns else 0.9
            attack = (home_scored + away_scored) / 2
            
            # Defense: Goals conceded per game (lower = better)
            home_conceded = home_games['FTAG'].mean() if len(home_games) > 0 and 'FTAG' in df.columns else 1.0
            away_conceded = away_games['FTHG'].mean() if len(away_games) > 0 and 'FTHG' in df.columns else 1.3
            defense = (home_conceded + away_conceded) / 2
            
            # Form: Win percentage
            wins = 0
            total = 0
            if 'FTR' in df.columns:
                wins += len(home_games[home_games['FTR'] == 'H'])
                wins += len(away_games[away_games['FTR'] == 'A'])
                total = all_games_count
            form = wins / max(total, 1)
            
            # Home advantage
            home_wins = len(home_games[home_games['FTR'] == 'H']) if 'FTR' in df.columns else 0
            home_adv = home_wins / max(len(home_games), 1)
            
            team_stats[team] = {
                'attack': round(attack, 3),
                'defense': round(defense, 3),
                'form': round(form, 3),
                'home_advantage': round(home_adv, 3)
            }
        
        # Build feature matrix — PURELY NUMERICAL
        features = []
        for _, row in df.iterrows():
            h = team_stats.get(row['HomeTeam'], {'attack': 1.0, 'defense': 1.0, 'form': 0.33, 'home_advantage': 0.45})
            a = team_stats.get(row['AwayTeam'], {'attack': 1.0, 'defense': 1.0, 'form': 0.33, 'home_advantage': 0.45})
            
            features.append({
                'h_attack': h['attack'],
                'h_defense': h['defense'],
                'h_form': h['form'],
                'h_home_adv': h['home_advantage'],
                'a_attack': a['attack'],
                'a_defense': a['defense'],
                'a_form': a['form'],
                # Derived features (interactions)
                'attack_diff': h['attack'] - a['attack'],
                'defense_diff': h['defense'] - a['defense'],
                'form_diff': h['form'] - a['form'],
            })
        
        features_df = pd.DataFrame(features)
        self.feature_columns = list(features_df.columns)
        self._team_stats = team_stats
        return features_df

    def train(self):
        """Train the model on anonymous features."""
        df = self.load_and_prep_data()
        
        if len(df) < 10:
            logger.warning("Not enough data to train (<10 matches)")
            return None

        X = self._build_anonymous_features(df)
        y = df['FTR'].map({'H': 0, 'D': 1, 'A': 2})
        
        # Drop any rows with NaN
        valid = ~y.isna()
        X = X[valid]
        y = y[valid]
        
        if len(X) < 10:
            return None
        
        # Cross-validation to estimate accuracy
        scores = cross_val_score(self.model_res, X, y, cv=min(5, len(X)), scoring='accuracy')
        logger.info(f"CV Accuracy: {scores.mean():.3f} (+/- {scores.std():.3f})")
        
        # Full train
        self.model_res.fit(X, y)
        self.is_trained = True
        
        return scores.mean()

    def predict_match(self, home_team, away_team):
        """
        Predict match result using ANONYMOUS features.
        If model isn't trained or team is unknown, returns neutral probs.
        """
        if not self.is_trained or not hasattr(self, '_team_stats'):
            return {'home_win': 0.33, 'draw': 0.33, 'away_win': 0.33}
        
        h = self._team_stats.get(home_team, {'attack': 1.0, 'defense': 1.0, 'form': 0.33, 'home_advantage': 0.45})
        a = self._team_stats.get(away_team, {'attack': 1.0, 'defense': 1.0, 'form': 0.33, 'home_advantage': 0.45})
        
        features = pd.DataFrame([{
            'h_attack': h['attack'],
            'h_defense': h['defense'],
            'h_form': h['form'],
            'h_home_adv': h['home_advantage'],
            'a_attack': a['attack'],
            'a_defense': a['defense'],
            'a_form': a['form'],
            'attack_diff': h['attack'] - a['attack'],
            'defense_diff': h['defense'] - a['defense'],
            'form_diff': h['form'] - a['form'],
        }])
        
        try:
            probs = self.model_res.predict_proba(features)[0]
            if len(probs) < 3:
                return {'home_win': probs[0], 'draw': 0.0, 'away_win': probs[-1]}
            return {
                'home_win': round(probs[0], 4),
                'draw': round(probs[1], 4),
                'away_win': round(probs[2], 4)
            }
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {'home_win': 0.33, 'draw': 0.33, 'away_win': 0.33}

    def predict_advanced_stats(self, home_team, away_team):
        """
        Estimates advanced stats (Corners, Shots, Cards, Fouls, BTTS, Goals)
        based on REAL season data.
        """
        try:
            from fallback_data import get_real_stats
        except ImportError:
            try:
                from src.fallback_data import get_real_stats
            except ImportError:
                return self._default_advanced_stats()
        
        probs = self.predict_match(home_team, away_team)
        h_stats = get_real_stats(home_team)
        a_stats = get_real_stats(away_team)
        
        h_dominance = probs['home_win'] - 0.33 
        a_dominance = probs['away_win'] - 0.33
        
        projected_corners_h = h_stats['corners'] * (1 + (h_dominance * 0.5))
        projected_corners_a = a_stats['corners'] * (1 + (a_dominance * 0.5))
        projected_shots_h = h_stats['shots_ot'] * (1 + (h_dominance * 0.6))
        projected_shots_a = a_stats['shots_ot'] * (1 + (a_dominance * 0.6))
        
        game_intensity = probs['draw'] * 3.0
        projected_cards_h = h_stats['cards'] + (game_intensity * 0.5)
        projected_cards_a = a_stats['cards'] + (game_intensity * 0.5)
        projected_fouls_h = h_stats.get('fouls', 12.0) + (game_intensity * 0.5)
        projected_fouls_a = a_stats.get('fouls', 12.0) + (game_intensity * 0.5)

        mismatch = abs(probs['home_win'] - probs['away_win'])
        base_btts = (h_stats.get('btts', 0.5) + a_stats.get('btts', 0.5)) / 2
        projected_btts = base_btts - (mismatch * 0.2)
        
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
            'goals': {
                'home': round(proj_goals_h, 1),
                'away': round(proj_goals_a, 1),
                'btts_prob': round(projected_btts, 2)
            }
        }

    def _generate_dummy_data(self):
        """Generates realistic dummy data for training when no CSV exists."""
        np.random.seed(42)
        teams = [f"Team_{chr(65+i)}" for i in range(20)]
        rows = []
        for _ in range(200):
            h = np.random.choice(teams)
            a = np.random.choice([t for t in teams if t != h])
            hg = np.random.poisson(1.5)
            ag = np.random.poisson(1.1)
            ftr = 'H' if hg > ag else ('A' if ag > hg else 'D')
            rows.append({'HomeTeam': h, 'AwayTeam': a, 'FTHG': hg, 'FTAG': ag, 'FTR': ftr})
        return pd.DataFrame(rows)

    def _default_advanced_stats(self):
        return {
            'corners': {'home': 5.0, 'away': 4.5, 'total': 9.5},
            'shots_ot': {'home': 4.0, 'away': 3.5, 'total': 7.5},
            'cards': {'home': 2.0, 'away': 2.0, 'total': 4.0},
            'fouls': {'home': 12.0, 'away': 12.0, 'total': 24.0},
            'goals': {'home': 1.3, 'away': 1.0, 'btts_prob': 0.48}
        }
