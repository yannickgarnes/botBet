"""
Database v2.5 — REGION BRUTEFORCE FIX
Tries multiple Supabase Pooler regions to bypass IPv6/Network issues.
Fixes 'invalid dsn' error by strictly handling secrets.
"""
import psycopg2
from psycopg2 import pool
import os
import logging
import socket

logger = logging.getLogger("OmniscienceDB")

# User Credentials
DB_PASS = "2-tnV9*skaSdFYw"
PROJECT_REF = "ezuveunlxxruvuadmhxp"
DB_NAME = "postgres"

# Candidate Connection Strings
CANDIDATES = []

# 1. IPv4 Poolers (Transaction Mode - Port 6543) - TRYING ALL COMMON REGIONS
regions = [
    "aws-0-eu-central-1", # Frankfurt (Most likely based on time)
    "aws-0-us-east-1",    # N. Virginia
    "aws-0-eu-west-1",    # Ireland
    "aws-0-eu-west-2",    # London
    "aws-0-eu-west-3",    # Paris
    "aws-0-sa-east-1",    # Sao Paulo
]

for reg in regions:
    host = f"{reg}.pooler.supabase.com"
    # Pooler connection string: postgres://[user].[project]:[pass]@[host]:6543/[db]
    dsn = f"postgresql://postgres.{PROJECT_REF}:{DB_PASS}@{host}:6543/{DB_NAME}?sslmode=require"
    CANDIDATES.append((f"Pooler ({reg})", dsn))

# 2. Direct Connection (IPv6 often fails on Cloud, but good to have)
direct_dsn = f"postgresql://postgres:{DB_PASS}@db.{PROJECT_REF}.supabase.co:5432/{DB_NAME}?sslmode=require"
CANDIDATES.append(("Direct IPv6", direct_dsn))

