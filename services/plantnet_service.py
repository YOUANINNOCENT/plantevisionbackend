import os
import time
import base64
from pathlib import Path
import json
from typing import Optional
from . import plantnet_api

UPLOAD_FILENAME_PREFIX = "upload_plantnet_"


def save_base64_image(image_b64: str, upload_dir: Path) -> str:
    """Decode base64 image and save into upload_dir. Returns str(path)."""
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    fname = f"{UPLOAD_FILENAME_PREFIX}{ts}.jpg"
    dest = upload_dir / fname
    # Accept both data:...;base64, and raw base64
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    data = base64.b64decode(image_b64)
    with dest.open("wb") as f:
        f.write(data)
    return str(dest)


def call_plantnet_api(image_b64: str, organs: Optional[list[str]] = None, lang: str = "fr") -> dict:
    """Save image and call PlantNet API via plantnet_api.identify_plant."""
    # save to temp file
    from pathlib import Path as _P
    tmp_dir = _P(__file__).resolve().parent.parent / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img_path = save_base64_image(image_b64, tmp_dir)
    # configurable timeout (seconds) via env
    try:
        timeout = int(os.getenv("PLANTNET_TIMEOUT", "12"))
    except Exception:
        timeout = 12

    try:
        res = plantnet_api.identify_plant([img_path], organs=organs, lang=lang, timeout=timeout)
        return res
    except Exception as e:
        return {"error": str(e)}


def format_result(data: dict) -> str:
    """Formatte la réponse PlantNet en texte lisible (simplifié)."""
    try:
        if not isinstance(data, dict):
            return json.dumps(data)
        results = data.get("results") or []
        if not results:
            return "Aucun résultat d'identification." 
        top = results[0]
        species = top.get("species") or {}
        sci = species.get("scientificNameWithoutAuthor") or species.get("scientificName", "Inconnu")
        common = ", ".join(species.get("commonNames", [])[:3]) or "—"
        score = top.get("score", 0)
        family = species.get("family", {}).get("scientificNameWithoutAuthor", "—")
        genus = species.get("genus", {}).get("scientificNameWithoutAuthor", "—")
        lines = [f"🌿 {sci} ({score*100:.1f}% de confiance)", f"📛 Noms communs: {common}", f"🔬 Famille: {family} | Genre: {genus}"]
        return "\n".join(lines)
    except Exception as e:
        return f"Erreur de formatage: {e}\n\nRéponse brute:\n{json.dumps(data, indent=2)}"
