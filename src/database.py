"""
Database v2.4 — IPV4 FIX (Supabase Pooler)
Autodetects IPv6 issues and switches to IPv4 Pooler automatically.
"""
import psycopg2
from psycopg2 import pool
import os
import logging

logger = logging.getLogger("OmniscienceDB")

# User provided Direct URL (IPv6 only - Fails on Streamlit)
DIRECT_URL = "postgresql://postgres:2-tnV9*skaSdFYw@db.ezuveunlxxruvuadmhxp.supabase.co:5432/postgres"

# Derived IPv4 Pooler URL (Guessing Frankfurt Region based on history)
# Format: postgres://[user].[project]:[pass]@[pooler_host]:6543/postgres
# Project: ezuveunlxxruvuadmhxp
# Region: aws-0-eu-central-1 (Frankfurt)
IPV4_POOLER_URL = "postgresql://postgres.ezuveunlxxruvuadmhxp:2-tnV9*skaSdFYw@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

class OddsBreakerDB:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OddsBreakerDB, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize_pool(self):
        if hasattr(self, 'postgreSQL_pool') and self.postgreSQL_pool:
            return

        candidates = []
        
        # Priority 1: Calculated IPv4 Pooler (Fixes "Cannot assign requested address")
        candidates.append(("IPv4 Pooler (Frankfurt)", IPV4_POOLER_URL))
        
        # Priority 2: Direct URL (Original)
        candidates.append(("Direct IPv6", DIRECT_URL))

        # Priority 3: Secrets/Env
        try:
            import streamlit as st
            if "postgres" in st.secrets:
                s = st.secrets["postgres"]
                if isinstance(s, dict): candidates.append(("Secrets", s.get("url")))
                else: candidates.append(("Secrets", str(s)))
        except: pass

        self._initialized = False
        last_error = None
        
        for name, dsn in candidates:
            if not dsn: continue
            try:
                # Cleanup
                clean_dsn = dsn.strip().strip("'").strip('"')
                
                logger.info(f"Connecting via {name}...")
                self.postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
                    1, 20, clean_dsn, sslmode='require'
                )
                logger.info(f"SUCCESS: Connected via {name}")
                self._initialized = True
                return
            except Exception as e:
                last_error = e
                logger.warning(f"Failed via {name}: {e}")
                continue

        # Critical Failure Reporting
        import streamlit as st
        st.error(f"❌ Error Crítico de Conexión (IPv4/IPv6): {last_error}")
        st.info("Diagnóstico: Streamlit Cloud usa IPv4. Supabase Direct usa IPv6. La corrección automática al Pooler (Puerto 6543) falló.")
        st.warning("Solución Manual: Ve a Supabase -> Database -> Connect -> Connection String -> Cambia 'Mode' a 'Transaction' y copia esa URL.")
        self._initialized = False

    def get_connection(self):
        if not self._initialized or not hasattr(self, 'postgreSQL_pool') or self.postgreSQL_pool is None:
            self.initialize_pool()
        if not hasattr(self, 'postgreSQL_pool') or self.postgreSQL_pool is None:
             raise Exception("Sin conexión a BD.")
        return self.postgreSQL_pool.getconn()

    def return_connection(self, conn):
        if self.postgreSQL_pool: self.postgreSQL_pool.putconn(conn)

    def execute_query(self, query, params=None, fetch=False):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch: return cursor.fetchall()
                conn.commit()
        except: return [] if fetch else None
        finally:
            if conn: self.return_connection(conn)

    # --- METHODS ---
    def create_tables(self):
        queries = [
            "CREATE TABLE IF NOT EXISTS matches_historical (game_id BIGINT PRIMARY KEY, date DATE, home_team VARCHAR(255), away_team VARCHAR(255), home_score INT, away_score INT, league_name VARCHAR(255), odds_home FLOAT, odds_draw FLOAT, odds_away FLOAT, result VARCHAR(10));",
            "CREATE TABLE IF NOT EXISTS features_deep_data (game_id BIGINT REFERENCES matches_historical(game_id), home_minutes_load FLOAT, away_minutes_load FLOAT, home_motivation_score FLOAT, away_motivation_score FLOAT, home_days_rest INT, away_days_rest INT, wind_factor FLOAT, rain_factor FLOAT, home_attack_strength FLOAT, away_attack_strength FLOAT, home_defense_strength FLOAT, away_defense_strength FLOAT, home_form FLOAT, away_form FLOAT, PRIMARY KEY (game_id));",
            "CREATE TABLE IF NOT EXISTS odds_snapshots (snapshot_id SERIAL PRIMARY KEY, game_id BIGINT, captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, bookmaker VARCHAR(100), odds_home FLOAT, odds_draw FLOAT, odds_away FLOAT, implied_prob_home FLOAT, implied_prob_draw FLOAT, implied_prob_away FLOAT);",
            "CREATE TABLE IF NOT EXISTS bets_history (bet_id SERIAL PRIMARY KEY, game_id BIGINT REFERENCES matches_historical(game_id), placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, selection VARCHAR(10), odds FLOAT, stake FLOAT, expected_value FLOAT, status VARCHAR(20) DEFAULT 'PENDING', pnl FLOAT DEFAULT 0.0, is_auto_bet BOOLEAN DEFAULT FALSE, learned BOOLEAN DEFAULT FALSE);",
        ]
        for q in queries: self.execute_query(q)

    def save_match_data(self, match_data: dict, deep_data: dict = None):
        try:
            self.execute_query("INSERT INTO matches_historical (game_id, date, home_team, away_team, home_score, away_score, league_name, odds_home, odds_draw, odds_away, result) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (game_id) DO UPDATE SET home_score = EXCLUDED.home_score, away_score = EXCLUDED.away_score, result = EXCLUDED.result", (match_data.get("game_id"), match_data.get("date"), match_data.get("home_team"), match_data.get("away_team"), match_data.get("home_score"), match_data.get("away_score"), match_data.get("league_name"), match_data.get("odds_home"), match_data.get("odds_draw"), match_data.get("odds_away"), match_data.get("result")))
            if deep_data: self.execute_query("INSERT INTO features_deep_data (game_id, home_attack_strength) VALUES (%s, %s) ON CONFLICT (game_id) DO NOTHING", (match_data.get("game_id"), 1.0))
        except: pass

    def place_bet(self, game_id, selection, odds, stake, ev, is_auto=False):
        self.execute_query("INSERT INTO bets_history (game_id, selection, odds, stake, expected_value, is_auto_bet) VALUES (%s, %s, %s, %s, %s, %s)", (game_id, selection, odds, stake, ev, is_auto))

    def get_pending_bets(self):
        return self.execute_query("SELECT b.bet_id, b.game_id, b.selection, b.odds, b.stake, m.result, m.home_team, m.away_team FROM bets_history b JOIN matches_historical m ON b.game_id = m.game_id WHERE b.status = 'PENDING'", fetch=True) or []

    def resolve_bet(self, bet_id, result_status, pnl):
        self.execute_query("UPDATE bets_history SET status = %s, pnl = %s WHERE bet_id = %s", (result_status, pnl, bet_id))

    def mark_bet_as_learned(self, bet_id):
        self.execute_query("UPDATE bets_history SET learned = TRUE WHERE bet_id = %s", (bet_id,))

    def get_bets_stats(self):
        rows = self.execute_query("SELECT COUNT(*), SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END), SUM(pnl), AVG(odds) FROM bets_history WHERE status IN ('WON', 'LOST')", fetch=True)
        return rows[0] if rows else (0, 0, 0, 0)
    
    def get_training_data(self, limit=5000):
        return []

if __name__ == "__main__":
    db = OddsBreakerDB()
    db.create_tables()
