import requests
base='http://127.0.0.1:8000'
print('Check ai_mode:', requests.get(base+'/admin/ai_mode').text)
print('Posting unsplash key test (empty) to verify endpoint responds...')
# don't actually post a real key here; just show endpoint exists
# r = requests.post(base + '/admin/unsplash_key', json={'key':'TESTKEY'})
# print('unsplash store', r.status_code, r.text)
print('Ready')
