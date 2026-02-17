import requests
import json
import re
import os
import time
import pandas as pd
import urllib3
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'understat_laliga.csv')

def fetch_understat_data(league="La_liga", season="2024"):
    """
    Fetches real stats from Understat for the current season.
    Returns DataFrame with Team, xG, xGA, etc.
    """
    if os.path.exists(CACHE_FILE):
        if (time.time() - os.path.getmtime(CACHE_FILE)) < 86400:
            print("📦 Using Cached Understat Data")
            return pd.read_csv(CACHE_FILE)

    print(f"🌐 Fetching Real Data from Understat ({league})...")
    url = f"https://understat.com/league/{league}/{season}"
    
    try:
        # Understat usually allows requests with proper User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        
        if res.status_code != 200:
            print(f"❌ Understat Blocked: {res.status_code}")
            return None
        
        # Extract JSON from <script>
        # Looking for: var teamsData = JSON.parse('...');
        match = re.search(r"var\s+teamsData\s*=\s*JSON\.parse\('([^']+)'\)", res.text)
        
        if not match:
            print("❌ No teamsData found in scripts.")
            return None
            
        # Decode JSON string (it's often hex/unicode escaped)
        json_str = match.group(1).encode('utf-8').decode('unicode_escape')
        data = json.loads(json_str)
        
        # Parse data
        # data is a dict where keys are team IDs, values contain stats
        rows = []
        for team_id, stats in data.items():
            # Calculate Per 90 Stats using 'history' array or aggregate fields
            # The 'history' array has match-by-match stats.
            
            # Simple aggregation from the main object if available, 
            # but usually it's better to sum up history
            history = stats.get('history', [])
            matches_played = len(history)
            
            if matches_played < 1: continue

            team_name = stats.get('title', 'Unknown')
            
            total_xG = sum([h['xG'] for h in history])
            total_xGA = sum([h['xGA'] for h in history])
            total_uncorrected_pts = sum([h['pts'] for h in history]) # Actual points
            
            # Additional metrics might need deep parsing of 'ppda' etc if needed
            
            rows.append({
                'Team': team_name,
                'Matches': matches_played,
                'xG_Per90': round(total_xG / matches_played, 2),
                'xGA_Per90': round(total_xGA / matches_played, 2),
                'Pts_Per_Match': round(total_uncorrected_pts / matches_played, 2)
            })
            
        df = pd.DataFrame(rows)
        
        # Save cache
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        df.to_csv(CACHE_FILE, index=False)
        print(f"✅ Extracted stats for {len(df)} teams.")
        return df
        
    except Exception as e:
        print(f"❌ Understat Error: {e}")
        return None

if __name__ == "__main__":
    df = fetch_understat_data()
    if df is not None:
        print(df.head())
