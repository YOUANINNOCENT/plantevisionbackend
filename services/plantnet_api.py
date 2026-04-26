"""
Adaptation locale de plantnet_api.py dans le dossier `backend/services`.
Utilise la variable d'environnement `PLANTNET_API_KEY`.
"""

import requests
import json
import logging
from pathlib import Path
import os

_raw_base = os.getenv("PLANTNET_API_URL", "https://my-api.plantnet.org/v2/identify/all")
# If user provided a root like https://my-api.plantnet.org, ensure we use the v2/identify base
if 'v2/identify' not in _raw_base:
    _raw_base = _raw_base.rstrip('/') + '/v2/identify'

logger = logging.getLogger(__name__)

# The PlantNet /v2/identify endpoint REQUIRES a project name (e.g. 'all',
# 'weurope', 'canada'...). If the URL stops at /v2/identify, append '/all'
# which identifies worldwide species.
BASE_URL = _raw_base.rstrip('/')
if BASE_URL.endswith('/v2/identify'):
    BASE_URL = BASE_URL + '/all'
API_KEY = os.getenv("PLANTNET_API_KEY", "2b10M02Imb8OZFWe7hvK9grqee")


def identify_plant(image_paths: list[str], organs: list[str] | None = None, lang: str = "fr", timeout: int = 10) -> dict:
    if organs is None:
        organs = ["auto"] * len(image_paths)

    if len(organs) != len(image_paths):
        raise ValueError("Le nombre d'organes doit correspondre au nombre d'images.")

    params = {
        "api-key": API_KEY,
        "lang": lang,
        "include-related-images": True,
        # Force the API to return its best guess even if it would normally reject
        "no-reject": True,
    }

    files = []
    opened_files = []

    try:
        for path, organ in zip(image_paths, organs):
            if isinstance(path, str) and (path.startswith("http://") or path.startswith("https://")):
                params.setdefault("images", []).append(path)
                params.setdefault("organs", []).append(organ)
            else:
                f = open(path, "rb")
                opened_files.append(f)
                files.append(("images", (Path(path).name, f, "image/jpeg")))
                files.append(("organs", (None, organ)))

        # Use the base identify endpoint (public API uses /v2/identify)
        url = f"{BASE_URL}"
        # Log the URL and params for debugging
        try:
            logger.debug(f"PlantNet request URL: {url}")
            logger.debug("PlantNet params: %s", params)
        except Exception:
            pass

        try:
            resp = requests.post(url, params=params, files=files if files else None, timeout=timeout)
            # If we get a 404 from a custom instance, try the public API as a fallback
            if resp.status_code == 404:
                # avoid looping if BASE_URL already points to api.plantnet.org
                if "api.plantnet.org" not in BASE_URL:
                    fallback = "https://api.plantnet.org/v2/identify"
                    try:
                        logger.warning("Received 404 from %s, retrying with public PlantNet API: %s", url, fallback)
                        resp2 = requests.post(fallback, params=params, files=files if files else None, timeout=timeout)
                        try:
                            resp2.raise_for_status()
                        except requests.HTTPError:
                            return {"error": f"{resp2.status_code} {resp2.text}", "url": fallback}
                        try:
                            return resp2.json()
                        except ValueError:
                            return {"error": "Invalid JSON response from fallback", "text": resp2.text, "url": fallback}
                    except Exception as e:
                        return {"error": str(e), "url": fallback}
                # if BASE_URL already is the public API, return the 404 info
                return {"error": f"{resp.status_code} {resp.text}", "url": url}

            try:
                resp.raise_for_status()
            except requests.HTTPError:
                # Return status and body for debugging
                return {"error": f"{resp.status_code} {resp.text}", "url": url}
            try:
                return resp.json()
            except ValueError:
                return {"error": "Invalid JSON response", "text": resp.text, "url": url}
        except Exception as e:
            logger.exception("Network error when calling PlantNet %s", url)
            return {"error": str(e), "url": url}

    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass


def display_results(results: dict, top_n: int = 3):
    if "results" not in results:
        logger.info("Aucun résultat trouvé.")
        logger.debug(json.dumps(results, indent=2, ensure_ascii=False))
        return

    logger.info("🌿 Score de correspondance globale : %s", results.get('bestMatch', 'N/A'))
    logger.info("Top %d espèces identifiées :", top_n)
    logger.info("%s", "-" * 50)

    for i, result in enumerate(results["results"][:top_n], 1):
        species = result["species"]
        score = result.get("score", 0)

        scientific_name = species.get("scientificNameWithoutAuthor", "Inconnu")
        common_names = species.get("commonNames", [])
        family = species.get("family", {}).get("scientificNameWithoutAuthor", "Inconnue")
        genus = species.get("genus", {}).get("scientificNameWithoutAuthor", "Inconnu")

        logger.info("#%d — %s", i, scientific_name)
        logger.info("   Confiance   : %.1f%%", score * 100)
        logger.info("   Famille     : %s", family)
        logger.info("   Genre       : %s", genus)
        if common_names:
            logger.info("   Noms communs: %s", ', '.join(common_names[:3]))
