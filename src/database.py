"""
Database v2.0 — Project Omniscience
- IMPLEMENTED save_match_data (was a stub)
- Indexes on date, league, teams for ms-level queries
- New table: odds_snapshots for Smart Money tracking
- get_training_data() for LSTM batch training
"""
import psycopg2
from psycopg2 import pool
import os
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

logger = logging.getLogger("OmniscienceDB")


class OddsBreakerDB:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OddsBreakerDB, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize_pool(self):
        try:
            # Try to get connection string from multiple sources
            dsn = None
            
            # 1. Streamlit Secrets (Recommended for Cloud)
            try:
                import streamlit as st
                if "postgres" in st.secrets:
                    # Check for 'url' key or simple string
                    if isinstance(st.secrets["postgres"], dict) and "url" in st.secrets["postgres"]:
                        dsn = st.secrets["postgres"]["url"]
                    elif isinstance(st.secrets["postgres"], str):
                        dsn = st.secrets["postgres"]
            except Exception:
                pass # Streamlit not installed or no secrets

            # 2. Environment Variable (Standard)
            if not dsn:
                dsn = os.getenv("DATABASE_URL")
            
            if dsn:
                self.postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn, sslmode='require')
                logger.info("Connected to DB via URL/DSN.")
            else:
                # 3. Individual Env Vars (Fallback / Local)
                self.postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(
                    1, 20,
                    user=os.getenv("DB_USER", "postgres"),
                    password=os.getenv("DB_PASS", "admin"),
                    host=os.getenv("DB_HOST", "localhost"),
                    port=os.getenv("DB_PORT", "5432"),
                    database=os.getenv("DB_NAME", "odds_breaker")
                )
                logger.info("Connected to DB via Env Vars.")

            if self.postgreSQL_pool:
                self._initialized = True
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Error while connecting to PostgreSQL: {error}")
            self._initialized = False

    def get_connection(self):
        if not self._initialized or not hasattr(self, 'postgreSQL_pool') or self.postgreSQL_pool is None:
            self.initialize_pool()
        if not hasattr(self, 'postgreSQL_pool') or self.postgreSQL_pool is None:
             raise Exception("Database connection failed. Please check your credentials.")
        return self.postgreSQL_pool.getconn()

    def return_connection(self, conn):
        self.postgreSQL_pool.putconn(conn)

    def execute_query(self, query, params=None, fetch=False):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                conn.commit()
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    def create_tables(self):
        """
        Initializes the database schema for ODDS-ABSOLUTE / Omniscience.
        Includes indexes for ms-level query performance.
        """
        queries = [
            # ---- MATCHES HISTORICAL ----
            """
            CREATE TABLE IF NOT EXISTS matches_historical (
                game_id BIGINT PRIMARY KEY,
                date DATE,
                home_team VARCHAR(255),
                away_team VARCHAR(255),
                home_score INT,
                away_score INT,
                league_name VARCHAR(255),
                odds_home FLOAT,
                odds_draw FLOAT,
                odds_away FLOAT,
                result VARCHAR(10)
            );
            """,
            
            # ---- DEEP DATA FEATURES ----
            """
            CREATE TABLE IF NOT EXISTS features_deep_data (
                game_id BIGINT REFERENCES matches_historical(game_id),
                home_minutes_load FLOAT,
                away_minutes_load FLOAT,
                home_motivation_score FLOAT,
                away_motivation_score FLOAT,
                home_days_rest INT,
                away_days_rest INT,
                wind_factor FLOAT,
                rain_factor FLOAT,
                home_attack_strength FLOAT,
                away_attack_strength FLOAT,
                home_defense_strength FLOAT,
                away_defense_strength FLOAT,
                home_form FLOAT,
                away_form FLOAT,
                referee_strictness FLOAT,
                weather_condition VARCHAR(50),
                PRIMARY KEY (game_id)
            );
            """,
            
            # ---- ODDS SNAPSHOTS (Smart Money Tracking) ----
            """
            CREATE TABLE IF NOT EXISTS odds_snapshots (
                snapshot_id SERIAL PRIMARY KEY,
                game_id BIGINT,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bookmaker VARCHAR(100),
                odds_home FLOAT,
                odds_draw FLOAT,
                odds_away FLOAT,
                implied_prob_home FLOAT,
                implied_prob_draw FLOAT,
                implied_prob_away FLOAT
            );
            """,
            
            # ---- MODEL PERFORMANCE LOG ----
            """
            CREATE TABLE IF NOT EXISTS model_performance_log (
                log_id SERIAL PRIMARY KEY,
                prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_version VARCHAR(50),
                accuracy_window_7d FLOAT,
                avg_log_loss FLOAT,
                total_bets_simulated INT,
                roi_simulated FLOAT,
                sharpe_ratio FLOAT
            );
            """,
            
            # ---- INDEXES FOR MS-LEVEL QUERIES ----
            "CREATE INDEX IF NOT EXISTS idx_matches_date ON matches_historical(date);",
            "CREATE INDEX IF NOT EXISTS idx_matches_league ON matches_historical(league_name);",
            "CREATE INDEX IF NOT EXISTS idx_matches_home ON matches_historical(home_team);",
            "CREATE INDEX IF NOT EXISTS idx_matches_away ON matches_historical(away_team);",
            "CREATE INDEX IF NOT EXISTS idx_odds_snap_game ON odds_snapshots(game_id);",
            "CREATE INDEX IF NOT EXISTS idx_odds_snap_time ON odds_snapshots(captured_at);",
            "CREATE INDEX IF NOT EXISTS idx_odds_snap_bm ON odds_snapshots(bookmaker);",

            # ---- BETTING HISTORY (Auto-Bet & Learning) ----
            """
            CREATE TABLE IF NOT EXISTS bets_history (
                bet_id SERIAL PRIMARY KEY,
                game_id BIGINT REFERENCES matches_historical(game_id),
                placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                selection VARCHAR(10), -- '1', 'X', '2'
                odds FLOAT,
                stake FLOAT,
                expected_value FLOAT,
                status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, WON, LOST, VOID
                pnl FLOAT DEFAULT 0.0,
                is_auto_bet BOOLEAN DEFAULT FALSE,
                learned BOOLEAN DEFAULT FALSE -- If True, RL model has trained on this
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_bets_status ON bets_history(status);",
        ]
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                for q in queries:
                    cursor.execute(q)
                conn.commit()
                logger.info("Database schema initialized with indexes.")
        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    def save_match_data(self, match_data: dict, deep_data: dict = None):
        """
        Saves match result and deep features to DB.
        
        match_data: {
            "game_id", "date", "home_team", "away_team",
            "home_score", "away_score", "league_name",
            "odds_home", "odds_draw", "odds_away", "result"
        }
        deep_data: {
            "home_minutes_load", "away_minutes_load",
            "home_motivation_score", "away_motivation_score",
            "home_days_rest", "away_days_rest",
            "wind_factor", "rain_factor", ...
        }
        """
        # Save match
        self.execute_query("""
            INSERT INTO matches_historical 
                (game_id, date, home_team, away_team, home_score, away_score,
                 league_name, odds_home, odds_draw, odds_away, result)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id) DO UPDATE SET
                home_score = EXCLUDED.home_score,
                away_score = EXCLUDED.away_score,
                result = EXCLUDED.result
        """, (
            match_data.get("game_id"),
            match_data.get("date"),
            match_data.get("home_team"),
            match_data.get("away_team"),
            match_data.get("home_score"),
            match_data.get("away_score"),
            match_data.get("league_name"),
            match_data.get("odds_home"),
            match_data.get("odds_draw"),
            match_data.get("odds_away"),
            match_data.get("result")
        ))
        
        # Save deep features
        if deep_data:
            self.execute_query("""
                INSERT INTO features_deep_data
                    (game_id, home_minutes_load, away_minutes_load,
                     home_motivation_score, away_motivation_score,
                     home_days_rest, away_days_rest,
                     wind_factor, rain_factor,
                     home_attack_strength, away_attack_strength,
                     home_defense_strength, away_defense_strength,
                     home_form, away_form)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id) DO UPDATE SET
                    home_minutes_load = EXCLUDED.home_minutes_load,
                    away_minutes_load = EXCLUDED.away_minutes_load
            """, (
                match_data.get("game_id"),
                deep_data.get("home_minutes_load", 0),
                deep_data.get("away_minutes_load", 0),
                deep_data.get("home_motivation_score", 0.5),
                deep_data.get("away_motivation_score", 0.5),
                deep_data.get("home_days_rest", 4),
                deep_data.get("away_days_rest", 4),
                deep_data.get("wind_factor", 0.1),
                deep_data.get("rain_factor", 0.1),
                deep_data.get("home_attack_strength", 1.0),
                deep_data.get("away_attack_strength", 1.0),
                deep_data.get("home_defense_strength", 1.0),
                deep_data.get("away_defense_strength", 1.0),
                deep_data.get("home_form", 0.33),
                deep_data.get("away_form", 0.33),
            ))

    def save_odds_snapshot(self, game_id: int, bookmaker: str, 
                           odds_h: float, odds_d: float, odds_a: float):
        """
        Saves a point-in-time odds snapshot for smart money tracking.
        Call this periodically (every 30-60 min) for each match.
        """
        # Calculate implied probabilities
        total = (1/odds_h) + (1/odds_d) + (1/odds_a) if odds_h and odds_d and odds_a else 1
        impl_h = round((1/odds_h) / total, 4) if odds_h else 0
        impl_d = round((1/odds_d) / total, 4) if odds_d else 0
        impl_a = round((1/odds_a) / total, 4) if odds_a else 0
        
        self.execute_query("""
            INSERT INTO odds_snapshots 
                (game_id, bookmaker, odds_home, odds_draw, odds_away,
                 implied_prob_home, implied_prob_draw, implied_prob_away)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (game_id, bookmaker, odds_h, odds_d, odds_a, impl_h, impl_d, impl_a))

    def get_training_data(self, limit=5000) -> list:
        """
        Extracts feature vectors for LSTM training from DB.
        Returns list of (features_14_dim, target_idx) tuples.
        """
        rows = self.execute_query("""
            SELECT 
                f.home_attack_strength, f.away_attack_strength,
                f.home_defense_strength, f.away_defense_strength,
                f.home_form, f.away_form,
                f.home_minutes_load / 900.0, f.away_minutes_load / 900.0,
                f.home_motivation_score, f.away_motivation_score,
                LEAST(f.home_days_rest / 7.0, 1.0), LEAST(f.away_days_rest / 7.0, 1.0),
                f.wind_factor, f.rain_factor,
                m.result
            FROM features_deep_data f
            JOIN matches_historical m ON f.game_id = m.game_id
            WHERE m.result IS NOT NULL
            ORDER BY m.date DESC
            LIMIT %s
        """, (limit,), fetch=True)
        
        if not rows:
            return []
        
        result = []
        result_map = {'1': 0, 'X': 1, '2': 2}
        for row in rows:
            features = list(row[:14])
            target = result_map.get(row[14], 1)
            result.append((features, target))
        
        return result

    def get_odds_movement(self, game_id: int) -> list:
        """Returns chronological odds snapshots for a match."""
        return self.execute_query("""
            SELECT captured_at, bookmaker, odds_home, odds_draw, odds_away
            FROM odds_snapshots
            WHERE game_id = %s
            ORDER BY captured_at ASC
        """, (game_id,), fetch=True) or []

    def place_bet(self, game_id, selection, odds, stake, ev, is_auto=False):
        """Records a new bet."""
        self.execute_query("""
            INSERT INTO bets_history (game_id, selection, odds, stake, expected_value, is_auto_bet)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (game_id, selection, odds, stake, ev, is_auto))

    def get_pending_bets(self):
        """Get all unresolved bets."""
        return self.execute_query("""
            SELECT b.bet_id, b.game_id, b.selection, b.odds, b.stake, m.result, m.home_team, m.away_team
            FROM bets_history b
            JOIN matches_historical m ON b.game_id = m.game_id
            WHERE b.status = 'PENDING'
        """, fetch=True)

    def resolve_bet(self, bet_id, result_status, pnl):
        """Updates bet status and PnL."""
        self.execute_query("""
            UPDATE bets_history 
            SET status = %s, pnl = %s
            WHERE bet_id = %s
        """, (result_status, pnl, bet_id))

    def mark_bet_as_learned(self, bet_id):
        """Marks that the RL model has trained on this outcome."""
        self.execute_query("UPDATE bets_history SET learned = TRUE WHERE bet_id = %s", (bet_id,))

    def get_bets_stats(self):
        """Returns aggregate stats for dashboard."""
        rows = self.execute_query("""
            SELECT 
                COUNT(*) as total_bets,
                SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END) as wins,
                SUM(pnl) as total_profit,
                AVG(odds) as avg_odds
            FROM bets_history
            WHERE status IN ('WON', 'LOST')
        """, fetch=True)
        return rows[0] if rows else (0, 0, 0, 0)


if __name__ == "__main__":
    db = OddsBreakerDB()
    db.create_tables()
    print("Database schema created with indexes.")
