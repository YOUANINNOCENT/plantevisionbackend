import requests
import logging

logger = logging.getLogger(__name__)
resp = requests.get('http://127.0.0.1:8000/admin/ai_mode')
logger.info('%s', resp.text)
