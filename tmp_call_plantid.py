import os
import sys
import base64
import traceback
import json

sys.path.insert(0, '.')
# enable debug for this process
os.environ['PLANTID_DEBUG'] = '1'

from services import plant_service

p = 'data/image_1.jpeg'
print('Reading', p)
with open(p, 'rb') as f:
    data = f.read()
img_b64 = base64.b64encode(data).decode()
print('Calling plant_service.call_plantid...')
try:
    res = plant_service.call_plantid(img_b64)
    print('Result OK:')
    print(json.dumps(res, indent=2, ensure_ascii=False))
except Exception as e:
    print('Exception during call:')
    traceback.print_exc()
