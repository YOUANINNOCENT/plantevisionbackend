import requests, base64, json
r = requests.post("http://127.0.0.1:8000/generate_image", json={"prompt":"Une feuille de menthe sur fond blanc, photographie réaliste","size":"512x512"}, timeout=120)
print("STATUS", r.status_code)
print(r.text[:2000])
try:
    j=r.json()
    img=j.get("image_b64")
    if img:
        data=base64.b64decode(img)
        open("sortie.png","wb").write(data)
        print("Saved sortie.png bytes:", len(data))
except Exception as e:
    print("JSON/save error", e)
