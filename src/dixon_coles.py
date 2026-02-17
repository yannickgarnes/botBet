import numpy as np
from scipy.stats import poisson
from scipy.optimize import minimize
import logging

logger = logging.getLogger("DixonColesEngine")

class DixonColesModel:
    """
    Implements the Dixon-Coles adjustment to the Poisson distribution
    for soccer score predictions, including time decay (recency weighting).
    """
    def __init__(self, rho=0.0):
        self.rho = rho # Dependence parameter (calculated via historical fit)

    def tau(self, x, y, mu, lamb, rho):
        """
        Dixon-Coles adjustment function for low scores (0-0, 1-0, 0-1, 1-1).
        Corrects for under-counting of draws.
        """
        if x == 0 and y == 0:
            return 1 - (mu * lamb * rho)
        elif x == 0 and y == 1:
            return 1 + (mu * rho)
        elif x == 1 and y == 0:
            return 1 + (lamb * rho)
        elif x == 1 and y == 1:
            return 1 - rho
        else:
            return 1.0

    def calculate_match_probabilities(self, home_exp_goals, away_exp_goals, max_goals=10):
        """
        Calculates 1X2 probabilities using Adjusted Poisson.
        """
        prob_matrix = np.zeros((max_goals, max_goals))
        
        for x in range(max_goals):
            for y in range(max_goals):
                # Simple Poisson Probabilities
                p_x = poisson.pmf(x, home_exp_goals)
                p_y = poisson.pmf(y, away_exp_goals)
                
                # Dixon-Coles Adjustment
                adjustment = self.tau(x, y, home_exp_goals, away_exp_goals, self.rho)
                
                prob_matrix[x, y] = p_x * p_y * adjustment
        
        # Normalize (ensure sum is 1.0)
        prob_matrix /= prob_matrix.sum()
        
        home_win = np.sum(np.tril(prob_matrix, -1))
        draw = np.sum(np.diag(prob_matrix))
        away_win = np.sum(np.triu(prob_matrix, 1))
        
        return {
            "1": round(home_win, 4),
            "X": round(draw, 4),
            "2": round(away_win, 4)
        }

    def apply_recency_weighting(self, matches_df, xi=0.0065):
        """
        Applies time decay weighting.
        xi: Decay parameter (higher = faster decay).
        matches_df must have a 'days_ago' column.
        """
        weights = np.exp(-xi * matches_df['days_ago'])
        return weights

# Example Implementation for integration
def get_dixon_coles_probs(home_mu, away_mu, rho=-0.1):
    model = DixonColesModel(rho=rho)
    return model.calculate_match_probabilities(home_mu, away_mu)

if __name__ == "__main__":
    # Test with typical soccer values
    home_mu, away_mu = 1.45, 1.15
    probs = get_dixon_coles_probs(home_mu, away_mu)
    print(f"Dixon-Coles Probs (Home {home_mu}, Away {away_mu}): {probs}")
