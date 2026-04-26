import os
import base64
import json
import requests

IMG_PATHS = ['data/image_1.jpeg', 'plante.jpg', 'data/image_1.png']
img = next((p for p in IMG_PATHS if os.path.exists(p)), None)
if not img:
    print('No test image found in data/. Place data/image_1.jpeg and retry.')
    raise SystemExit(1)

with open(img, 'rb') as f:
    b = f.read()

b64 = base64.b64encode(b).decode('ascii')

url = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')
endpoint = f"{url}/identify_plantnet"
print('Posting to', endpoint)

try:
    resp = requests.post(endpoint, json={'images': [b64], 'user_id': 1}, timeout=60)
    print('HTTP', resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)
except requests.exceptions.Timeout:
    print('Request timed out')
except Exception as e:
    print('Request failed:', e)
