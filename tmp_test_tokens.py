import requests
r = requests.post('http://127.0.0.1:8000/ask', json={'message':'Combien de tokens pour cette réponse ?'}, timeout=60)
print('status', r.status_code)
try:
    print(r.json())
except Exception:
    print(r.text)
