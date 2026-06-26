import pandas as pd
from backend.engine.indicators.engine import IndicatorEngine

def test_indicator_calculation():
    df = pd.DataFrame({"close": [100]*50, "high": [105]*50, "low": [95]*50, "volume": [1000]*50})
    res = IndicatorEngine.calculate_all(df)
    assert "rsi" in res.columns
    assert "macd" in res.columns
