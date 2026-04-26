# assistant_botanique.py

import os
import requests
import time
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# ==============================
# CONFIGURATION (from environment)
# ==============================
# Read API keys from environment to avoid hard-coded secrets.
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY", "")
PIXAZO_API_KEY = os.getenv("PIXAZO_API_KEY", "")

if not PLANTNET_API_KEY:
    logger.warning("PLANTNET_API_KEY not set in environment; PlantNet calls will likely fail")
if not PIXAZO_API_KEY:
    logger.warning("PIXAZO_API_KEY not set in environment; image generation will likely fail")

PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
PIXAZO_URL = "https://api.pixazo.ai/v1/images/generate"


# ==============================
# COMPRESSION IMAGE
# ==============================
def compresser_image(input_path):
    img = Image.open(input_path)
    img = img.resize((800, 800))
    output_path = "temp.jpg"
    img.save(output_path, quality=70)
    return output_path


# ==============================
# IDENTIFICATION PLANTE
# ==============================
def identifier_plante(image_path):
    for tentative in range(3):
        try:
            with open(image_path, "rb") as img:
                response = requests.post(
                    PLANTNET_URL,
                    files={"images": img},
                    data={
                        "api-key": PLANTNET_API_KEY,
                        "organs": "leaf"
                    },
                    timeout=30
                )

            if response.status_code == 200:
                data = response.json()
                try:
                    return data["results"][0]["species"]["scientificNameWithoutAuthor"]
                except:
                    return "Plante inconnue"

            elif response.status_code == 504:
                print("Serveur lent, retry...")
                time.sleep(2)

            else:
                return f"Erreur API: {response.status_code}"

        except requests.exceptions.Timeout:
            print("Timeout, retry...")
            time.sleep(2)

        except Exception as e:
            return f"Erreur: {str(e)}"

    return "Serveur indisponible"


# ==============================
# GENERATION IMAGE PIXAZO
# ==============================
def generer_image(prompt):
    if not PIXAZO_API_KEY:
        return {"error": "PIXAZO_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {PIXAZO_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {"prompt": prompt, "model": "flux"}

    try:
        response = requests.post(PIXAZO_URL, headers=headers, json=data, timeout=30)

        if response.status_code != 200:
            return {"error": f"Erreur image: {response.status_code}", "status": response.status_code}

        # Try to parse JSON first
        ct = response.headers.get('content-type', '')
        if 'application/json' in ct:
            j = response.json()
            # Common provider shapes: {'image_url': 'http...'} or {'data': 'data:image/...;base64,...'}
            for key in ('image', 'image_url', 'url', 'data', 'result'):
                if isinstance(j, dict) and key in j:
                    return {key: j[key]}
            # if provider returns nested structure, try to find strings that look like urls/base64
            def find_str(d):
                if isinstance(d, dict):
                    for v in d.values():
                        r = find_str(v)
                        if r:
                            return r
                if isinstance(d, list):
                    for v in d:
                        r = find_str(v)
                        if r:
                            return r
                if isinstance(d, str):
                    if d.startswith('data:image') or d.startswith('http'):
                        return d
                return None

            s = find_str(j)
            if s:
                # return under consistent key
                if s.startswith('data:image'):
                    return {"image_b64": s}
                return {"image_url": s}
            return {"raw": j}

        # If response is image bytes, return base64 data URI
        if ct.startswith('image/'):
            import base64

            b64 = base64.b64encode(response.content).decode('ascii')
            return {"image_b64": f"data:{ct};base64,{b64}"}

        # Unknown content-type: return raw text
        text = response.text
        return {"raw_text": text}

    except requests.exceptions.Timeout:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


# ==============================
# ASSISTANT BOTANIQUE
# ==============================
def assistant_botanique(image_path):

    print("Compression image...")
    image_path = compresser_image(image_path)

    print("Identification plante...")
    plante = identifier_plante(image_path)

    print("Generation description...")
    description = f"{plante} est une plante pouvant être comestible, médicinale ou toxique selon son usage."

    print("Generation image...")
    image = generer_image(f"{plante}, plante réaliste, haute qualité")

    return {
        "plante": plante,
        "description": description,
        "image": image
    }


if __name__ == "__main__":
    result = assistant_botanique("plante.jpg")
    print(result)
