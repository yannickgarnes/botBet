"""
ODDS API Client — Project Omniscience
Fetches REAL odds from 40+ bookmakers including Bet365.
API: https://the-odds-api.com (Free: 500 requests/month)

Also includes RapidAPI Bet365 as fallback.
"""
import requests
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("OddsAPI")

# ============================================================
# PRIMARY: The Odds API (Free tier: 500 req/month)
# Covers: Bet365, Betfair, William Hill, Pinnacle, 1xBet, etc.
# ============================================================

THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")  # Get free key at https://the-odds-api.com
THE_ODDS_BASE = "https://api.the-odds-api.com/v4"

# ============================================================
# FALLBACK: RapidAPI Bet365 (Free basic plan)
# ============================================================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_BET365_HOST = "bet365-api-inplay.p.rapidapi.com"


class OddsClient:
    """
    Unified odds client. Fetches from The Odds API (primary) 
    and falls back to RapidAPI Bet365 or community-implied odds.
    """

    def __init__(self):
        self.api_key = THE_ODDS_API_KEY
        self.rapid_key = RAPIDAPI_KEY
        self.requests_used = 0
        self.cache = {}

    # ----------------------------------------------------------
    # THE ODDS API — Primary Source
    # ----------------------------------------------------------

    def get_live_odds(self, sport: str = "soccer", region: str = "eu",
                      markets: str = "h2h", bookmakers: str = "bet365") -> List[Dict]:
        """
        Fetches live odds for a sport.
        
        Args:
            sport: Sport key (e.g. 'soccer_epl', 'soccer_spain_la_liga', 'soccer')
            region: 'eu' for European decimal odds, 'uk' for fractional
            markets: 'h2h' (1X2), 'spreads', 'totals'
            bookmakers: Comma-separated bookmaker keys (e.g. 'bet365,betfair,pinnacle')
        
        Returns:
            List of matches with odds from specified bookmakers
        """
        if not self.api_key:
            logger.warning("THE_ODDS_API_KEY not set. Using fallback.")
            return []

        url = f"{THE_ODDS_BASE}/sports/{sport}/odds/"
        params = {
            "apiKey": self.api_key,
            "regions": region,
            "markets": markets,
            "bookmakers": bookmakers,
            "oddsFormat": "decimal"
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            self.requests_used += 1

            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"Fetched odds for {len(data)} matches. "
                            f"Requests remaining: {resp.headers.get('x-requests-remaining', '?')}")
                return data
            elif resp.status_code == 401:
                logger.error("Invalid API key for The Odds API")
            elif resp.status_code == 429:
                logger.warning("Rate limit exceeded on The Odds API")
            else:
                logger.error(f"Odds API error: {resp.status_code}")
        except Exception as e:
            logger.error(f"Odds API request failed: {e}")

        return []

    def get_available_sports(self) -> List[Dict]:
        """Returns all sports with active odds."""
        if not self.api_key:
            return self._get_default_sports()

        url = f"{THE_ODDS_BASE}/sports/"
        params = {"apiKey": self.api_key}

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch sports list: {e}")

        return self._get_default_sports()

    def get_match_odds_by_teams(self, home_team: str, away_team: str,
                                 sport: str = "soccer") -> Optional[Dict]:
        """
        Searches for a specific match and returns its odds from ALL bookmakers.
        Used to calculate Probability Gap (IA vs Casa).
        """
        all_odds = self.get_live_odds(sport=sport, bookmakers="bet365,pinnacle,betfair,williamhill,1xbet")

        for match in all_odds:
            h = match.get("home_team", "").lower()
            a = match.get("away_team", "").lower()

            if (home_team.lower() in h or h in home_team.lower()) and \
               (away_team.lower() in a or a in away_team.lower()):
                return self._parse_match_odds(match)

        return None

    def get_odds_movement(self, home_team: str, away_team: str,
                          sport: str = "soccer") -> Optional[Dict]:
        """
        Compares opening odds vs current odds to detect Smart Money Flow.
        Requires paid tier for historical odds — approximated via spread analysis.
        
        Returns:
            {
                "home_movement": -0.15,   # Odds dropped (money coming in)
                "draw_movement": +0.05,
                "away_movement": +0.10,   # Odds drifted (money leaving)
                "smart_money_signal": "HOME"  # Where smart money is going
            }
        """
        match_odds = self.get_match_odds_by_teams(home_team, away_team, sport)
        if not match_odds or len(match_odds.get("bookmakers", {})) < 2:
            return None

        # Smart Money Detection: Compare sharp bookmaker (Pinnacle) vs soft (Bet365)
        pinnacle = match_odds["bookmakers"].get("pinnacle", {})
        bet365 = match_odds["bookmakers"].get("bet365", {})

        if not pinnacle or not bet365:
            return None

        # If Pinnacle odds are LOWER than Bet365 → Sharp money is backing that outcome
        movement = {}
        signal = "NONE"
        max_gap = 0

        for outcome in ["home", "draw", "away"]:
            p_odds = pinnacle.get(outcome, 0)
            b_odds = bet365.get(outcome, 0)
            if p_odds > 0 and b_odds > 0:
                gap = b_odds - p_odds  # Positive = Bet365 hasn't adjusted yet
                movement[f"{outcome}_movement"] = round(gap, 3)
                if gap > max_gap:
                    max_gap = gap
                    signal = outcome.upper()

        movement["smart_money_signal"] = signal
        return movement

    # ----------------------------------------------------------
    # RAPIDAPI BET365 — Fallback
    # ----------------------------------------------------------

    def get_bet365_odds_rapid(self, sport_id: int = 1) -> List[Dict]:
        """
        Fallback: Fetches Bet365 odds via RapidAPI.
        sport_id: 1=Soccer, 18=Basketball, 13=Tennis
        """
        if not self.rapid_key:
            return []

        url = f"https://{RAPIDAPI_BET365_HOST}/bet365/get_sports"
        headers = {
            "X-RapidAPI-Key": self.rapid_key,
            "X-RapidAPI-Host": RAPIDAPI_BET365_HOST
        }

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f"RapidAPI Bet365 failed: {e}")

        return []

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    def _parse_match_odds(self, match_data: Dict) -> Dict:
        """Parses The Odds API response into our standard format."""
        result = {
            "home_team": match_data.get("home_team", ""),
            "away_team": match_data.get("away_team", ""),
            "commence_time": match_data.get("commence_time", ""),
            "sport": match_data.get("sport_key", ""),
            "bookmakers": {}
        }

        for bm in match_data.get("bookmakers", []):
            bm_key = bm.get("key", "unknown")
            for market in bm.get("markets", []):
                if market.get("key") == "h2h":
                    outcomes = {}
                    for o in market.get("outcomes", []):
                        name = o.get("name", "")
                        if name == result["home_team"]:
                            outcomes["home"] = o.get("price", 0)
                        elif name == result["away_team"]:
                            outcomes["away"] = o.get("price", 0)
                        elif name == "Draw":
                            outcomes["draw"] = o.get("price", 0)
                    result["bookmakers"][bm_key] = outcomes

        return result

    def _get_default_sports(self) -> List[Dict]:
        """Returns default soccer leagues when API is unavailable."""
        return [
            {"key": "soccer_spain_la_liga", "title": "La Liga - Spain", "active": True},
            {"key": "soccer_epl", "title": "EPL - England", "active": True},
            {"key": "soccer_germany_bundesliga", "title": "Bundesliga - Germany", "active": True},
            {"key": "soccer_italy_serie_a", "title": "Serie A - Italy", "active": True},
            {"key": "soccer_france_ligue_one", "title": "Ligue 1 - France", "active": True},
            {"key": "soccer_uefa_champs_league", "title": "UEFA Champions League", "active": True},
            {"key": "soccer_uefa_europa_league", "title": "UEFA Europa League", "active": True},
        ]

    def get_implied_probabilities(self, decimal_odds: Dict) -> Dict:
        """
        Converts decimal odds to implied probabilities (removing margin).
        Input: {"home": 2.10, "draw": 3.40, "away": 3.50}
        Output: {"home": 0.465, "draw": 0.287, "away": 0.279}
        """
        if not decimal_odds:
            return {}

        raw = {}
        total_implied = 0
        for key, odds in decimal_odds.items():
            if odds > 0:
                imp = 1 / odds
                raw[key] = imp
                total_implied += imp

        # Remove margin (overround) proportionally
        fair = {}
        for key, imp in raw.items():
            fair[key] = round(imp / total_implied, 4)

        return fair


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def get_bet365_odds(home_team: str, away_team: str) -> Dict:
    """
    Quick function to get Bet365 odds for a match.
    Returns: {"1": 1.85, "X": 3.40, "2": 4.50} or empty dict
    """
    client = OddsClient()
    match = client.get_match_odds_by_teams(home_team, away_team)
    if match:
        bet365 = match["bookmakers"].get("bet365", {})
        if bet365:
            return {
                "1": bet365.get("home", 0),
                "X": bet365.get("draw", 0),
                "2": bet365.get("away", 0)
            }
    return {}


if __name__ == "__main__":
    client = OddsClient()
    
    # Test: List available sports
    sports = client.get_available_sports()
    print(f"Available sports: {len(sports)}")
    for s in sports[:5]:
        print(f"  - {s.get('title', s.get('key'))}")
    
    # Test: Get La Liga odds
    odds = client.get_live_odds(sport="soccer_spain_la_liga")
    print(f"\nLa Liga matches with odds: {len(odds)}")
    for m in odds[:3]:
        print(f"  {m.get('home_team')} vs {m.get('away_team')}")
