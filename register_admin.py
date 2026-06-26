import requests

resp = requests.post("http://localhost:8000/api/auth/register", json={
    "email": "admin@swingtrade.com",
    "username": "admin",
    "password": "password"
})
print(resp.status_code, resp.text)
