import requests
import json

url = 'https://www.nseindia.com/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=NIFTY%20500'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

try:
    session = requests.Session()
    session.headers.update(headers)
    session.get('https://www.nseindia.com/', timeout=10)
    
    resp = session.get(url, timeout=15)
    with open('/app/backend/nse_api_dump.json', 'w') as f:
        f.write(resp.text)
    
    data = resp.json()
    stocks = data.get("data", [])
    print(f'Total items: {len(stocks)}')
    symbols = []
    for item in stocks:
        if isinstance(item, dict):
            sym = (item.get("symbol") or "").strip()
            symbols.append(sym)
    print(f'Parsed symbols: {len(symbols)}')
    print(f'First 10 symbols: {symbols[:10]}')
except Exception as e:
    print(f'Error: {e}')
