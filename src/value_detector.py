class ValueDetector:
    def __init__(self):
        pass

    def calculate_margin(self, odds_home, odds_draw, odds_away):
        """
        Calculates the bookmaker's margin.
        Formula: (1/Home + 1/Draw + 1/Away) - 1
        """
        margin = (1/odds_home + 1/odds_draw + 1/odds_away) - 1
        return margin

    def get_implied_probability(self, odds, margin=0):
        """
        Returns the true implied probability (removing margin proportionally).
        """
        raw_prob = 1 / odds
        # Adjusted for margin (fair odds)
        # Simple method: raw_prob / (1 + margin)
        fair_prob = raw_prob / (1 + margin)
        return fair_prob

    def analyze_bet(self, model_prob, bookmaker_odds):
        """
        Compares Model Probability (Real) vs Bookmaker Implied Probability.
        Returns EV (Expected Value).
        EV = (Probability * Odds) - 1
        If EV > 0, it's a value bet.
        """
        ev = (model_prob * bookmaker_odds) - 1
        
        is_value = ev > 0.05 # Threshold: 5% Value
        grade = "NO BET"
        
        if ev > 0.20: grade = "💎 DIAMOND"
        elif ev > 0.10: grade = "🥇 GOLD"
        elif ev > 0.05: grade = "🥈 SILVER"
        elif ev > 0: grade = "🥉 BRONZE"
        
        return {
            'ev': ev,
            'is_value': is_value,
            'grade': grade,
            'model_prob': model_prob,
            'implied_prob': 1/bookmaker_odds
        }
