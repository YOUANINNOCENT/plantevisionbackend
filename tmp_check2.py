import requests
try:
    r = requests.get('http://127.0.0.1:8000/admin/ai_mode', timeout=10)
    print('GET /admin/ai_mode', r.status_code)
    try:
        print(r.json())
    except:
        print(r.text[:1000])
except Exception as e:
    print('error', e)
