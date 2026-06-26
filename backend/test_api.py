import requests

url = 'https://www.nseindia.com/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=NIFTY%20500'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

try:
    print('Testing new NSE API URL...')
    session = requests.Session()
    session.headers.update(headers)
    session.get('https://www.nseindia.com/', timeout=10)
    
    resp = session.get(url, timeout=15)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'data type: {type(data)}')
        print(f'data keys: {list(data.keys())}')
        print(f'data: {data}')
except Exception as e:
    print(f'Error: {e}')
