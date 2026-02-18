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
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_cache_date != today:
            self.cached_sofa_events = self.sofa.fetch_events(today)
            self.last_cache_date = today
            
        best_match = None
        best_score = 0
        for ev in self.cached_sofa_events:
            sh = ev.get('homeTeam', {}).get('name', '')
            sa = ev.get('awayTeam', {}).get('name', '')
            score = (self._similar(h_name, sh) + self._similar(a_name, sa)) / 2
            if score > 0.65 and score > best_score:
                best_score = score
                best_match = ev.get('id')
        return best_match if best_match else None

    def generate_daily_bets(self, confidence_threshold=0.01, max_bets=15):
        logger.info("Starting Daily Auto-Bet Generation (ULTRA MODE)...")
        today_str = datetime.now().strftime("%d/%m/%Y")
        games = self.scraper.get_games(today_str)
        if not games: return 0
        bets_placed = 0
        
        for game in games:
            if bets_placed >= max_bets: break
            try:
                game_id = game.get('id')
                h_name = game.get('homeCompetitor', {}).get('name')
                a_name = game.get('awayCompetitor', {}).get('name')
                
                sofa_id = self._find_sofa_id(h_name, a_name)
                sofa_data = self.sofa.process_game_odds(sofa_id) if sofa_id else None
                
                odds_1x2 = {"1": 2.5, "X": 3.2, "2": 2.8} 
                if sofa_data and sofa_data.get("1X2"):
                    for c in sofa_data["1X2"]:
                        val = c.get('fractionalValue')
                        dec = float(val.split('/')[0])/float(val.split('/')[1]) + 1 if '/' in str(val) else float(val)
                        if c['name'] == '1': odds_1x2["1"] = dec
                        elif c['name'] == 'X': odds_1x2["X"] = dec
                        elif c['name'] == '2': odds_1x2["2"] = dec
                else:
                    comm = self.scraper.get_game_predictions(game_id)
                    if comm and comm.get('totalVotes', 0) > 50:
                        odds_1x2 = {
                            "1": round(1 / (comm['1']/100 + 0.05), 2),
                            "X": round(1 / (comm['X']/100 + 0.05), 2),
                            "2": round(1 / (comm['2']/100 + 0.05), 2)
                        }
                
                implied_h = 1.0 / odds_1x2.get("1", 2.5)
                implied_a = 1.0 / odds_1x2.get("2", 2.5)
                features = [
                    round(implied_h * 3.0, 2), round(implied_a * 3.0, 2),
                    round(implied_a * 2.0, 2), round(implied_h * 2.0, 2),
                    round(implied_h, 2), round(implied_a, 2),
                    0.5, 0.5, 
                    1.0 if implied_h > 0.6 else 0.5, 0.5, 
                    4, 4, 0.1, 0.1
                ]
                probs = self.rl_engine.predict(features)
                
                ev_1 = (probs["1"] * odds_1x2["1"]) - 1
                ev_2 = (probs["2"] * odds_1x2["2"]) - 1
                
                # BETTING LOGIC (Relaxed for Action)
                if ev_1 > confidence_threshold:
                    self._place_bet_safe(game_id, "1", odds_1x2["1"], ev_1)
                    bets_placed += 1
                elif ev_2 > confidence_threshold:
                    self._place_bet_safe(game_id, "2", odds_1x2["2"], ev_2)
                    bets_placed += 1
                    
                if sofa_data:
                    # CORNERS: Ultra Aggressive
                    # If Home implied > 55% (Strong Favorite) OR High Attack -> Bet Over Corners
                    if sofa_data.get("Corners") and (implied_h > 0.55 or features[0] > 1.3):
                         self._place_bet_safe(game_id, "Corners Over 8.5", 1.85, 0.15) # Boosted EV
                         bets_placed += 1
                    
                    # GOALS: Open Game
                    if sofa_data.get("Goals") and (probs["1"] > 0.35 and probs["2"] > 0.25):
                         self._place_bet_safe(game_id, "Over 2.5 Goals", 1.90, 0.12)
                         bets_placed += 1
                    
                    # BTTS: Balanced Teams
                    if sofa_data.get("BTTS") and abs(implied_h - implied_a) < 0.2:
                         self._place_bet_safe(game_id, "BTTS Yes", 1.80, 0.10)
                         bets_placed += 1

                self.db.save_match_data({
                    "game_id": game_id, "date": datetime.now(),
                    "home_team": h_name, "away_team": a_name,
                    "league_name": game.get('competitionDisplayName'),
                    "odds_home": odds_1x2["1"], "odds_draw": odds_1x2["X"], "odds_away": odds_1x2["2"],
                    "result": None, "home_score": None, "away_score": None
                })
            except Exception as e:
                logger.error(f"Error game {game.get('id')}: {e}")
                continue
        return bets_placed

    def _place_bet_safe(self, game_id, selection, odds, ev, is_auto=True):
        try:
            stake = 10 * (1 + ev) 
            self.db.place_bet(game_id, selection, odds, round(stake, 2), round(ev, 3), is_auto=is_auto)
        except Exception: pass

    def check_results_and_learn(self):
        logger.info("Resolving bets...")
        pending = self.db.get_pending_bets()
        if not pending: return 0, 0
        
        resolved = 0
        training_samples = []
        
        today = datetime.now().strftime("%d/%m/%Y")
        finished_games = {g['id']: (g['homeCompetitor']['score'], g['awayCompetitor']['score']) 
                         for g in self.scraper.get_games(today) if g.get('status',{}).get('type') == 'Finished'}

        for bet in pending:
            try:
                # SAFE ACCESS (If bet is dict or tuple)
                if isinstance(bet, dict): gid = bet['game_id']; lbl = bet['selection']
                else: gid = bet[1]; lbl = bet[2] # Fallback for tuples if DB not fixed
                
                if gid not in finished_games: continue
                
                h, a = finished_games[gid]
                won = False
                
                if lbl == "1": won = h > a
                elif lbl == "X": won = h == a
                elif lbl == "2": won = a > h
                elif "Over" in lbl: won = (h+a) > 2.5
                elif "BTTS" in lbl: won = (h>0 and a>0)
                
                if isinstance(bet, dict): bid = bet['bet_id']; stake = bet['stake']; odds = bet['odds']
                else: bid = bet[0]; stake = bet[4]; odds = bet[3]
                
                pnl = (stake * odds) - stake if won else -stake
                self.db.update_bet_status(bid, "WON" if won else "LOST", pnl)
                resolved += 1
                
                match = self.db.get_match_data(gid)
                if match:
                   if isinstance(match, dict): oh = match['odds_home']; oa = match['odds_away']
                   else: oh = match[7]; oa = match[9] 
                   
                   ih = 1/(oh or 2.5); ia = 1/(oa or 2.5)
                   feats = [ih*3, ia*3, ia*2, ih*2, ih, ia, 0.5, 0.5, 1 if ih>0.6 else 0.5, 0.5, 4, 4, 0.1, 0.1]
                   targ = [1,0,0] if h>a else ([0,1,0] if h==a else [0,0,1])
                   training_samples.append((feats, targ))
            except Exception as e: 
                logger.error(f"Resolution Error: {e}")
            
        if training_samples:
            self.rl_engine.train_on_batch([x[0] for x in training_samples], [x[1] for x in training_samples])
            self.rl_engine.save_model() # PERSIST KNOWLEDGE
            logger.info("Model trained and SAVED.")
            
        return resolved, len(training_samples)
