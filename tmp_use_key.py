import requests, base64
base='http://127.0.0.1:8000'
# store provided key (user-provided)
k='52d5b0344e79d20aed9522326c0138e896bea211'
try:
    r1 = requests.post(base + '/admin/openai_key', json={'key': k}, timeout=30)
    print('store status', r1.status_code, r1.text[:200])
except Exception as e:
    print('store error', type(e).__name__, e)
try:
    r2 = requests.post(base + '/admin/ai_mode', json={'mode':'remote'}, timeout=30)
    print('mode status', r2.status_code, r2.text[:200])
except Exception as e:
    print('mode error', type(e).__name__, e)
try:
    r = requests.post(base + '/generate_image', json={'prompt':'Une feuille de menthe sur fond blanc, photographie réaliste','size':'512x512'}, timeout=180)
    print('generate status', r.status_code)
    print(r.text[:2000])
    try:
        j = r.json()
        img = j.get('image_b64')
        if img:
            data = base64.b64decode(img)
            open('sortie.png','wb').write(data)
            print('Saved sortie.png bytes:', len(data))
        else:
            print('No image_b64 in response')
    except Exception as e:
        print('json/save error', type(e).__name__, e)
except Exception as e:
    print('request error', type(e).__name__, e)
