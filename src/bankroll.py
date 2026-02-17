import logging

logger = logging.getLogger("BankrollManager")

class BankrollManager:
    def __init__(self, initial_bankroll=1000.0, max_stake_pct=0.05):
        """
        initial_bankroll: The total capital.
        max_stake_pct: Maximum allowed stake (e.g., 0.05 = 5%) to avoid over-exposure.
        """
        self.bankroll = initial_bankroll
        self.max_stake_pct = max_stake_pct

    def calculate_kelly_stake(self, odds, prob):
        """
        Fórmula de Kelly: f* = (bp - q) / b
        f* = Fracción del bankroll a apostar.
        b = Cuota - 1 (ganancia neta por unidad).
        p = Probabilidad de ganar (0 a 1).
        q = Probabilidad de perder (1 - p).
        """
        if odds <= 1: return 0.0
        
        b = odds - 1
        p = prob
        q = 1 - p
        
        fraction = (b * p - q) / b
        
        # We use 'Kelly Fraction' adjustment (e.g. Quarter Kelly or Half Kelly)
        # to be more conservative. Defaulting to Half Kelly (0.5).
        kelly_fraction = 0.5
        stake_pct = fraction * kelly_fraction
        
        # Apply safety limits
        safe_stake_pct = max(0.0, min(stake_pct, self.max_stake_pct))
        stake_amount = self.bankroll * safe_stake_pct
        
        return {
            "percentage": round(safe_stake_pct * 100, 2),
            "amount": round(stake_amount, 2),
            "raw_kelly": round(fraction, 4)
        }

    def update_bankroll(self, pnl):
        self.bankroll += pnl
        logger.info(f"Bankroll updated: {self.bankroll}")

if __name__ == "__main__":
    bm = BankrollManager(1000, 0.05)
    # Example: Odds 2.1, calculated prob 0.55
    res = bm.calculate_kelly_stake(2.1, 0.55)
    print(f"Stake Recommendation: {res}")
