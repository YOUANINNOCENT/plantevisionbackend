import requests
r = requests.get('http://127.0.0.1:8000/admin/ai_mode', timeout=5)
print(r.status_code, r.text)
