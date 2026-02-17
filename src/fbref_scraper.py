import pandas as pd
import requests
import time
import os
import sys
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cache path
CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'fbref_stats.csv')

def fetch_season_stats(comp_url="https://fbref.com/en/comps/12/La-Liga-Stats"):
    """
    Fetches 2024/2025 La Liga stats from Fbref.
    Argument: comp_url (default La Liga)
    """
    
    # Check cache (24h)
    if os.path.exists(CACHE_FILE):
        if (time.time() - os.path.getmtime(CACHE_FILE)) < 86400:
            print("📦 Using Cached Fbref Stats")
            return pd.read_csv(CACHE_FILE)

    print("🌐 Fetching Real Data from Fbref...")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # SSL Verify False
        res = requests.get(comp_url, headers=headers, verify=False)
        
        if res.status_code != 200:
            print(f"❌ Fbref Blocked: {res.status_code}")
            return None
            
        dfs = pd.read_html(res.text)
        
        stats_df = None
        for df in dfs:
            # Flatten MultiIndex if present
            if isinstance(df.columns, pd.MultiIndex):
                new_cols = []
                for col in df.columns.values:
                    clean_col = "_".join([str(c) for c in col if "Unnamed" not in str(c)]).strip()
                    if not clean_col: clean_col = str(col[-1])
                    new_cols.append(clean_col)
                df.columns = new_cols
            
            # Look for indicators of the main stats table
            cols_str = " ".join(list(df.columns))
            if "Squad" in cols_str and "Gls" in cols_str and "Sh" in cols_str:
                stats_df = df
                break
        
        if stats_df is None:
            print("❌ No stats table found.")
            return None

        # Extract Columns Robustly
        final_data = []
        
        def find_col(keywords):
            for c in stats_df.columns:
                if all(k in c for k in keywords):
                    return c
            return None

        c_squad = find_col(['Squad'])
        c_sh90  = find_col(['Sh', '90'])
        c_sot90 = find_col(['SoT', '90'])
        c_gls90 = find_col(['Gls', '90'])
        c_crd   = find_col(['CrdY']) 
        
        print(f"   -> Columns: {c_squad} | {c_sh90} | {c_sot90}")

        if not c_squad: return None
        
        for index, row in stats_df.iterrows():
            team = str(row[c_squad])
            if "vs " in team or team == "nan": continue
            
            try:
                sh = float(row[c_sh90]) if c_sh90 else 10.5
                sot = float(row[c_sot90]) if c_sot90 else 3.5
                gls = float(row[c_gls90]) if c_gls90 else 1.2
                crd = float(row[c_crd]) if c_crd else 2.2
                
                final_data.append({
                    'Team': team,
                    'ShotsInGame': sh, 
                    'SoTInGame': sot,
                    'GoalsInGame': gls,
                    'CardsInGame': crd
                })
            except:
                continue
                
        final_df = pd.DataFrame(final_data)
        
        # Save cache
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        final_df.to_csv(CACHE_FILE, index=False)
        print(f"✅ Extracted stats for {len(final_df)} teams.")
        return final_df
            
    except Exception as e:
        print(f"❌ Fbref Error: {e}")
        return None

if __name__ == "__main__":
    df = fetch_season_stats()
    if df is not None:
        print(df.head())
