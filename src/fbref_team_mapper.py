import requests
import re
import json
import logging
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL = "https://fbref.com/en/comps/12/La-Liga-Stats"
OUTPUT_FILE = os.path.join("data", "fbref_teams.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def map_teams():
    try:
        logger.info(f"Fetching {URL}...")
        resp = requests.get(URL, headers=HEADERS, verify=False)
        if resp.status_code != 200:
            logger.error(f"Failed {resp.status_code}")
            return
            
        html = resp.text
        # Regex to find squad links: <a href="/en/squads/ID/Name">Name</a>
        # Usually inside <th data-stat="squad"> or <td data-stat="squad">
        
        # Pattern: href="(/en/squads/[a-f0-9]+/[^"]+)">([^<]+)</a>
        matches = re.findall(r'href="(/en/squads/[a-f0-9]+/[^"]+)">([^<]+)</a>', html)
        
        team_map = {}
        for link, name in matches:
            # Clean name
            name = name.strip()
            # FBREF sometimes has duplicates or specific table links, but the squad link is standard
            if "Match-Logs" in link: continue # Skip logs
            
            full_link = f"https://fbref.com{link}"
            # logger.info(f"Found: {name} -> {full_link}")
            team_map[name] = full_link
            
        logger.info(f"Mapped {len(team_map)} teams.")
        
        os.makedirs("data", exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(team_map, f, indent=2)
        logger.info(f"Saved to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Exc: {e}")

if __name__ == "__main__":
    map_teams()
