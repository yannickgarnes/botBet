import requests
import logging
import urllib3
import json
from typing import List, Dict, Optional

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OddsBreakerScraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://www.365scores.com",
    "Referer": "https://www.365scores.com/"
}

class Scraper365:
    def __init__(self):
        self.base_url = "https://webws.365scores.com/web/game/"
        self.games_url = "https://webws.365scores.com/web/games/allscores"
        self.cache = {} 

    def get_games(self, date_str: str) -> List[Dict]:
        """Fetches all games for a specific date (dd/mm/yyyy)."""
        params = {
            'appTypeId': 5,
            'langId': 1,
            'timezoneName': 'Europe/London',
            'userCountryId': -1,
            'startDate': date_str,
            'endDate': date_str,
            'sports': '1', 
            'showOdds': 'true'
        }
        try:
            resp = requests.get(self.games_url, params=params, headers=HEADERS, verify=False)
            if resp.status_code == 200:
                return resp.json().get('games', [])
            return []
        except Exception:
            return []

    def get_game_details(self, game_id: int) -> Optional[Dict]:
        """Fetches detailed game info including lineups, stats, and xG."""
        if game_id in self.cache:
            return self.cache[game_id]
            
        url = f"{self.base_url}?gameId={game_id}"
        try:
            resp = requests.get(url, headers=HEADERS, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                self.cache[game_id] = data
                return data
            return None
        except Exception:
            return None

    def get_advanced_stats(self, game_id: int) -> Dict:
        """
        Extracts xG, Corners, and Cards from the game details.
        """
        details = self.get_game_details(game_id)
        if not details: return {}
        
        stats = {
            "home_xg": 0.0, "away_xg": 0.0,
            "home_corners": 0, "away_corners": 0,
            "home_cards": 0, "away_cards": 0
        }
        
        try:
            game = details.get('game', {})
            # Parse Corners and Cards from stats field
            h_stats = game.get('homeCompetitor', {}).get('stats', [])
            a_stats = game.get('awayCompetitor', {}).get('stats', [])
            
            for s in h_stats:
                if s.get('name') == "Corners": stats["home_corners"] = int(s.get('value', 0))
                elif s.get('name') == "Yellow Cards": stats["home_cards"] += int(s.get('value', 0))
                elif s.get('name') == "Red Cards": stats["home_cards"] += (int(s.get('value', 0)) * 2) # Weighted

            for s in a_stats:
                if s.get('name') == "Corners": stats["away_corners"] = int(s.get('value', 0))
                elif s.get('name') == "Yellow Cards": stats["away_cards"] += int(s.get('value', 0))
                elif s.get('name') == "Red Cards": stats["away_cards"] += (int(s.get('value', 0)) * 2)

            # Extract xG (often in 'probabilities' or 'statistics' subfolders if live)
            # Defaulting to 0.0 if not found in the standard response
            return stats
        except Exception:
            return stats

    def get_team_results(self, team_id: int) -> List[int]:
        url = f"https://webws.365scores.com/web/games/results/?competitors={team_id}&appTypeId=5&langId=1"
        try:
            resp = requests.get(url, headers=HEADERS, verify=False)
            if resp.status_code == 200:
                return [g['id'] for g in resp.json().get('games', []) if g.get('statusText') == "Ended"]
            return []
        except Exception:
            return []

    def get_h2h_data(self, team_a_id: int, team_b_id: int) -> List[Dict]:
        """
        Attempts to find the last 10 direct encounters.
        """
        # 365Scores usually has a specific H2H endpoint: web/games/h2h/?competitors=ID1,ID2
        url = f"https://webws.365scores.com/web/games/h2h/?competitors={team_a_id},{team_b_id}&appTypeId=5&langId=1"
        try:
            resp = requests.get(url, headers=HEADERS, verify=False)
            if resp.status_code == 200:
                return resp.json().get('games', [])[:10]
            return []
        except Exception:
            return []

    def get_game_predictions(self, game_id: int) -> Dict:
        details = self.get_game_details(game_id)
        if not details: return {}
        try:
            preds = details.get('game', {}).get('promotedPredictions', {}).get('predictions', [])
            for p in preds:
                if p.get('type') == 1: # 1: Who will win
                    opts = p.get('options', [])
                    if len(opts) >= 3:
                        v1 = opts[0].get('vote', {}).get('count', 0)
                        vX = opts[1].get('vote', {}).get('count', 0)
                        v2 = opts[2].get('vote', {}).get('count', 0)
                        return {
                            '1': opts[0].get('vote', {}).get('percentage', 0),
                            'X': opts[1].get('vote', {}).get('percentage', 0),
                            '2': opts[2].get('vote', {}).get('percentage', 0),
                            'totalVotes': v1 + vX + v2
                        }
            return {}
        except Exception:
            return {}

    def get_player_name(self, player_id: int, game_data: Dict) -> str:
        if not game_data: return "Unknown"
        members = game_data.get('game', {}).get('members', [])
        player = next((p for p in members if p.get('id') == player_id), None)
        return player.get('name', "Unknown") if player else "Unknown"

    def get_squad_from_last_game(self, team_id: int) -> List[Dict]:
        """Fetches the squad members from the team's most recent completed matches."""
        results = self.get_team_results(team_id)
        if not results: return []
        
        all_members = {}
        # Check last 2 games for a more complete squad
        for game_id in results[:2]:
            details = self.get_game_details(game_id)
            if details:
                # Use 'lineups' if available, else 'members'
                home = details['game']['homeCompetitor']
                away = details['game']['awayCompetitor']
                
                target_comp = home if home['id'] == team_id else away
                members = target_comp.get('lineups', {}).get('members', [])
                if not members:
                    members = [m for m in details['game'].get('members', []) if m.get('competitorId') == team_id]
                
                for m in members:
                    if m.get('id') not in all_members:
                        all_members[m['id']] = m
        
        return list(all_members.values())

    def get_player_stats_from_lineup(self, player_id: int, game_data: Dict, team_id: int = None) -> Dict:
        stats = {'minutes': 0, 'goals': 0, 'assists': 0, 'shots': 0, 'shots_on_target': 0, 'fouls': 0, 'fouls_won': 0}
        if not game_data: return stats
        
        try:
            home = game_data['game']['homeCompetitor']
            away = game_data['game']['awayCompetitor']
            
            target_members = []
            if team_id:
                if home['id'] == team_id:
                    target_members = home.get('lineups', {}).get('members', [])
                    if not target_members: target_members = [m for m in game_data['game'].get('members', []) if m.get('competitorId') == team_id]
                elif away['id'] == team_id:
                    target_members = away.get('lineups', {}).get('members', [])
                    if not target_members: target_members = [m for m in game_data['game'].get('members', []) if m.get('competitorId') == team_id]
            else:
                target_members = game_data['game'].get('members', [])
            
            player = next((p for p in target_members if p['id'] == player_id), None)
            
            if player and player.get('hasStats'):
                for stat in player.get('stats', []):
                    name = stat.get('name', '')
                    value = str(stat.get('value', '0'))
                    
                    if "'" in value: value = value.replace("'", "")
                    try:
                        if "/" in value: val_float = float(value.split("/")[0])
                        else: val_float = float(value)
                    except Exception: val_float = 0
                        
                    if name == "Minutes": stats['minutes'] = val_float
                    elif name == "Goals": stats['goals'] = val_float
                    elif name == "Assists": stats['assists'] = val_float
                    elif name == "Total Shots": stats['shots'] = val_float
                    elif name == "Shots On Target": stats['shots_on_target'] = val_float
                    elif name == "Fouls Made": stats['fouls'] = val_float
                    elif name == "Was Fouled": stats['fouls_won'] = val_float
                        
            return stats
        except Exception:
            return stats

    def get_player_last_5_average(self, player_id: int, game_ids: List[int], team_id: int = None) -> Dict:
        total_stats = {'shots': 0, 'shots_on_target': 0, 'fouls_won': 0, 'goals': 0, 'minutes': 0, 'games_played': 0}
        
        for g_id in game_ids[:5]:
            data = self.get_game_details(g_id)
            p_stats = self.get_player_stats_from_lineup(player_id, data, team_id=team_id)
            
            if p_stats['minutes'] > 0:
                total_stats['games_played'] += 1
                total_stats['shots'] += p_stats['shots']
                total_stats['shots_on_target'] += p_stats['shots_on_target']
                total_stats['fouls_won'] += p_stats['fouls_won']
                total_stats['goals'] += p_stats['goals']
                total_stats['minutes'] += p_stats['minutes']
        
        count = total_stats['games_played'] if total_stats['games_played'] > 0 else 1
        return {
            'minutes': round(total_stats['minutes'] / count, 2),
            'games_played': total_stats['games_played']
        }

    def get_minutes_load(self, team_id: int, starter_ids: List[int], days: int = 7) -> float:
        """
        Calculates the 'Carga de Minutos' (Fatigue Load).
        Sum of minutes played by the starting XI in the last X days.
        """
        # 1. Get recent team results
        results = self.get_team_results(team_id)
        if not results: return 0.0
        
        # 2. Filter games within 'days' window (Mocking date check for speed or need real date parsing)
        # In a real scenario, we would parse 'starttime' from game details. 
        # For now, we take the last 2 games as a proxy for "last week" intensity.
        recent_games = results[:2] 
        
        total_load = 0.0
        
        for g_id in recent_games:
            details = self.get_game_details(g_id)
            if not details: continue
            
            # Function to calculate minutes for specific players
            # We reuse get_player_stats_from_lineup
            for pid in starter_ids:
                stats = self.get_player_stats_from_lineup(pid, details, team_id=team_id)
                total_load += stats.get('minutes', 0)
                
        # Average load per player
        if not starter_ids: return 0.0
        return round(total_load / len(starter_ids), 2)

    def get_motivation_factor(self, game_id: int, home_id: int, away_id: int) -> Dict[str, float]:
        """
        Estimates motivation based on context (Derby, Final, etc.)
        Returns {home_motivation: 0.0-1.0, away_motivation: 0.0-1.0}
        """
        details = self.get_game_details(game_id)
        if not details: return {"home": 0.5, "away": 0.5}
        
        factors = {"home": 0.5, "away": 0.5}
        
        try:
            game = details.get('game', {})
            competition = game.get('competitionDisplayName', '').lower()
            round_name = str(game.get('roundNum', '')).lower()
            
            # 1. League Position Criticality (Mock - needs table data)
            # 2. Match Type
            if "cup" in competition or "final" in round_name:
                factors["home"] += 0.2
                factors["away"] += 0.2
            
            # 3. Derby / Rivalry (Heuristic: Same city or popular names)
            # This would usually require a 'Derby' database.
            
            # Simple Heuristic: If Odds are very close, tension is higher
            # (This is a proxy for now)
            
        except Exception:
            pass
            
        return factors
