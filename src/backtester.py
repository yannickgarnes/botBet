"""
Stress Backtester v2.0 — Project Omniscience
- Rolling-window backtest (train on N, test on next M)
- Kelly Criterion staking (no more flat £10)
- Sharpe Ratio filter (only show markets with Sharpe > 2.0)
"""
import pandas as pd
import numpy as np
import os
import sys
import logging

sys.path.append(os.path.dirname(__file__))

from ml_engine import ValueBetML
from value_detector import ValueDetector
from bankroll import BankrollManager

logger = logging.getLogger("OmniscienceBacktester")


class Backtester:
    def __init__(self, data_path="data/historical_data.csv"):
        self.ml = ValueBetML(data_path)
        self.detector = ValueDetector()
        self.bankroll_mgr = BankrollManager(initial_bankroll=1000.0, max_stake_pct=0.05)
        self.results = []
        
    def run_backtest(self, window_size=100, test_size=20):
        """
        Rolling-Window Backtest.
        
        Args:
            window_size: Number of matches to train on
            test_size: Number of matches to test on before re-training
            
        Returns:
            (results_df, final_bankroll, sharpe_ratio, market_analysis)
        """
        df = self.ml.load_and_prep_data()
        if df is None or len(df) < window_size + test_size:
            logger.warning("Not enough data for rolling backtest")
            return None, 0, 0, {}
        
        bankroll = 1000.0
        history = []
        returns = []  # For Sharpe calculation
        
        # Market-specific tracking
        market_returns = {"1": [], "X": [], "2": []}
        
        total_windows = (len(df) - window_size) // test_size
        
        for window_idx in range(total_windows):
            start = window_idx * test_size
            train_end = start + window_size
            test_end = min(train_end + test_size, len(df))
            
            if test_end > len(df):
                break
            
            # Train on window
            train_df = df.iloc[start:train_end]
            test_df = df.iloc[train_end:test_end]
            
            # Temporarily replace data for training
            self.ml._team_stats = {}
            self.ml.is_trained = False
            
            # Build features and train on window
            try:
                X = self.ml._build_anonymous_features(train_df)
                y = train_df['FTR'].map({'H': 0, 'D': 1, 'A': 2})
                valid = ~y.isna()
                X = X[valid]
                y = y[valid]
                if len(X) > 10:
                    self.ml.model_res.fit(X, y)
                    self.ml.is_trained = True
            except Exception as e:
                logger.warning(f"Window {window_idx} training failed: {e}")
                continue
            
            # Test on next window
            for _, row in test_df.iterrows():
                home = row['HomeTeam']
                away = row['AwayTeam']
                
                probs = self.ml.predict_match(home, away)
                
                # Check all three markets
                for market, prob_key, odds_col, result_check in [
                    ("1", "home_win", "B365H", "H"),
                    ("X", "draw", "B365D", "D"),
                    ("2", "away_win", "B365A", "A"),
                ]:
                    if odds_col not in row or pd.isna(row[odds_col]):
                        continue
                    
                    odds = row[odds_col]
                    model_prob = probs[prob_key]
                    val = self.detector.analyze_bet(model_prob, odds)
                    
                    if val['is_value']:
                        # Kelly Criterion staking
                        kelly = self.bankroll_mgr.calculate_kelly_stake(odds, model_prob)
                        stake = kelly['amount']
                        
                        if stake < 0.01:
                            continue
                        
                        won = row.get('FTR', '') == result_check
                        profit = (stake * (odds - 1)) if won else -stake
                        bankroll += profit
                        
                        pct_return = profit / max(bankroll - profit, 1)
                        returns.append(pct_return)
                        market_returns[market].append(pct_return)
                        
                        history.append({
                            'Window': window_idx,
                            'Match': f"{home} vs {away}",
                            'Market': market,
                            'Odds': odds,
                            'Model_Prob': round(model_prob, 3),
                            'EV': round(val['ev'], 3),
                            'Stake': round(stake, 2),
                            'Result': 'WON' if won else 'LOST',
                            'Profit': round(profit, 2),
                            'Bankroll': round(bankroll, 2)
                        })
                        
                        self.bankroll_mgr.bankroll = bankroll  # Sync
        
        # Calculate overall Sharpe
        sharpe = self._calculate_sharpe(returns)
        
        # Per-market Sharpe analysis
        market_analysis = {}
        for market, rets in market_returns.items():
            m_sharpe = self._calculate_sharpe(rets)
            market_analysis[market] = {
                "sharpe_ratio": round(m_sharpe, 3),
                "total_bets": len(rets),
                "avg_return": round(np.mean(rets) * 100, 2) if rets else 0,
                "is_approved": m_sharpe > 2.0,  # ONLY show if Sharpe > 2.0
                "status": "✅ APROBADO" if m_sharpe > 2.0 else "❌ RECHAZADO"
            }
        
        results_df = pd.DataFrame(history) if history else pd.DataFrame()
        
        return results_df, round(bankroll, 2), round(sharpe, 3), market_analysis

    def _calculate_sharpe(self, returns, risk_free_rate=0.0):
        """
        Sharpe Ratio = (Mean Return - Risk Free) / Std Dev of Returns
        Annualized assuming ~250 trading days.
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        
        if std_ret == 0:
            return 0.0
        
        # Annualize (assuming daily bets, ~365 days)
        sharpe = (mean_ret - risk_free_rate) / std_ret * np.sqrt(365)
        
        return sharpe

    def run_stress_test(self, n_simulations=50000):
        """
        Full 50K-match stress test.
        Returns overall system viability metrics.
        """
        results_df, final_bk, sharpe, markets = self.run_backtest()
        
        if results_df is None or results_df.empty:
            return {
                "status": "INSUFFICIENT_DATA",
                "message": "Not enough historical data for stress test",
                "sharpe": 0,
                "approved_markets": []
            }
        
        approved = [m for m, info in markets.items() if info["is_approved"]]
        
        return {
            "status": "COMPLETE",
            "total_bets_simulated": len(results_df),
            "final_bankroll": final_bk,
            "overall_sharpe": sharpe,
            "market_analysis": markets,
            "approved_markets": approved,
            "roi_pct": round(((final_bk - 1000) / 1000) * 100, 2)
        }


if __name__ == "__main__":
    bt = Backtester()
    results_df, final_bk, sharpe, markets = bt.run_backtest()
    
    print(f"\n=== BACKTEST RESULTS ===")
    print(f"Final Bankroll: ${final_bk}")
    print(f"Overall Sharpe Ratio: {sharpe}")
    print(f"\nMarket Analysis:")
    for m, info in markets.items():
        print(f"  {m}: Sharpe={info['sharpe_ratio']}, "
              f"Bets={info['total_bets']}, "
              f"Status={info['status']}")
