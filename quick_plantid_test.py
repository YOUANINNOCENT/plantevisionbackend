import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PLANTID_API_KEY")

if not API_KEY:
    print("PLANTID_API_KEY not set in environment or .env")
    raise SystemExit(1)

# choose an image (fall back to data/image_1.jpeg)
img_paths = ["plante.jpg", "data/image_1.jpeg", "data/image_1.png"]
img_path = next((p for p in img_paths if os.path.exists(p)), None)
if not img_path:
    print("Aucune image trouvée. Placez une image nommée 'plante.jpg' ou 'data/image_1.jpeg'")
    raise SystemExit(1)

with open(img_path, "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

masked = (API_KEY[:4] + "..." + API_KEY[-4:]) if len(API_KEY) > 8 else "***"
print(f"Using API key: {masked}")

try:
    resp = requests.post(
        "https://api.plant.id/v3/identification",
        params={
            "details": "common_names,taxonomy,description,best_watering,best_light_condition,best_soil_type",
            "language": "fr",
        },
        headers={
            "Api-Key": API_KEY,
            "Content-Type": "application/json",
        },
        json={"images": [image_b64]},
        timeout=20,
    )
    print("status:", resp.status_code)
    print(resp.text)
except Exception as e:
    print("Request failed:", e)
    raise
