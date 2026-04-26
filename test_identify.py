import base64, requests, json, sys, os

def main():
    # Accept image path as first arg, default to backend/data/image_1.jpeg
    img_arg = sys.argv[1] if len(sys.argv) > 1 else os.path.join('data', 'image_1.jpeg')
    if not os.path.exists(img_arg):
        print('Image not found:', img_arg)
        sys.exit(2)

    with open(img_arg, 'rb') as f:
        img = f.read()

    b64 = base64.b64encode(img).decode()
    try:
        r = requests.post('http://127.0.0.1:8000/identify', json={'images':[b64], 'user_id': 1}, timeout=60)
        print('status', r.status_code)
        try:
            print(json.dumps(r.json(), indent=2))
        except Exception:
            print(r.text)
    except Exception as e:
        print('request failed:', e)
        sys.exit(1)

if __name__ == '__main__':
    main()
