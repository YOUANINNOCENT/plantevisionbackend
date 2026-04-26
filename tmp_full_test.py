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

r = requests.post('http://127.0.0.1:8000/admin/ai_mode', json={'mode':'remote'}, timeout=10)
print('POST set remote', r.status_code)
try:
    print(r.json())
except:
    print(r.text[:1000])

r2 = requests.get('http://127.0.0.1:8000/admin/ai_mode', timeout=10)
print('GET again', r2.status_code)
try:
    print(r2.json())
except:
    print(r2.text[:1000])

r3 = requests.post('http://127.0.0.1:8000/ask', json={'message':'Bonjour, test accès IA'}, timeout=60)
print('/ask status', r3.status_code)
try:
    print(r3.json())
except:
    print(r3.text[:1000])
