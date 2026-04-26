import requests, json
base='http://127.0.0.1:8000'
long_prompt = 'Explique en détails la biosynthèse du menthol dans Mentha × piperita, en décrivant les voies métaboliques, enzymes clés, localisation cellulaire et facteurs influençant la production. Répondez de façon technique et approfondie.'
r = requests.post(base + '/ask', json={'message': long_prompt}, timeout=120)
print('/ask', r.status_code)
try:
    print(json.dumps(r.json(), ensure_ascii=False)[:4000])
except Exception:
    print(r.text[:2000])
