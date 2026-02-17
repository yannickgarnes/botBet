import sys
import os
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ml_engine import ValueBetML
from src.value_detector import ValueDetector
from src.backtester import Backtester

def test_integration():
    print("TEST: Initializing ML Engine...")
    ml = ValueBetML()
    if ml.load_and_prep_data() is None:
        print("FAIL: Data not found.")
        return
        
    print("TEST: Training Model...")
    acc = ml.train()
    if acc is None:
        print("FAIL: Model training failed.")
        return
    print(f"PASS: Model Accuracy: {acc:.2f}")

    print("TEST: Predicting Match...")
    probs = ml.predict_match("Real Madrid", "Barcelona")
    print(f"PASS: Predictions: {probs}")
    
    print("TEST: Value Detection...")
    detector = ValueDetector()
    val = detector.analyze_bet(probs['home_win'], 2.50)
    print(f"PASS: Value Analysis: {val}")
    
    print("TEST: Backtesting...")
    backtester = Backtester()
    results, bankroll = backtester.run_backtest()
    if results is not None:
        print(f"PASS: Backtest Complete. Final Bankroll: {bankroll}")
    else:
        print("FAIL: Backtest returned None.")

if __name__ == "__main__":
    test_integration()
