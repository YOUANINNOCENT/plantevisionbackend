import time, requests
base='http://127.0.0.1:8000'
for i in range(15):
    try:
        r = requests.get(base + '/health', timeout=3)
        if r.status_code==200:
            print('health ok')
            break
    except Exception as e:
        pass
    time.sleep(1)
else:
    print('server not ready')
    raise SystemExit(1)

r = requests.post(base + '/ask', json={'message':'Bonjour, test après redémarrage'}, timeout=60)
print('/ask', r.status_code)
try:
    print(r.json())
except Exception:
    print(r.text[:1000])
