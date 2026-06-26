import requests, io
import pandas as pd

url = 'https://niftyindices.com/IndexConstituents/ind_nifty500list.csv'
headers = {'User-Agent': 'Mozilla/5.0'}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f'Status: {resp.status_code}, Content-Type: {resp.headers.get("content-type")}')
    
    lines = resp.text.splitlines()
    header_idx = 0
    for i, line in enumerate(lines):
        if 'symbol' in line.lower():
            header_idx = i
            print(f'Found header at {i}: {line}')
            break
            
    df = pd.read_csv(io.StringIO(resp.text), skiprows=header_idx, on_bad_lines='skip', dtype=str)
    print(f'Columns: {list(df.columns)}')
    # Try different case for Symbol column
    symbol_col = next((c for c in df.columns if 'symbol' in c.lower()), None)
    if symbol_col:
        symbols = df[symbol_col].dropna().tolist()
        print(f'Found {len(symbols)} symbols. First 5: {symbols[:5]}')
    else:
        print('No symbol column found')
except Exception as e:
    print(f'Error: {e}')
