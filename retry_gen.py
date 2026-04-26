import requests, json
import logging

logger = logging.getLogger(__name__)
url='http://127.0.0.1:8000/generate_image'
logger.info('Posting to %s', url)
try:
    r = requests.post(url, json={'prompt':'Une feuille de menthe sur fond blanc, photographie réaliste','size':'512x512'}, timeout=120)
    logger.info('STATUS %s', r.status_code)
    logger.debug('HEADERS %s', r.headers)
    logger.debug('BODY %s', r.text)
    try:
        j = r.json()
        logger.info('JSON keys: %s', list(j.keys()))
    except Exception as e:
        logger.exception('No JSON')
except Exception as e:
    logger.exception('REQUEST ERROR')
