"""
Monte Carlo Simulator v2.0 — Project Omniscience
- 50,000 iterations (stress-level)
- Sharpe Ratio calculation built-in
- Compatible with dashboard "Control Total" visualizations
"""
import numpy as np
import plotly.graph_objects as go
import pandas as pd
import logging

logger = logging.getLogger("OmniscienceSimulator")


class ValueSimulator:
    def __init__(self, bankroll=1000.0, iterations=50000):
        self.bankroll_start = bankroll
        self.iterations = iterations

    def run_monte_carlo(self, p_win, odds, stake_pct, num_bets=500):
        """
        Simulates 50,000 paths of betting strategy.
        Returns comprehensive metrics including Sharpe Ratio.
        """
        results = []
        ruin_count = 0
        all_returns = []
        
        for _ in range(self.iterations):
            current_bank = self.bankroll_start
            path = [current_bank]
            path_returns = []
            
            outcomes = np.random.choice([1, 0], size=num_bets, p=[p_win, 1 - p_win])
            
            for win in outcomes:
                stake = current_bank * stake_pct
                if win:
                    profit = stake * (odds - 1)
                    current_bank += profit
                else:
                    profit = -stake
                    current_bank -= stake
                
                pct_return = profit / max(current_bank - profit, 1)
                path_returns.append(pct_return)
                path.append(current_bank)
                
                if current_bank < 1.0:
                    ruin_count += 1
                    break
            
            results.append(path[-1])
            all_returns.extend(path_returns)
            
        prob_ruin = ruin_count / self.iterations
        avg_final = np.mean(results)
        
        # Sharpe Ratio
        sharpe = self._calculate_sharpe(all_returns)
        
        # Percentiles for risk assessment
        p5 = np.percentile(results, 5)
        p25 = np.percentile(results, 25)
        p75 = np.percentile(results, 75)
        p95 = np.percentile(results, 95)
        
        return {
            "prob_ruin": round(prob_ruin, 4),
            "expected_bankroll": round(avg_final, 2),
            "median_bankroll": round(np.median(results), 2),
            "sharpe_ratio": round(sharpe, 3),
            "percentile_5": round(p5, 2),
            "percentile_25": round(p25, 2),
            "percentile_75": round(p75, 2),
            "percentile_95": round(p95, 2),
            "max_drawdown_avg": round(self._avg_max_drawdown(results), 2),
            "iterations": self.iterations,
            "is_viable": sharpe > 2.0  # OMNISCIENCE FILTER
        }

    def _calculate_sharpe(self, returns, risk_free=0.0):
        """Annualized Sharpe Ratio."""
        if not returns or len(returns) < 2:
            return 0.0
        mean_r = np.mean(returns)
        std_r = np.std(returns)
        if std_r == 0:
            return 0.0
        return (mean_r - risk_free) / std_r * np.sqrt(365)

    def _avg_max_drawdown(self, final_bankrolls):
        """Average maximum drawdown from peak."""
        below_start = [b for b in final_bankrolls if b < self.bankroll_start]
        if not below_start:
            return 0.0
        worst_losses = [(self.bankroll_start - b) / self.bankroll_start * 100 for b in below_start]
        return np.mean(worst_losses)

    def generate_equity_comparison(self, history_df):
        """
        Compares strategy: Blind betting vs Value betting (>5%).
        """
        fig = go.Figure()
        
        blind_equity = [self.bankroll_start]
        value_equity = [self.bankroll_start]
        
        for _, row in history_df.iterrows():
            # Blind Path
            stake = blind_equity[-1] * 0.02
            if row['outcome'] == 'win':
                blind_equity.append(blind_equity[-1] + (stake * (row['odds'] - 1)))
            else:
                blind_equity.append(blind_equity[-1] - stake)
                
            # Value Path
            if row['is_value_ia']:
                v_stake = value_equity[-1] * row['kelly_stake']
                if row['outcome'] == 'win':
                    value_equity.append(value_equity[-1] + (v_stake * (row['odds'] - 1)))
                else:
                    value_equity.append(value_equity[-1] - v_stake)
            else:
                value_equity.append(value_equity[-1])

        fig.add_trace(go.Scatter(
            y=blind_equity, name="Apuestas Ciegas (2% Fijo)", 
            line=dict(color='gray', dash='dash'),
            fill='tozeroy', fillcolor='rgba(128,128,128,0.1)'
        ))
        fig.add_trace(go.Scatter(
            y=value_equity, name="Value Betting (IA + Kelly)", 
            line=dict(color='#00FFCC', width=3),
            fill='tozeroy', fillcolor='rgba(0,255,204,0.1)'
        ))
        
        fig.update_layout(
            template="plotly_dark",
            title="⚡ Comparación de Equity — Ciego vs IA Omniscience",
            xaxis_title="Número de Apuestas",
            yaxis_title="Bankroll ($)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        
        return fig


if __name__ == "__main__":
    sim = ValueSimulator(1000, iterations=50000)
    report = sim.run_monte_carlo(0.5, 2.2, 0.02)
    print(f"Monte Carlo 50K Results:")
    for k, v in report.items():
        print(f"  {k}: {v}")
