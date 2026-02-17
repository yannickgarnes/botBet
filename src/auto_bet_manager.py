import pandas as pd
import logging
from datetime import datetime
import time

# Import custom modules
from database import OddsBreakerDB
from scraper_365 import Scraper365
from rl_engine import RLEngine
from main_engine import PredictionEngine

logger = logging.getLogger("AutoBetManager")

class AutoBetManager:
    def __init__(self):
        self.db = OddsBreakerDB()
        self.scraper = Scraper365()
        self.rl_engine = RLEngine()
        # Fallback engine for probabilities if RL is uncertain? 
        # Actually RL engine gives probs directly.
        
    def generate_daily_bets(self, confidence_threshold=0.15, max_bets=5):
        """
        Scans today's games, uses RL Engine to predict, and places bets 
        if Value > Threshold.
        """
        logger.info("Starting Daily Auto-Bet Generation...")
        today_str = datetime.now().strftime("%d/%m/%Y")
        
        # 1. Fetch Games
        games = self.scraper.get_games(today_str)
        if not games:
            logger.info("No games found today.")
            return 0
            
        bets_placed = 0
        
        for game in games:
            if bets_placed >= max_bets:
                break
                
            try:
                game_id = game.get('id')
                h_name = game.get('homeCompetitor', {}).get('name')
                a_name = game.get('awayCompetitor', {}).get('name')
                status_text = game.get('statusText', '')
                is_finished = status_text == 'Ended' or game.get('completion') == 100
                
                # Check if already bet
                # (Ideally DB check here, simplified for now)
                
                # 4. Get Odds (First, to derive features!)
                # If scraping 365, odds might be hidden. 
                odds = {"1": 2.5, "X": 3.2, "2": 2.8} # Placeholder
                
                # Check 365 community as proxy for odds
                comm = self.scraper.get_game_predictions(game_id)
                if comm and comm.get('totalVotes', 0) > 100:
                    odds = {
                        "1": round(1 / (comm['1']/100 + 0.05), 2),
                        "X": round(1 / (comm['X']/100 + 0.05), 2),
                        "2": round(1 / (comm['2']/100 + 0.05), 2)
                    }

                # 2. Build Features (SMART HEURISTIC based on Odds)
                # Instead of static values, we derive relative strength from the odds.
                # This makes the AI "understand" who is the favorite.
                implied_h = 1.0 / odds.get("1", 2.5)
                implied_a = 1.0 / odds.get("2", 2.5)
                
                features = [
                    round(implied_h * 3.0, 2),  # Home Attack (Stronger if favorite)
                    round(implied_a * 3.0, 2),  # Away Attack
                    round(implied_a * 2.0, 2),  # Home Defense (Good if opponent weak)
                    round(implied_h * 2.0, 2),  # Away Defense
                    round(implied_h, 2),        # Home Form
                    round(implied_a, 2),        # Away Form
                    0.5, 0.5,                   # Load (Unknown)
                    0.8 if implied_h > 0.6 else 0.5, # Motivation (Higher if heavy fav)
                    0.5,
                    4, 4,                       # Days Rest
                    0.1, 0.1                    # Weather
                ]
                
                # 3. Predict with RL
                probs = self.rl_engine.predict(features)
                
                # 5. Calculate EV
                ev_1 = (probs["1"] * odds["1"]) - 1
                ev_2 = (probs["2"] * odds["2"]) - 1
                
                selection = None
                chosen_odds = 0
                chosen_ev = 0
                
                if ev_1 > confidence_threshold:
                    selection = "1"
                    chosen_odds = odds["1"]
                    chosen_ev = ev_1
                elif ev_2 > confidence_threshold:
                    selection = "2"
                    chosen_odds = odds["2"]
                    chosen_ev = ev_2
                    
                if selection:
                    # Determine Result if finished
                    real_result = None
                    if is_finished:
                         h_s = game.get('homeCompetitor', {}).get('score', -1)
                         a_s = game.get('awayCompetitor', {}).get('score', -1)
                         if h_s > a_s: real_result = "1"
                         elif a_s > h_s: real_result = "2"
                         else: real_result = "X"

                    # Save Match Data first (Reference Integrity)
                    match_data = {
                        "game_id": game_id,
                        "date": datetime.now(), # Approximate
                        "home_team": h_name,
                        "away_team": a_name,
                        "league_name": game.get('competitionDisplayName'),
                        "odds_home": odds["1"],
                        "odds_draw": odds["X"],
                        "odds_away": odds["2"],
                        "result": real_result if is_finished else None,
                        "home_score": game.get('homeCompetitor', {}).get('score') if is_finished else None,
                        "away_score": game.get('awayCompetitor', {}).get('score') if is_finished else None
                    }
                    
                    # Save Deep Data (so we can train later!)
                    deep_data = {
                         "home_minutes_load": features[6]*900, "away_minutes_load": features[7]*900,
                         "home_motivation_score": features[8], "away_motivation_score": features[9],
                         "home_days_rest": int(features[10]*7), "away_days_rest": int(features[11]*7),
                         "home_attack_strength": features[0], "away_attack_strength": features[1],
                         "home_defense_strength": features[2], "away_defense_strength": features[3],
                         "home_form": features[4], "away_form": features[5],
                         "wind_factor": features[12], "rain_factor": features[13]
                    }
                    self.db.save_match_data(match_data, deep_data) # Re-save with deep
                    
                    # Place Bet
                    stake = 10 * (1 + chosen_ev) # Kelly-ish
                    # Check if allowed directly in a loop w/o duplicates logic (DB handles duplicates usually via ID but here we use SERIAL)
                    self.db.place_bet(game_id, selection, chosen_odds, round(stake, 2), round(chosen_ev, 3), is_auto=True)
                    bets_placed += 1
                    
                    # --- INSTANT LEARNING FOR FINISHED GAMES ---
                    if is_finished and real_result:
                        # 1. Resolve
                        # We need the bet_id we just created. 
                        # Since we don't have it easily returned, we can fetch pending for this game
                        # Or just rely on the next 'check_results_and_learn' call.
                        # BUT, user wants it 'incredible'. Let's trigger a check immediately.
                        pass # We will call check_results_and_learn() at the end of the batch in dashboard.py

                    logger.info(f"Auto-Bet Placed: {h_name} vs {a_name} -> {selection} @ {chosen_odds} (Finished: {is_finished})")
                    
            except Exception as e:
                logger.error(f"Error processing game {game.get('id')}: {e}")
                continue
                
        return bets_placed

    def check_results_and_learn(self):
        """
        Checks pending bets. If match ended:
        1. Update Bet Status (Win/Loss)
        2. Train RL Model (Back-loop)
        """
        pending = self.db.get_pending_bets()
        if not pending:
            return 0, 0 # resolved, learned
        
        resolved_count = 0
        learned_count = 0
        
        for bet in pending:
            # bet: (bet_id, game_id, selection, odds, stake, result, home, away)
            bet_id, game_id, selection, odds, stake, db_result, h_team, a_team = bet
            
            # 1. Check if result is already in DB (from other processes)
            final_result = db_result
            
            # 2. If not in DB, scrape it
            if not final_result:
                details = self.scraper.get_game_details(game_id)
                if details and details.get('game', {}).get('statusText') == 'Ended':
                    h_score = details['game']['homeCompetitor']['score']
                    a_score = details['game']['awayCompetitor']['score']
                    
                    if h_score > a_score: final_result = "1"
                    elif a_score > h_score: final_result = "2"
                    else: final_result = "X"
                    
                    # Update DB with result
                    match_data = {
                        "game_id": game_id,
                        "home_score": h_score,
                        "away_score": a_score,
                        "result": final_result
                        # Other fields optional for update
                    }
                    self.db.save_match_data(match_data) # Updates existing
            
            # 3. Resolve Bet & Learn
            if final_result:
                # Resolve PnL
                won = (selection == final_result)
                pnl = (stake * odds - stake) if won else -stake
                status = "WON" if won else "LOST"
                
                self.db.resolve_bet(bet_id, status, pnl)
                resolved_count += 1
                
                # --- LEARNING STEP ---
                # Retrieve features from DB to train
                # We replicate the query from get_training_data but for single ID
                rows = self.db.execute_query("""
                    SELECT 
                        home_attack_strength, away_attack_strength,
                        home_defense_strength, away_defense_strength,
                        home_form, away_form,
                        home_minutes_load / 900.0, away_minutes_load / 900.0,
                        home_motivation_score, away_motivation_score,
                        LEAST(home_days_rest / 7.0, 1.0), LEAST(away_days_rest / 7.0, 1.0),
                        wind_factor, rain_factor
                    FROM features_deep_data
                    WHERE game_id = %s
                """, (game_id,), fetch=True)
                
                if rows:
                    features = list(rows[0])
                    # Target index: 1->0, X->1, 2->2
                    target_map = {"1": 0, "X": 1, "2": 2}
                    target_idx = target_map.get(final_result, 1)
                    
                    loss = self.rl_engine.train_step(features, target_idx)
                    self.db.mark_bet_as_learned(bet_id)
                    learned_count += 1
                    logger.info(f"Learned from {h_team} vs {a_team} (Loss: {loss:.4f})")
        
        # Save model after batch learning
        if learned_count > 0:
            self.rl_engine.save_model()
            
        return resolved_count, learned_count
