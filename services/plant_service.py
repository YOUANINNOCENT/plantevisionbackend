import os
import requests
import base64
import json
import time
from pathlib import Path
from typing import Optional
import io

API_URL = "https://api.plant.id/v3/identification"


def call_plantid(image_b64: str) -> dict:
    # Read the API key from environment at call time so it can be set dynamically
    key = os.environ.get("PLANTID_API_KEY", "").strip().strip('"')
    if not key:
        # try loading .env in repo root (dev convenience)
        try:
            base_dir = Path(__file__).resolve().parents[1]
            env_path = base_dir / '.env'
            if env_path.exists():
                for ln in env_path.read_text(encoding='utf8').splitlines():
                    if not ln or ln.strip().startswith('#'):
                        continue
                    if '=' not in ln:
                        continue
                    k, v = ln.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v:
                        os.environ.setdefault(k, v)
                key = os.environ.get('PLANTID_API_KEY', '').strip().strip('"')
        except Exception:
            key = os.environ.get('PLANTID_API_KEY', '')

    if not key:
        return {"error": "Clé API non trouvée (PLANTID_API_KEY non configurée)"}

    headers = {"Api-Key": key, "Content-Type": "application/json"}
    params = {
        "details": "common_names,taxonomy,description,best_watering,best_light_condition,best_soil_type",
        "language": "fr",
    }
    json_body = {"images": [image_b64]}

    # optional debug logging (activate by setting PLANTID_DEBUG=1)
    debug = os.environ.get("PLANTID_DEBUG", "") == "1"
    if debug:
        masked = (key[:4] + "..." + key[-4:]) if len(key) > 8 else "***"
        try:
            sample = json.dumps(json_body)[:1000]
        except Exception:
            sample = "<unable to jsonify>"
        print(f"[PLANTID DEBUG] API KEY = {masked}")
        print(f"[PLANTID DEBUG] POST {API_URL}")
        print(f"[PLANTID DEBUG] params={params}")
        print(f"[PLANTID DEBUG] json(sample)={sample}")
    try:
        resp = requests.post(
            API_URL,
            params=params,
            headers=headers,
            json=json_body,
            timeout=20,
        )
    except requests.exceptions.Timeout:
        if debug:
            print("[PLANTID DEBUG] Timeout when calling Plant.id")
        return {"error": "Timeout API"}
    except requests.exceptions.ConnectionError as e:
        if debug:
            print(f"[PLANTID DEBUG] ConnectionError: {e}")
        return {"error": "Erreur connexion API"}
    except Exception as e:
        if debug:
            print(f"[PLANTID DEBUG] Exception: {e}")
        return {"error": f"Unexpected error: {e}"}

    if debug:
        print(f"[PLANTID DEBUG] STATUS = {resp.status_code}")
        print(f"[PLANTID DEBUG] RESPONSE = {resp.text[:2000]}")

    if resp.status_code == 401:
        return {"error": "Clé API invalide ou mal configurée"}
    if resp.status_code == 403:
        return {"error": "Accès refusé (IP ou restriction)"}

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        return {"error": f"Plant.id HTTP {resp.status_code}: {resp.text}"}

    try:
        return resp.json()
    except Exception:
        return {"text": resp.text}


