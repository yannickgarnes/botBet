from datetime import datetime, timedelta
import logging

try:
    from .scraper_365 import Scraper365
except ImportError:
    from src.scraper_365 import Scraper365

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_weekly_fixtures():
    """
    Returns REAL upcoming La Liga fixtures for the next 3 days using 365Scores API.
    """
    scraper = Scraper365()
    fixtures = []
    
    # Get today and next 2 days
    today = datetime.now()
    dates = [today + timedelta(days=i) for i in range(3)]
    
    # logger.info(f"Fetching fixtures for {dates[0].strftime('%d/%m/%Y')} - {dates[-1].strftime('%d/%m/%Y')}...")
    
    for d in dates:
        date_str = d.strftime("%d/%m/%Y")
        try:
            games = scraper.get_games(date_str)
            if not games: continue

            for g in games:
                # Filter for La Liga (ID 11), Premier (17), Serie A (23), Bundesliga (25), Ligue 1 (7), Champions (572)
                # Also include Copa del Rey (20) or other relevant cups if needed
                comp_id = g.get('competitionId')
                if comp_id in [11, 17, 23, 25, 7, 572, 20]: 
                    
                    # Extract Data
                    home_name = g['homeCompetitor']['name']
                    away_name = g['awayCompetitor']['name']
                    
                    # Formatting Time
                    start_time = g.get('startTime', today.isoformat())
                    try:
                        # 365 often gives startTime as ISO string like '2025-02-16T20:00:00+00:00'
                        # We need to be careful with timezones.
                        # For simple display, just slice the string or parse.
                        t_str = start_time.split('T')[1][:5]
                        dt_obj = datetime.strptime(start_time[:10], "%Y-%m-%d")
                        display_date = dt_obj.strftime("%a %d %b")
                    except:
                        t_str = "TBD"
                        display_date = date_str
                    
                    # Default Mock Odds
                    h_odds = 2.0
                    d_odds = 3.2
                    a_odds = 2.5
                    
                    # Try to extract real odds if available in 'game.members'? No, in 'game.odds'?
                    # The get_games response has 'odds' sometimes if showOdds=true
                    if 'odds' in g:
                        # Parse odds structure (complex) -> skip for now to keep it fast
                        pass

                    fixtures.append({
                        "id": g['id'], # CRITICAL: This ID drives the player stats scraper
                        "home": home_name,
                        "away": away_name,
                        "date": display_date,
                        "time": t_str,
                        "competition": g.get('competitionDisplayName', 'Unknown'),
                        "odds_h": h_odds, 
                        "odds_d": d_odds,
                        "odds_a": a_odds
                    })
        except Exception as e:
            logger.error(f"Error fetching fixtures for {date_str}: {e}")
            
    # Sort by time?
    # fixtures.sort(key=lambda x: x['time']) # Rough sort
    
    logger.info(f"Loaded {len(fixtures)} live fixtures.")
    return fixtures
