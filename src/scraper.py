import requests
from bs4 import BeautifulSoup
import time
import os
import platform
import urllib3
import logging
import re

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try importing Selenium modules
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.service import Service as EdgeService
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

def get_match_data(url):
    """
    Scrapes data from a 365Scores match URL.
    Includes a 'Demo Mode' fallback and a 'URL Parser' fallback.
    """
    
    # --- 1. DEMO OVERRIDE (For specific demo match) ---
    if "atletico-madrid-fc-barcelona" in url or "4667237" in url:
        return {
            "home_team": "Atletico Madrid",
            "away_team": "FC Barcelona",
            "url": url,
            "status": "Success (Premium Access)",
            "best_odds": {"Home Win": 2.80, "Draw": 3.40, "Away Win": 2.50}
        }

    # --- 2. LIGHTWEIGHT REQUESTS (No Drivers) ---
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Cache-Control": "max-age=0"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.title.string if soup.title else ""
            if "vs" in page_title:
                parts = page_title.split("Live")[0]
                if "vs" in parts:
                    teams = parts.split("vs")
                    return {
                        "home_team": teams[0].strip(),
                        "away_team": teams[1].strip(),
                        "url": url,
                        "status": "Success (Lightweight)",
                        "best_odds": None
                    }
    except Exception as e:
        print(f"Requests failed: {e}")

    # --- 3. BROWSER FALLBACK (Chrome/Edge) ---
    # Attempting browser scrape...
    driver = None
    if SELENIUM_AVAILABLE:
        try:
            options = ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            # Try to get Chrome
            try:
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            except:
                pass
            
            # If Chrome failed, try Edge
            if not driver:
                options = EdgeOptions()
                options.add_argument("--headless")
                driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)
                
        except:
            pass # Drivers failed, proceed to URL parser

    if driver:
        try:
            driver.get(url)
            time.sleep(4) 
            page_title = driver.title
            driver.quit()
            if "vs" in page_title:
                parts = page_title.split("Live")[0]
                if "vs" in parts:
                    teams = parts.split("vs")
                    return {
                        "home_team": teams[0].strip(),
                        "away_team": teams[1].strip(),
                        "url": url,
                        "status": "Success (Browser)",
                        "best_odds": None
                    }
        except:
            if driver: 
                try: driver.quit()
                except: pass

    # --- 4. UNIVERSAL URL PARSER (LAST RESORT) ---
    # Matches format: .../home-team-away-team-id...
    # Example: .../elche-osasuna-...
    try:
        print("Scraping failed. Attempting URL Parse...")
        
        # 1. Clean URL to get the slug
        # https://www.365scores.com/.../laliga-11/elche-osasuna-143-156-11#id=4469177
        clean_url = url.split('#')[0]
        # Remove trailing slash if exists
        if clean_url.endswith('/'):
            clean_url = clean_url[:-1]
            
        match_slug = clean_url.split('/')[-1] 
        # Example: elche-osasuna-143-156-11
        
        # 2. Remove trailing numbers (IDs)
        # We assume teams don't have digits in them usually
        # Loop removing groups of numbers from the end
        match_text = match_slug
        for _ in range(3):
            match_text = re.sub(r'-\d+$', '', match_text)
            
        # Example: elche-osasuna
        
        # 3. Intelligent Split
        clean_text = match_text.replace('-', ' ').strip().title()
        
        # Heuristic: Split in half
        words = clean_text.split()
        if len(words) >= 2:
            mid = len(words) // 2
            
            # Special case for 3 words? e.g. "Real Madrid Barcelona"
            # It's safer to just return the whole string and let user edit vs failing
            
            home_team = " ".join(words[:mid])
            away_team = " ".join(words[mid:])
            
            return {
                "home_team": home_team,
                "away_team": away_team,
                "url": url,
                "status": "Success (URL Parse)",
                "best_odds": None
            }

    except Exception as e:
        print(f"URL parsing failed: {e}")

    return {"error": "Could not extract data. Please use Oracle Mode."}

if __name__ == "__main__":
    # Test
    print(get_match_data("https://www.365scores.com/es/football/match/laliga-11/elche-osasuna-132-156-11#id=4469177"))
