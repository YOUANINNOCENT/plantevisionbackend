import requests, base64
base='http://127.0.0.1:8000'
key='4uoC_uTQPMFo__g0nYNXbUfaDSWPWNgyhqzVXaGiKnw'
try:
    r1 = requests.post(base + '/admin/unsplash_key', json={'key': key}, timeout=30)
    print('unsplash store status', r1.status_code)
    print('unsplash store resp (trunc):', r1.text[:200])
except Exception as e:
    print('unsplash store error', type(e).__name__, e)

try:
    r = requests.post(base + '/generate_image', json={'prompt':'Une feuille de menthe sur fond blanc, photographie réaliste','size':'512x512'}, timeout=180)
    print('generate status', r.status_code)
    print('generate resp (trunc):', r.text[:1000])
    try:
        j = r.json()
        if j.get('image_b64'):
            data = base64.b64decode(j['image_b64'])
            open('sortie.png','wb').write(data)
            print('Saved sortie.png, bytes:', len(data))
        else:
            print('JSON keys:', list(j.keys()))
    except Exception as e:
        print('JSON parse/save error', type(e).__name__, e)
except Exception as e:
    print('generate request error', type(e).__name__, e)
