import logging
from scraper_365 import Scraper365
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Scraper
scraper = Scraper365()

def get_probable_lineup(team_name, game_id=None):
    """
    Returns a dict of players for the team.
    Uses REAL recent match history with participation filtering.
    """
    if game_id:
        logger.info(f"Generating isolated squad for {team_name}")
        details = scraper.get_game_details(game_id)
        if details:
            try:
                # 1. Identify Team ID
                home_comp = details['game']['homeCompetitor']
                away_comp = details['game']['awayCompetitor']
                
                # Loose matching
                if team_name.lower() in home_comp['name'].lower():
                    team_id = home_comp['id']
                else:
                    team_id = away_comp['id']
                
                # 2. Get Recent Match IDs for this specific team
                team_recent_matches = scraper.get_team_results(team_id)
                if not team_recent_matches:
                    logger.warning(f"No results for team {team_id}")
                    return {}

                # 3. Get Squad from the latest games
                raw_lineup = scraper.get_squad_from_last_game(team_id)
                
                live_players = {}
                for p in raw_lineup:
                    try:
                        p_id = p['id']
                        p_name = scraper.get_player_name(p_id, details)
                        
                        # Fallback for name
                        if p_name == "Unknown" and team_recent_matches:
                            last_details = scraper.get_game_details(team_recent_matches[0])
                            p_name = scraper.get_player_name(p_id, last_details)

                        # 4. Calculate Stats ISOLATED to this team
                        # (Pass team_id to avoid picking up opponent stats)
                        avg_data = scraper.get_player_last_5_average(p_id, team_recent_matches, team_id=team_id)
                        
                        # 5. STRICT FILTER: Must have played for THIS TEAM in last 5 matches
                        # This definitively removes ghosts like Sane (Bayern) from Gala's list.
                        if avg_data['games_played'] == 0:
                            # logger.info(f"Filtered {p_name} - no minutes for {team_name}")
                            continue

                        # 6. Build History
                        history = []
                        for mid in team_recent_matches[:5]:
                            m_details = scraper.get_game_details(mid)
                            p_m_stats = scraper.get_player_stats_from_lineup(p_id, m_details, team_id=team_id)
                            
                            opp = "Match"
                            if m_details:
                                m_g = m_details['game']
                                opp = m_g['awayCompetitor']['name'] if m_g['homeCompetitor']['id'] == team_id else m_g['homeCompetitor']['name']
                            
                            history.append({
                                "opponent": opp,
                                "shots": p_m_stats.get('shots', 0),
                                "shots_ot": p_m_stats.get('shots_on_target', 0),
                                "fouls_won": p_m_stats.get('fouls_won', 0),
                                "goals": p_m_stats.get('goals', 0)
                            })

                        live_players[p_name] = {
                            "position": str(p.get('role', 'ply')), 
                            "last_5_matches": history,
                            "avg_shots": avg_data['shots'],
                            "avg_sot": avg_data['shots_on_target'],
                            "avg_fouls": avg_data['fouls_won']
                        }
                    except Exception as e:
                        logger.error(f"Error processing {p.get('id')}: {e}")
                
                if live_players:
                    logger.info(f"Verified {len(live_players)} players for {team_name}")
                    return live_players
            except Exception as e:
                logger.error(f"Isolated fetch failed: {e}")

    return {}

def analyze_last_5(player_name, team, game_id=None):
    players = get_probable_lineup(team, game_id)
    if player_name in players:
        return players[player_name]['last_5_matches']
    return []
