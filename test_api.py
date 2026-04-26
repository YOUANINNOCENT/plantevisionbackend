import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

PLANTNET_API_URL = os.getenv('PLANTNET_API_URL', '').strip()
PLANTNET_API_KEY = os.getenv('PLANTNET_API_KEY', '').strip()
PLANTID_API_KEY = os.getenv('PLANTID_API_KEY', '').strip()

print('PLANTNET_API_URL =', PLANTNET_API_URL)
print('PLANTNET_API_KEY =', (PLANTNET_API_KEY[:4] + '...' + PLANTNET_API_KEY[-4:]) if PLANTNET_API_KEY else '<not set>')
print('PLANTID_API_KEY =', (PLANTID_API_KEY[:4] + '...' + PLANTID_API_KEY[-4:]) if PLANTID_API_KEY else '<not set>')

# find a test image
candidates = ['data/image_1.jpeg', 'plante.jpg', 'data/image_1.png']
img = next((p for p in candidates if os.path.exists(p)), None)
if not img:
    print('\nNo sample image found in backend/data. Place one and re-run to test live endpoints.')
else:
    print('\nUsing image:', img)
    with open(img, 'rb') as f:
        b = f.read()
    b64 = base64.b64encode(b).decode('ascii')

    if PLANTNET_API_URL and PLANTNET_API_KEY:
        print('\nTesting PlantNet auth...')
        try:
            files = {'images': open(img, 'rb')}
            resp = requests.post(PLANTNET_API_URL, params={'api-key': PLANTNET_API_KEY}, files=files, timeout=20)
            print('STATUS =', resp.status_code)
            try:
                print(resp.json())
            except Exception:
                print(resp.text[:2000])
        except Exception as e:
            print('PlantNet request failed:', e)

    if PLANTID_API_KEY:
        print('\nTesting Plant.id auth...')
        try:
            headers = {'Api-Key': PLANTID_API_KEY, 'Content-Type': 'application/json'}
            resp = requests.post('https://api.plant.id/v3/identification', headers=headers, json={'images':[b64]}, timeout=20)
            print('STATUS =', resp.status_code)
            try:
                print(resp.json())
            except Exception:
                print(resp.text[:2000])
        except Exception as e:
            print('Plant.id request failed:', e)

print('\nTest complete')