def format_result(data: dict) -> str:
    try:
        # Two possible response shapes are supported:
        # - legacy: data.result.classification.suggestions (probability)
        # - newer: data.results -> list of {score, species: {...}}

        # Newer Plant.id style: use `results` array with `score` and `species`
        if isinstance(data.get("results"), list) and data.get("results"):
            results = list(data.get("results"))
            # sort by score desc
            results.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
            top = results[0]
            score = round(float(top.get("score", 0)) * 100, 1)
            species = top.get("species", {}) or {}
            nom_sci = species.get("scientificNameWithoutAuthor") or species.get("scientificName", "Inconnu")
            noms_communs = species.get("commonNames") or []
            nom_commun = ", ".join(noms_communs[:3]) if noms_communs else "Non disponible"
            famille = (species.get("family") or {}).get("scientificNameWithoutAuthor") if isinstance(species.get("family"), dict) else (species.get("family") or "—")
            genre = (species.get("genus") or {}).get("scientificNameWithoutAuthor") if isinstance(species.get("genus"), dict) else (species.get("genus") or "—")

            lines = [
                f"🌿 Plante identifiée : {nom_sci} ({score}% de confiance)",
                f"📛 Noms communs     : {nom_commun}",
                f"🔬 Famille          : {famille} | Genre : {genre}",
            ]

            # other possibilities
            if len(results) > 1:
                autres = [
                    f"  - {(r.get('species') or {}).get('scientificNameWithoutAuthor', (r.get('species') or {}).get('scientificName', 'Inconnu'))} ({round(float(r.get('score',0))*100,1)}%)"
                    for r in results[1:4]
                ]
                lines += ["", "🔎 Autres possibilités :"] + autres

            return "\n".join(lines)

        # Legacy style: classification.suggestions
        result = data.get("result", {})
        classification = result.get("classification", {})
        suggestions = classification.get("suggestions", [])
        if not suggestions:
            is_plant = result.get("is_plant", {}).get("binary", False)
            if not is_plant:
                return "❌ Aucune plante détectée dans l'image."
            return "⚠️ Plante détectée mais impossible de l'identifier précisément."

        # sort suggestions by probability descending just in case
        suggestions = sorted(suggestions, key=lambda s: float(s.get("probability", 0)), reverse=True)
        top = suggestions[0]
        nom_sci = top.get("name", "Inconnu")
        proba = round(float(top.get("probability", 0)) * 100, 1)
        details = top.get("details", {})
        noms_communs = details.get("common_names") or []
        nom_commun = ", ".join(noms_communs[:3]) if noms_communs else "Non disponible"
        taxo = details.get("taxonomy", {})
        famille = taxo.get("family", "—")
        genre = taxo.get("genus", "—")
        desc_obj = details.get("description", {})
        description = desc_obj.get("value", "") if isinstance(desc_obj, dict) else ""
        if description and len(description) > 300:
            description = description[:300] + "..."

        def soin(cle):
            obj = details.get(cle, {})
            return obj.get("value", "") if isinstance(obj, dict) else ""

        arrosage = soin("best_watering")
        lumiere = soin("best_light_condition")
        sol = soin("best_soil_type")

        lines = [
            f"🌿 Plante identifiée : {nom_sci} ({proba}% de confiance)",
            f"📛 Noms communs     : {nom_commun}",
            f"🔬 Famille          : {famille} | Genre : {genre}",
        ]
        if description:
            lines += ["", "📖 Description :", description]
        soins = []
        if arrosage:
            soins.append(f"  💧 Arrosage : {arrosage}")
        if lumiere:
            soins.append(f"  ☀️  Lumière  : {lumiere}")
        if sol:
            soins.append(f"  🪴 Sol      : {sol}")
        if soins:
            lines += ["", "🌱 Conseils d'entretien :"] + soins
        if len(suggestions) > 1:
            autres = [
                f"  - {s.get('name', 'Inconnu')} ({round(float(s.get('probability',0))*100, 1)}%)"
                for s in suggestions[1:4]
            ]
            lines += ["", "🔎 Autres possibilités :"] + autres
        return "\n".join(lines)
    except Exception as e:
        return f"Erreur de formatage : {e}\n\nRéponse brute :\n{json.dumps(data, indent=2)}"


def save_base64_image(image_b64: str, upload_dir: Path) -> Optional[str]:
    try:
        data = base64.b64decode(image_b64)
        filename = f"capture_{int(time.time() * 1000)}.jpg"
        path = upload_dir / filename
        with path.open("wb") as f:
            f.write(data)
        return str(path)
    except Exception:
        return None


