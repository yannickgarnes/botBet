import requests
import re
import logging
from urllib.parse import quote
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def search_fbref_team(team_name: str):
    """Searches FBREF for a team and returns the Squad URL."""
    query = quote(team_name)
    url = f"https://fbref.com/en/search/search.fcgi?search={query}"
    
    try:
        logger.info(f"Searching FBREF for {team_name}...")
        resp = requests.get(url, headers=HEADERS, verify=False, allow_redirects=True)
        
        # If redirect to squad page directly
        if "/squads/" in resp.url:
            logger.info(f"Direct redirect to: {resp.url}")
            return resp.url
            
        # Parse search results
        # Look for first link containing /squads/
        match = re.search(r'<a href="(/en/squads/[^"]+)"', resp.text)
        if match:
            full_url = f"https://fbref.com{match.group(1)}"
            logger.info(f"Found squad link: {full_url}")
            return full_url
            
        logger.warning("No squad link found in search results.")
        return None
        
    except Exception as e:
        logger.error(f"Error searching {team_name}: {e}")
        return None

if __name__ == "__main__":
    search_fbref_team("Real Madrid")
    search_fbref_team("Girona")
