import os
import requests
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

PLANTNET_API_URL = os.getenv('PLANTNET_API_URL', '').strip()
PLANTNET_API_KEY = os.getenv('PLANTNET_API_KEY', '').strip()

if not PLANTNET_API_URL:
    logger.error('PLANTNET_API_URL not set. Set PLANTNET_API_URL in .env or environment to the full endpoint (e.g. https://my-api.plantnet.org/v2/identify/all).')
    raise SystemExit(1)

# pick a test image
img_candidates = ['plante.jpg', 'data/image_1.jpeg', 'data/image_1.png']
img_path = next((p for p in img_candidates if os.path.exists(p)), None)
if not img_path:
    logger.error('No test image found. Place an image named plante.jpg or data/image_1.jpeg and retry.')
    raise SystemExit(1)

logger.info('Using endpoint: %s', PLANTNET_API_URL)
if PLANTNET_API_KEY:
    logger.info('Using API key (masked): %s', PLANTNET_API_KEY[:4] + '...' + PLANTNET_API_KEY[-4:])

files = {'images': open(img_path, 'rb')}

# Try different authentication placements: header Api-Key, header X-Api-Key, Authorization: Bearer, or query param
auth_methods = []
if PLANTNET_API_KEY:
    auth_methods = [
        ('header', {'Api-Key': PLANTNET_API_KEY}),
        ('header', {'X-Api-Key': PLANTNET_API_KEY}),
        ('header', {'Authorization': f'Bearer {PLANTNET_API_KEY}'}),
        ('query', {'api-key': PLANTNET_API_KEY}),
    ]
else:
    auth_methods = [(None, {})]

last_exc = None
for method, auth in auth_methods:
    logger.info('\nTrying auth method: %s %s', method, list(auth.keys()))
    params = {}
    headers = {}
    if method == 'header':
        headers.update(auth)
    elif method == 'query':
        params.update(auth)
    try:
        resp = requests.post(PLANTNET_API_URL, params=params, headers=headers, files=files, timeout=30)
        logger.info('status: %s', resp.status_code)
        try:
            logger.debug('%s', resp.json())
        except Exception:
            logger.debug('%s', resp.text)
        # stop on successful (<400) response
        if resp.status_code < 400:
            break
    except Exception as e:
        logger.exception('Request failed')
        last_exc = e

if last_exc:
    raise last_exc