def call_plantnet_api(image_b64: str) -> dict:
    """Call PlantNet identification API using a multipart upload.

    Returns parsed JSON on success. Raises RuntimeError with a clear
    message for known errors (401/403) and lets requests raise for others.
    """
    # Read url and key from environment (allow .env to have been loaded)
    url = os.environ.get("PLANTNET_API_URL", "").strip().strip('"')
    key = os.environ.get("PLANTNET_API_KEY", "").strip().strip('"')

    if not url:
        raise RuntimeError("PLANTNET_API_URL not configured")

    # prepare files payload from base64 image
    try:
        data = base64.b64decode(image_b64)
    except Exception:
        raise RuntimeError("Invalid image data")

    files = {"images": ("upload.jpg", data)}

    params = {}
    headers = {}
    if key:
        # many PlantNet setups accept api-key as query parameter
        params["api-key"] = key

    debug = os.environ.get("PLANTNET_DEBUG", "") == "1"
    if debug:
        print(f"[PLANTNET DEBUG] POST {url} params={params} headers={headers} filesize={len(data)}")

    try:
        resp = requests.post(url, params=params, headers=headers, files=files, timeout=20)
    except requests.exceptions.Timeout:
        raise RuntimeError("Timeout contacting PlantNet")
    except Exception as e:
        raise

    # debug logging
    if debug:
        print(f"[PLANTNET DEBUG] status={resp.status_code} body={resp.text[:2000]}")

    if resp.status_code == 401:
        raise RuntimeError("Clé API invalide")
    if resp.status_code == 403:
        raise RuntimeError("Accès refusé (IP ou restriction)")

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        # surface response text for troubleshooting
        raise RuntimeError(f"PlantNet HTTP {resp.status_code}: {resp.text}")

    try:
        return resp.json()
    except Exception:
        # return raw text when JSON parsing fails
        return {"text": resp.text}


def call_plant_api(image_b64: str, retries: int = 3, timeout: int = 20) -> dict:
    """Robust call to PlantNet-like API with retries and clear error mapping.

    Returns parsed JSON on success or a dict with key 'error' describing the problem.
    """
    url = os.environ.get("PLANTNET_API_URL", "").strip().strip('"')
    key = os.environ.get("PLANTNET_API_KEY", "").strip().strip('"')

    if not url:
        return {"error": "PLANTNET_API_URL not configured"}

    try:
        data = base64.b64decode(image_b64)
    except Exception:
        return {"error": "Invalid image data"}

    files = {"images": ("upload.jpg", data)}
    params = {}
    headers = {}
    if key:
        params["api-key"] = key

    attempt = 0
    last_exception = None
    while attempt < retries:
        attempt += 1
        try:
            resp = requests.post(url, params=params, headers=headers, files=files, timeout=timeout)
            print(f"[PLANT_API] attempt={attempt} STATUS: {resp.status_code}")
            print(f"[PLANT_API] RESPONSE: {resp.text[:2000]}")

            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {"text": resp.text}

            if resp.status_code == 401:
                return {"error": "Clé API invalide"}
            if resp.status_code == 403:
                return {"error": "Accès refusé (IP ou restriction API)"}
            if resp.status_code == 429:
                return {"error": "Trop de requêtes, réessaye plus tard"}
            if resp.status_code >= 500:
                # server-side error — may retry
                err = {"error": "Serveur API indisponible (502/503)"}
                # if not last attempt, sleep briefly then retry
                if attempt < retries:
                    time.sleep(1)
                    continue
                return err

            # other client errors
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}

        except requests.exceptions.Timeout:
            print(f"[PLANT_API] attempt={attempt} Timeout")
            last_exception = requests.exceptions.Timeout()
            if attempt < retries:
                time.sleep(1)
                continue
            return {"error": "Timeout API"}
        except requests.exceptions.ConnectionError as e:
            print(f"[PLANT_API] attempt={attempt} ConnectionError: {e}")
            last_exception = e
            if attempt < retries:
                time.sleep(1)
                continue
            return {"error": "Erreur connexion API"}
        except Exception as e:
            print(f"[PLANT_API] attempt={attempt} Exception: {e}")
            last_exception = e
            if attempt < retries:
                time.sleep(1)
                continue
            return {"error": f"Unexpected error: {e}"}

