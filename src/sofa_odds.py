import requests
import logging
from datetime import datetime

logger = logging.getLogger("SofaOdds")

class SofaOdds:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.sofascore.com/',
            'Origin': 'https://www.sofascore.com'
        }

    def fetch_events(self, date_str=None):
        """Fetch all football events from SofaScore for a given date (YYYY-MM-DD)."""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
            
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        try:
            r = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if r.status_code == 200:
                return r.json().get('events', [])
            else:
                logger.warning(f"SofaScore Events Error: {r.status_code}")
        except Exception as e:
            logger.error(f"SofaScore Events Exception: {e}")
        return []

    def fetch_odds(self, event_id):
        """Fetch all betting odds for a SofaScore event.
        Markets: 1=1X2, 11=Double Chance, 12=BTTS, 6=Total Goals, etc.
        """
        # We try to fetch 'all' markets. 
        # Typically endpoint is /event/{id}/odds/1/all
        url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/1/all"
        try:
            r = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if r.status_code == 200:
                return r.json().get('markets', [])
        except Exception as e:
            logger.error(f"SofaScore Odds Exception ({event_id}): {e}")
        return []

    def get_market_odds(self, markets, market_name):
        """Helper to find specific market odds in the list."""
        # market_name map: "Full time" (1X2), "Both teams to score", "Total" (Goals), "Corner" (maybe in different endpoint?)
        # SofaScore variable names are like 'Full time', 'Double chance', 'Both teams to score', 'Total'
        for m in markets:
            if m.get('marketName') == market_name:
                return m.get('choices', [])
        return []

    def process_game_odds(self, game_id):
        """Returns a structured dict of odds for analysis."""
        markets = self.fetch_odds(game_id)
        if not markets: return None
        
        data = {
            "1X2": [],
            "BTTS": [],
            "Goals": [],
            "Corners": [], # Might not be in main 'all' endpoint, usually separate or in 'marketName' check
            "Cards": []
        }
        
        for m in markets:
            name = m.get('marketName')
            choices = m.get('choices', [])
            
            if name == "Full time":
                data["1X2"] = choices
            elif name == "Both teams to score":
                data["BTTS"] = choices
            elif name == "Total": # Over/Under Goals
                data["Goals"] = choices # List of groups usually (2.5, 3.5...)
                # SofaScore returns all lines.
            elif "Corner" in name: 
                # E.g. "Total corners" or "Corners 1x2"
                data["Corners"].append({"name": name, "choices": choices})
            elif "Card" in name or "Yellow" in name:
                data["Cards"].append({"name": name, "choices": choices})
                
        return data