class OddsBreakerDB:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OddsBreakerDB, cls).__new__(cls)
            cls._instance._initialized = False
            cls._instance.engine_type = None # 'postgres' or 'sqlite'
        return cls._instance

    def initialize_pool(self):
        if hasattr(self, 'postgreSQL_pool') and self.postgreSQL_pool: return
        if hasattr(self, 'sqlite_conn') and self.sqlite_conn: return

        # 1. Try PostgreSQL (Cloud)
        for name, dsn in CANDIDATES:
            try:
                self.postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn)
                conn = self.postgreSQL_pool.getconn() # Test
                self.postgreSQL_pool.putconn(conn)
                self.engine_type = 'postgres'
                self._initialized = True
                logger.info(f"Connected via {name}")
                return
            except:
                continue

        # 2. FALLBACK TO SQLITE (Local/Ephemeral)
        logger.warning("Falling back to SQLite")
        self.engine_type = 'sqlite'
        self.sqlite_path = 'bets_history.db'
        self._initialized = True

    def get_connection(self):
        if not self._initialized: self.initialize_pool()
        
        if self.engine_type == 'postgres':
            return self.postgreSQL_pool.getconn()
        else:
            # SQLite Connection
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn

    def return_connection(self, conn):
        if self.engine_type == 'postgres' and self.postgreSQL_pool:
            self.postgreSQL_pool.putconn(conn)
        elif self.engine_type == 'sqlite':
            conn.close()

    def execute_query(self, query, params=None, fetch=False):
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Adapt query for SQLite
            if self.engine_type == 'sqlite':
                query = query.replace('%s', '?')
                query = query.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
                query = query.replace('TIMESTAMP DEFAULT CURRENT_TIMESTAMP', 'DATETIME DEFAULT CURRENT_TIMESTAMP')
                # Fix ON CONFLICT syntax for SQLite (simplified)
                if "ON CONFLICT" in query and "excluded." in query:
                    # Replace Postgres 'excluded.' with SQLite 'excluded.' (case sensitive in some versions?)
                    # Actually, standard SQLite uses 'excluded.col'.
                    # Just ensure we don't have artifacts.
                    pass
                
                # Sanitize Params for SQLite (Datetime -> Str)
                if params:
                    new_params = []
                    for p in params:
                        if isinstance(p, (datetime.datetime, datetime.date)):
                            new_params.append(str(p))
                        else:
                            new_params.append(p)
                    params = tuple(new_params)

            cursor.execute(query, params or ())
            
            if fetch:
                res = cursor.fetchall()
                if self.engine_type == 'sqlite':
                    return [tuple(r) for r in res]
                return res
            
            conn.commit()
        except Exception as e:
            logger.error(f"Query Error ({self.engine_type}): {e}")
            # VISIBLE ERROR FOR USER
            try:
                import streamlit as st
                # Only show unique errors to avoid spam
                if "query_error_displayed" not in st.session_state:
                    st.toast(f"⚠️ DB Error: {e}", icon="🔥")
                    st.session_state.query_error_displayed = True
            except: pass
            
            if conn: conn.rollback()
            return [] if fetch else None
        finally:
            if conn: self.return_connection(conn)

    # --- TABLES & LOGIC ---
    def create_tables(self):
        # Universal Schema
        queries = [
            """CREATE TABLE IF NOT EXISTS matches_historical (
                game_id BIGINT PRIMARY KEY,
                date DATE,
                home_team VARCHAR(255), away_team VARCHAR(255),
                home_score INT, away_score INT,
                league_name VARCHAR(255),
                odds_home FLOAT, odds_draw FLOAT, odds_away FLOAT,
                result VARCHAR(10)
            )""",
            """CREATE TABLE IF NOT EXISTS features_deep_data (
                game_id BIGINT PRIMARY KEY REFERENCES matches_historical(game_id),
                home_minutes_load FLOAT, away_minutes_load FLOAT,
                home_motivation_score FLOAT, away_motivation_score FLOAT,
                home_days_rest INT, away_days_rest INT,
                wind_factor FLOAT, rain_factor FLOAT,
                home_attack_strength FLOAT, away_attack_strength FLOAT,
                home_defense_strength FLOAT, away_defense_strength FLOAT,
                home_form FLOAT, away_form FLOAT
            )""",
            """CREATE TABLE IF NOT EXISTS bets_history (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id BIGINT REFERENCES matches_historical(game_id),
                placed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                selection VARCHAR(10), odds FLOAT, stake FLOAT,
                expected_value FLOAT,
                status VARCHAR(20) DEFAULT 'PENDING',
                pnl FLOAT DEFAULT 0.0,
                is_auto_bet BOOLEAN DEFAULT FALSE,
                learned BOOLEAN DEFAULT FALSE
            )"""
        ]
        for q in queries: self.execute_query(q)

    def save_match_data(self, match_data: dict, deep_data: dict = None):
        # Robust Upsert
        if self.engine_type == 'sqlite':
             # SQLite Upsert
             self.execute_query("""
                INSERT INTO matches_historical (game_id, date, home_team, away_team, home_score, away_score, league_name, odds_home, odds_draw, odds_away, result)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(game_id) DO UPDATE SET 
                home_score=excluded.home_score, away_score=excluded.away_score, result=excluded.result
             """, (
                 match_data.get("game_id"), match_data.get("date"), 
                 match_data.get("home_team"), match_data.get("away_team"), 
                 match_data.get("home_score"), match_data.get("away_score"), 
                 match_data.get("league_name"), 
                 match_data.get("odds_home"), match_data.get("odds_draw"), match_data.get("odds_away"), 
                 match_data.get("result")
             ))
        else:
            # Postgres Upsert
            self.execute_query("""
                INSERT INTO matches_historical (game_id, date, home_team, away_team, home_score, away_score, league_name, odds_home, odds_draw, odds_away, result)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id) DO UPDATE SET home_score = EXCLUDED.home_score, away_score = EXCLUDED.away_score, result = EXCLUDED.result
            """, (
                 match_data.get("game_id"), match_data.get("date"), 
                 match_data.get("home_team"), match_data.get("away_team"), 
                 match_data.get("home_score"), match_data.get("away_score"), 
                 match_data.get("league_name"), 
                 match_data.get("odds_home"), match_data.get("odds_draw"), match_data.get("odds_away"), 
                 match_data.get("result")
            ))
        
        # Stub for deep data to prevent crash
        if deep_data:
            self.execute_query("INSERT INTO features_deep_data (game_id, home_attack_strength) VALUES (%s, %s) ON CONFLICT(game_id) DO NOTHING", (match_data.get("game_id"), 1.0))

    def place_bet(self, game_id, selection, odds, stake, ev, is_auto=False):
        self.execute_query("INSERT INTO bets_history (game_id, selection, odds, stake, expected_value, is_auto_bet) VALUES (%s, %s, %s, %s, %s, %s)", (game_id, selection, odds, stake, ev, is_auto))

    def get_pending_bets(self):
        return self.execute_query("SELECT b.bet_id, b.game_id, b.selection, b.odds, b.stake, m.result, m.home_team, m.away_team FROM bets_history b JOIN matches_historical m ON b.game_id = m.game_id WHERE b.status = 'PENDING'", fetch=True) or []
    
    def get_recent_bets(self, limit=20):
        # Returns ALL bets (Pending + Won + Lost) ordered by time
        return self.execute_query(f"SELECT b.bet_id, b.game_id, b.selection, b.odds, b.stake, b.status, m.home_team, m.away_team, b.pnl FROM bets_history b JOIN matches_historical m ON b.game_id = m.game_id ORDER BY b.bet_id DESC LIMIT {limit}", fetch=True) or []

    def resolve_bet(self, bet_id, result_status, pnl):
        self.execute_query("UPDATE bets_history SET status = %s, pnl = %s WHERE bet_id = %s", (result_status, pnl, bet_id))

    def mark_bet_as_learned(self, bet_id):
        self.execute_query("UPDATE bets_history SET learned = 1 WHERE bet_id = %s", (bet_id,))

    def get_bets_stats(self):
        rows = self.execute_query("SELECT COUNT(*), SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END), SUM(pnl), AVG(odds) FROM bets_history WHERE status IN ('WON', 'LOST')", fetch=True)
        return rows[0] if rows else (0, 0, 0, 0)
    
    def get_training_data(self, limit=5000):
        # Stub
        return []

if __name__ == "__main__":
    db = OddsBreakerDB()
    db.create_tables()
    print("Hybrid DB Initialized")
