from fastapi import APIRouter, HTTPException, Depends
import pandas as pd
import os
from backend.app.dependencies import get_current_user
from backend.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.get("/{symbol}")
async def get_chart_data(symbol: str, tf: str = "15minute", current_user = Depends(get_current_user)):
    # Map friendly names to actual file suffixes if needed
    if tf == "15m":
        tf_suffix = "15minute"
    elif tf == "1D" or tf == "day" or tf == "daily":
        tf_suffix = "day"
    else:
        tf_suffix = tf
        
    file_path = f"/app/data/historical/{symbol}_{tf_suffix}.csv"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Historical data not found for symbol on timeframe {tf}")
    
    try:
        df = pd.read_csv(file_path)
        
        # Standardize columns
        df.columns = [c.lower() for c in df.columns]
        if 'datetime' in df.columns:
            df.rename(columns={'datetime': 'date'}, inplace=True)
            
        # Calculate static Support & Resistance (Pivot levels)
        # We'll use recent 20, 60, and 200 periods
        sr_levels = {}
        if len(df) >= 20:
            sr_levels['R1_20'] = float(df['high'].tail(20).max())
            sr_levels['S1_20'] = float(df['low'].tail(20).min())
        if len(df) >= 60:
            sr_levels['R2_60'] = float(df['high'].tail(60).max())
            sr_levels['S2_60'] = float(df['low'].tail(60).min())
        if len(df) >= 200:
            sr_levels['R3_200'] = float(df['high'].tail(200).max())
            sr_levels['S3_200'] = float(df['low'].tail(200).min())
            
        # Take the last 500 rows for the chart to show plenty of data
        df = df.tail(500)
        
        data = []
        for _, row in df.iterrows():
            # lightweight-charts uses unix timestamp in seconds for intraday
            dt = pd.to_datetime(row['date'])
            # Assuming IST, let's just use UTC timestamp if the data is already localized
            time_val = int(dt.timestamp())
            
            data.append({
                "time": time_val,
                "open": float(row.get('open', 0)),
                "high": float(row.get('high', 0)),
                "low": float(row.get('low', 0)),
                "close": float(row.get('close', 0)),
                "value": float(row.get('volume', 0)),
                "color": "#26a69a" if float(row.get('close', 0)) >= float(row.get('open', 0)) else "#ef5350",
            })
            
        return {"status": "success", "data": data, "sr_levels": sr_levels}
        
    except Exception as e:
        logger.error(f"Error serving chart data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading data: {str(e)}")
