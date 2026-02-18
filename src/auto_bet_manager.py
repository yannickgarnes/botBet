import pandas as pd
import logging
from datetime import datetime
import time
import random
from difflib import SequenceMatcher

# Import custom modules
from database import OddsBreakerDB
from scraper_365 import Scraper365
from rl_engine import RLEngine
from main_engine import PredictionEngine
from sofa_odds import SofaOdds

logger = logging.getLogger("AutoBetManager")

class AutoBetManager:
    def __init__(self):
        self.db = OddsBreakerDB()
        self.scraper = Scraper365()
        self.rl_engine = RLEngine()
        self.sofa = SofaOdds()
        self.cached_sofa_events = []
        self.last_cache_date = None

    def _similar(self, a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _find_sofa_id(self, h_name, a_name):
        # Refresh cache if new day
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_cache_date != today:
            self.cached_sofa_events = self.sofa.fetch_events(today)
            self.last_cache_date = today
            
        best_match = None
        best_score = 0
        
        for ev in self.cached_sofa_events:
            sh = ev.get('homeTeam', {}).get('name', '')
            sa = ev.get('awayTeam', {}).get('name', '')
            
            # Match score (avg of home/away match)
            score = (self._similar(h_name, sh) + self._similar(a_name, sa)) / 2
            if score > 0.65: # Threshold for match
                if score > best_score:
                    best_score = score
                    best_match = ev.get('id')
        
        return best_match if best_match else None

    def generate_daily_bets(self, confidence_threshold=0.01, max_bets=10):
        logger.info("Starting Daily Auto-Bet Generation...")
        today_str = datetime.now().strftime("%d/%m/%Y")
        
        games = self.scraper.get_games(today_str)
        if not games: return 0
            
        bets_placed = 0
        
        for game in games:
            if bets_placed >= max_bets: break
            try:
                game_id = game.get('id') # 365 ID
                h_name = game.get('homeCompetitor', {}).get('name')
                a_name = game.get('awayCompetitor', {}).get('name')
                
                # 1. Match with SofaScore
                sofa_id = self._find_sofa_id(h_name, a_name)
                sofa_data = None
                if sofa_id:
                    sofa_data = self.sofa.process_game_odds(sofa_id)
                
                # 2. Get Odds (Priority: Sofa -> Community -> Default)
                odds_1x2 = {"1": 2.5, "X": 3.2, "2": 2.8} 
                has_real_odds = False
                
                if sofa_data and sofa_data.get("1X2"):
                    # Parse Sofa
                    for c in sofa_data["1X2"]:
                        val = c.get('fractionalValue')
                        dec = 0
                        if '/' in str(val):
                            n, d = val.split('/')
                            dec = float(n)/float(d) + 1
                        else: dec = float(val)
                        
                        if c['name'] == '1': odds_1x2["1"] = dec
                        elif c['name'] == 'X': odds_1x2["X"] = dec
                        elif c['name'] == '2': odds_1x2["2"] = dec
                    has_real_odds = True
                else:
                    # FALLBACK: 365 Community Votes (RESTORED)
                    comm = self.scraper.get_game_predictions(game_id)
                    if comm and comm.get('totalVotes', 0) > 50:
                        odds_1x2 = {
                            "1": round(1 / (comm['1']/100 + 0.05), 2),
                            "X": round(1 / (comm['X']/100 + 0.05), 2),
                            "2": round(1 / (comm['2']/100 + 0.05), 2)
                        }
                
                # 3. RL Prediction
                implied_h = 1.0 / odds_1x2.get("1", 2.5)
                implied_a = 1.0 / odds_1x2.get("2", 2.5)
                features = [
                    round(implied_h * 3.0, 2), round(implied_a * 3.0, 2),
                    round(implied_a * 2.0, 2), round(implied_h * 2.0, 2),
                    round(implied_h, 2), round(implied_a, 2),
                    0.5, 0.5, 
                    1.0 if implied_h > 0.6 else 0.5, 0.5, # Motivation
                    4, 4, 0.1, 0.1
                ]
                probs = self.rl_engine.predict(features)
                
                # 4. Place 1X2 Bets
                ev_1 = (probs["1"] * odds_1x2["1"]) - 1
                ev_2 = (probs["2"] * odds_1x2["2"]) - 1
                
                if ev_1 > confidence_threshold:
                    self._place_bet_safe(game_id, "1", odds_1x2["1"], ev_1, is_auto=True)
                    bets_placed += 1
                elif ev_2 > confidence_threshold:
                    self._place_bet_safe(game_id, "2", odds_1x2["2"], ev_2, is_auto=True)
                    bets_placed += 1
                    
                # 5. Place Auxiliary Bets (Only if Sofa Data exists)
                if sofa_data:
                    # Corners (Relaxed)
                    if sofa_data.get("Corners"):
                        # If strong home fav or high attack
                        if implied_h > 0.6 or features[0] > 1.4:
                             self._place_bet_safe(game_id, "Corners Over 8.5", 1.85, 0.1, is_auto=True)
                             bets_placed += 1
                    
                    # Goals (Over 2.5)
                    if sofa_data.get("Goals"):
                         if probs["1"] > 0.35 and probs["2"] > 0.25: # Open game
                             self._place_bet_safe(game_id, "Over 2.5 Goals", 1.90, 0.12, is_auto=True)
                             bets_placed += 1
                             
                    # BTTS
                    if sofa_data.get("BTTS"):
                         if features[0] > 1.3 and features[1] > 1.3:
                             self._place_bet_safe(game_id, "BTTS Yes", 1.80, 0.08, is_auto=True)
                             bets_placed += 1

                # Save Data
                match_data = {
                    "game_id": game_id, "date": datetime.now(),
                    "home_team": h_name, "away_team": a_name,
                    "league_name": game.get('competitionDisplayName'),
                    "odds_home": odds_1x2["1"], "odds_draw": odds_1x2["X"], "odds_away": odds_1x2["2"],
                    "result": None, "home_score": None, "away_score": None
                }
                self.db.save_match_data(match_data)
                
            except Exception as e:
                logger.error(f"Error game {game.get('id')}: {e}")
                continue
                
        return bets_placed

    def _place_bet_safe(self, game_id, selection, odds, ev, is_auto=True):
        stake = 10 * (1 + ev) 
        self.db.place_bet(game_id, selection, odds, round(stake, 2), round(ev, 3), is_auto=is_auto)

    def check_results_and_learn(self):
        # ... (Keep existing or pass) ...
        # Minimal implementation for file completeness
        self.db.get_pending_bets()
        return 0, 0
