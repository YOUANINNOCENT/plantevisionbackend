"""Service de génération d'images pour les plantes.

Stratégie :
  1) ModelsLab (text-to-image IA, configurable via MODELSLAB_API_KEY)
  2) Fallback Unsplash (recherche d'image existante via UNSPLASH_KEY)
  3) Erreur explicite si aucun fournisseur disponible

Toutes les fonctions retournent l'image encodée en base64 (sans le préfixe
data URI), pour que le backend puisse la renvoyer telle quelle au frontend.
"""

from __future__ import annotations

import base64
import os
import traceback
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Presets de style — appliqués au prompt avant l'appel à ModelsLab.
# ---------------------------------------------------------------------------
#
# Chaque preset contient :
#   - prefix : phrase à coller AVANT le prompt utilisateur (établit le sujet)
#   - suffix : phrase à coller APRÈS (qualité, technique, lumière)
#   - negative : négatifs supplémentaires propres au style (concaténés au negative
#                par défaut)
#
# Le preset par défaut "botanical_realistic" cible le rendu d'une plante isolée
# en photo studio claire, idéal pour identifier une espèce.
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "botanical_realistic": {
        "prefix": "Ultra-realistic botanical photography of",
        "suffix": (
            ", isolated against a clean white studio background, soft diffused "
            "natural light, sharp focus, fine leaf veins and petal details, "
            "professional macro lens, 8k, scientific reference quality"
        ),
        "negative": "cartoon, illustration, painting, drawing, low quality",
    },
    "botanical_illustration": {
        "prefix": "Vintage botanical illustration of",
        "suffix": (
            ", in the style of 19th-century scientific plant plates, hand-drawn "
            "ink lines, soft watercolor wash, cream paper background, labeled "
            "anatomical accuracy, detailed leaves and flowers"
        ),
        "negative": "photograph, 3d render, blurry, modern",
    },
    "watercolor": {
        "prefix": "Delicate watercolor painting of",
        "suffix": (
            ", soft pastel tones, flowing pigments, fine brush strokes, white "
            "watercolor paper texture, artistic and elegant"
        ),
        "negative": "photograph, harsh lines, digital, 3d render",
    },
    "oil_painting": {
        "prefix": "Classical oil painting of",
        "suffix": (
            ", in the style of a 17th-century Dutch still life, warm golden "
            "lighting, rich textured brushwork, dark background, museum quality"
        ),
        "negative": "photograph, modern, cartoon, blurry",
    },
    "pencil_sketch": {
        "prefix": "Detailed pencil sketch of",
        "suffix": (
            ", graphite on white paper, fine cross-hatching, soft shading, "
            "scientific botanical reference, monochrome"
        ),
        "negative": "color, photograph, painted",
    },
    "vintage_engraving": {
        "prefix": "Antique copperplate engraving of",
        "suffix": (
            ", black ink on aged parchment paper, intricate line work, "
            "Latin name labeled below, 18th-century scientific atlas style"
        ),
        "negative": "color, modern, photograph",
    },
    "studio_photo": {
        "prefix": "Professional studio photograph of",
        "suffix": (
            ", crisp focus, soft three-point lighting, neutral grey background, "
            "magazine quality, high resolution, true-to-life colors"
        ),
        "negative": "blurry, low light, cartoon",
    },
    "none": {
        "prefix": "",
        "suffix": "",
        "negative": "",
    },
}

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, watermark, text, logo, signature, nsfw, "
    "deformed, extra limbs, mutated, jpeg artifacts, cropped"
)


def _apply_style(prompt: str, style: Optional[str]) -> tuple[str, str]:
    """Renvoie (prompt_enrichi, negative_prompt_enrichi) selon le preset choisi."""
    key = (style or "").strip().lower()
    if key not in STYLE_PRESETS:
        key = (os.environ.get("MODELSLAB_DEFAULT_STYLE") or "botanical_realistic").lower()
    if key not in STYLE_PRESETS:
        key = "botanical_realistic"
    preset = STYLE_PRESETS[key]
    parts = [preset["prefix"], prompt.strip(), preset["suffix"]]
    full_prompt = " ".join(p for p in parts if p).strip()
    negatives = [DEFAULT_NEGATIVE_PROMPT, preset["negative"]]
    full_negative = ", ".join(n for n in negatives if n)
    return full_prompt, full_negative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_size(size: str) -> tuple[int, int]:
    """Parse "1024x1024" → (1024, 1024). Tombe sur 512x512 si format invalide."""
    try:
        w, h = size.lower().split("x", 1)
        return int(w), int(h)
    except Exception:
        return 512, 512


def _download_to_b64(url: str, timeout: int = 60) -> str:
    """Télécharge une URL d'image et renvoie le base64 (sans préfixe data:)."""
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return base64.b64encode(r.content).decode("ascii")


# ---------------------------------------------------------------------------
# Google Gemini (priorité 1 — génération IA native via gemini-2.5-flash-image)
# ---------------------------------------------------------------------------


def _generate_via_gemini(
    prompt: str,
    size: str,
    style: Optional[str] = None,
) -> Optional[str]:
    """Appelle l'API Gemini 2.5 Flash Image pour générer une image.

    Renvoie le base64 de l'image (sans préfixe data:), ou None si la clé n'est
    pas configurée. Lève RuntimeError sur erreur d'API explicite.

    Doc : https://ai.google.dev/gemini-api/docs/image-generation
    """
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        print("[image_service] GEMINI_API_KEY non configurée — skip")
        return None
    print(f"[image_service] GEMINI_API_KEY détectée ({len(api_key)} caractères)")

    # Liste de modèles à essayer dans l'ordre. Google renomme régulièrement
    # ses modèles donc on tente plusieurs candidats. Si GEMINI_IMAGE_MODEL est
    # défini dans .env, il passe en tête.
    forced = (os.environ.get("GEMINI_IMAGE_MODEL") or "").strip()
    candidate_models = [
        forced,
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-preview",
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.0-flash-exp",
        "imagen-3.0-generate-002",  # endpoint :predict, géré plus bas
    ]
    # Élimine doublons et entrées vides en gardant l'ordre
    seen = set()
    candidate_models = [
        m for m in candidate_models if m and not (m in seen or seen.add(m))
    ]

    # Applique le preset de style choisi (botanical_realistic par défaut).
    full_prompt, _negative = _apply_style(prompt, style)
    width, height = _parse_size(size)

    # Le modèle Gemini n'expose pas de paramètre width/height direct, mais on
    # peut influencer le format en l'indiquant dans le prompt (ratio carré, etc.).
    aspect_hint = ""
    if width == height:
        aspect_hint = " Square 1:1 aspect ratio."
    elif width > height:
        aspect_hint = " Wide 16:9 aspect ratio."
    else:
        aspect_hint = " Portrait 9:16 aspect ratio."

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }
    last_error: Optional[str] = None

    for model in candidate_models:
        is_imagen = model.startswith("imagen-")
        if is_imagen:
            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:predict"
            )
            payload = {
                "instances": [{"prompt": full_prompt + aspect_hint}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "1:1" if width == height else (
                        "16:9" if width > height else "9:16"
                    ),
                },
            }
        else:
            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent"
            )
            payload = {
                "contents": [{"parts": [{"text": full_prompt + aspect_hint}]}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                },
            }

        try:
            print(
                f"[image_service] Gemini : essai model={model} "
                f"size={width}x{height}"
            )
            resp = requests.post(api_url, headers=headers, json=payload, timeout=90)
            if resp.status_code == 404:
                # Modèle inconnu pour cette clé — on passe au suivant sans alerte
                last_error = f"{model}: 404 not found"
                continue
            if resp.status_code != 200:
                last_error = f"{model}: HTTP {resp.status_code}: {resp.text[:200]}"
                # 400 ou 403 → on essaie quand même les autres modèles
                continue
            data = resp.json()
        except requests.RequestException as e:
            last_error = f"{model}: erreur réseau {e}"
            continue
        except ValueError:
            last_error = f"{model}: réponse non-JSON"
            continue

        # ===== Parse réponse selon le type d'endpoint =====
        try:
            if is_imagen:
                # Format Imagen :predict → predictions[0].bytesBase64Encoded
                preds = data.get("predictions") or []
                if not preds:
                    last_error = f"{model}: pas de prédictions"
                    continue
                b64 = preds[0].get("bytesBase64Encoded")
                if b64:
                    print(
                        f"[image_service] Imagen ({model}) a renvoyé une image "
                        f"({len(b64)} chars base64)"
                    )
                    return b64
                last_error = f"{model}: pas de bytesBase64Encoded"
                continue

            # Format Gemini :generateContent → candidates[0].content.parts[].inlineData
            candidates = data.get("candidates") or []
            if not candidates:
                block = data.get("promptFeedback", {}).get("blockReason")
                if block:
                    raise RuntimeError(
                        f"Gemini a bloqué la requête (raison : {block}). "
                        "Reformule le prompt."
                    )
                last_error = f"{model}: pas de candidats"
                continue
            parts = (candidates[0].get("content") or {}).get("parts") or []
            for p in parts:
                inline = p.get("inlineData") or p.get("inline_data")
                if inline and isinstance(inline, dict):
                    mime = inline.get("mimeType") or inline.get("mime_type") or ""
                    b64 = inline.get("data") or ""
                    if mime.startswith("image/") and b64:
                        print(
                            f"[image_service] Gemini ({model}) a renvoyé une "
                            f"image ({mime}, {len(b64)} chars base64)"
                        )
                        return b64
            # Aucune image — peut-être que ce modèle renvoie juste du texte
            text_replies = [p.get("text", "") for p in parts if p.get("text")]
            if text_replies:
                last_error = (
                    f"{model}: a renvoyé du texte au lieu d'image "
                    f"({text_replies[0][:80]}...)"
                )
            else:
                last_error = f"{model}: aucune image dans la réponse"
            continue
        except RuntimeError:
            # Blocage safety → on n'essaie pas les autres modèles
            raise
        except Exception as e:
            last_error = f"{model}: {e}"
            continue

    # Tous les modèles ont échoué
    raise RuntimeError(
        f"Aucun modèle Gemini compatible avec ta clé. "
        f"Dernière erreur : {last_error}. "
        "Liste les modèles disponibles via "
        "https://generativelanguage.googleapis.com/v1beta/models?key=TA_CLE"
    )


# ---------------------------------------------------------------------------
# ModelsLab (priorité 2 — fallback)
# ---------------------------------------------------------------------------


def _generate_via_modelslab(
    prompt: str,
    size: str,
    style: Optional[str] = None,
) -> Optional[str]:
    """Appelle l'API realtime text2img de ModelsLab.

    Renvoie le base64 de l'image, ou None si le fournisseur n'est pas configuré.
    Lève RuntimeError en cas d'erreur d'API explicite (clé invalide, quota, etc.).

    Le preset `style` enrichit le prompt avec un prefix/suffix typés et un
    negative_prompt adapté. Si non fourni, on utilise MODELSLAB_DEFAULT_STYLE.
    """
    api_key = (os.environ.get("MODELSLAB_API_KEY") or "").strip()
    if not api_key:
        print(
            "[image_service] MODELSLAB_API_KEY est vide — "
            "vérifie que la ligne est non-commentée dans backend/.env "
            "et que le backend a été redémarré après l'édition."
        )
        return None
    print(f"[image_service] MODELSLAB_API_KEY détectée ({len(api_key)} caractères)")

    api_url = (
        os.environ.get("MODELSLAB_API_URL")
        or "https://modelslab.com/api/v6/realtime/text2img"
    ).strip()

    width, height = _parse_size(size)

    # Applique le preset de style choisi (botanical_realistic par défaut)
    full_prompt, negative_prompt = _apply_style(prompt, style)

    payload = {
        "key": api_key,
        "prompt": full_prompt,
        "negative_prompt": negative_prompt,
        "width": str(width),
        "height": str(height),
        "samples": "1",
        "safety_checker": False,
        "enhance_prompt": True,
        "seed": None,
        "base64": False,
        "webhook": None,
        "track_id": None,
    }
    # Modèle Stable Diffusion à utiliser, si configuré
    model_id = (os.environ.get("MODELSLAB_MODEL_ID") or "").strip()
    if model_id:
        payload["model_id"] = model_id

    try:
        print(
            f"[image_service] ModelsLab : style={style or os.environ.get('MODELSLAB_DEFAULT_STYLE', 'botanical_realistic')} "
            f"size={width}x{height} model={model_id or 'default'}"
        )
        print(f"[image_service] prompt enrichi : {full_prompt[:120]}...")
        resp = requests.post(api_url, json=payload, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(
                f"ModelsLab HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"ModelsLab : erreur réseau : {e}")
    except ValueError:
        raise RuntimeError(
            f"ModelsLab : réponse non-JSON : {resp.text[:200]}"
        )

    status = (data.get("status") or "").lower()
    # Cas d'erreur explicite
    if status == "error":
        msg = data.get("message") or data.get("messege") or str(data)
        raise RuntimeError(f"ModelsLab a refusé la requête : {msg}")

    # Récupère l'URL de l'image générée
    output = data.get("output") or []
    if not output and data.get("future_links"):
        output = data.get("future_links") or []

    image_url: Optional[str] = None
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, str):
            image_url = first
        elif isinstance(first, dict):
            image_url = first.get("url") or first.get("image")

    if not image_url:
        raise RuntimeError(
            f"ModelsLab : aucune URL d'image dans la réponse : {data}"
        )

    print(f"[image_service] ModelsLab a renvoyé : {image_url[:80]}...")
    return _download_to_b64(image_url)


# ---------------------------------------------------------------------------
# Pollinations.ai (priorité 2 — fallback IA gratuit, pas de clé)
# ---------------------------------------------------------------------------


def _generate_via_pollinations(prompt: str, size: str, style: Optional[str] = None) -> Optional[str]:
    """Génère une image via Pollinations.ai (gratuit, sans clé API).

    Renvoie le base64 de l'image. Pollinations renvoie directement les bytes
    de l'image PNG en réponse à une simple requête GET.
    """
    from urllib.parse import quote

    # Applique le même preset de style que ModelsLab pour la cohérence
    full_prompt, _ = _apply_style(prompt, style)
    width, height = _parse_size(size)

    # Pollinations.ai endpoint : /prompt/{prompt_encoded}
    encoded = quote(full_prompt[:500])  # limite raisonnable pour l'URL
    # Paramètres : nologo=true enlève le watermark, model=flux pour qualité
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&model=flux&safe=true"
    )
    # Pollinations gratuit limite à 1 requête concurrente par IP, on retry
    # sur 429 avec un backoff progressif.
    import time

    last_status = 0
    last_text = ""
    for attempt in range(1, 4):  # 3 essais max
        try:
            print(
                f"[image_service] Pollinations.ai : génération {width}x{height} "
                f"(essai {attempt}/3)"
            )
            r = requests.get(url, timeout=90)
            last_status = r.status_code
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                if not ct.startswith("image/"):
                    raise RuntimeError(
                        f"Pollinations a renvoyé du non-image (content-type={ct})"
                    )
                print(
                    f"[image_service] Pollinations a renvoyé "
                    f"{len(r.content)} octets"
                )
                return base64.b64encode(r.content).decode("ascii")
            if r.status_code == 429:
                # Queue saturée — on attend un peu plus à chaque essai
                wait = 3 * attempt
                last_text = r.text[:120]
                print(
                    f"[image_service] Pollinations 429 (queue saturée), "
                    f"retry dans {wait}s"
                )
                time.sleep(wait)
                continue
            # Autre erreur HTTP : on n'insiste pas
            raise RuntimeError(
                f"Pollinations HTTP {r.status_code}: {r.text[:200]}"
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Pollinations : erreur réseau : {e}")

    raise RuntimeError(
        f"Pollinations a refusé après 3 essais (HTTP {last_status}: {last_text})"
    )


# ---------------------------------------------------------------------------
# Unsplash (priorité 3 — fallback photo existante)
# ---------------------------------------------------------------------------


def _generate_via_unsplash(prompt: str) -> Optional[str]:
    unsplash_key = (os.environ.get("UNSPLASH_KEY") or "").strip()
    if not unsplash_key:
        return None
    try:
        url = "https://api.unsplash.com/photos/random"
        params = {"query": prompt, "orientation": "portrait"}
        headers = {
            "Accept-Version": "v1",
            "Authorization": f"Client-ID {unsplash_key}",
        }
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        urls = j.get("urls") or {}
        for key in ("raw", "full", "regular", "small"):
            if urls.get(key):
                return _download_to_b64(urls[key])
        raise RuntimeError(f"Aucune URL image dans la réponse Unsplash : {j}")
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Erreur Unsplash : {e}")


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------


def generate_image(
    prompt: str,
    size: Optional[str] = None,
    style: Optional[str] = None,
) -> str:
    """Génère une image pour `prompt` et renvoie le base64 (sans data URI).

    Paramètres :
      - prompt : description de la plante/scène à générer.
      - size : "WxH" (ex. "768x768"). Défaut = MODELSLAB_DEFAULT_SIZE ou 768x768.
      - style : preset parmi STYLE_PRESETS.keys(). Défaut = MODELSLAB_DEFAULT_STYLE.

    Ordre des fournisseurs : ModelsLab → Unsplash → erreur.
    """
    # Taille par défaut depuis .env
    if not size:
        size = (os.environ.get("MODELSLAB_DEFAULT_SIZE") or "768x768").strip()

    # 1) Gemini (génération IA native Google, fournisseur principal)
    try:
        result = _generate_via_gemini(prompt, size, style=style)
        if result:
            return result
    except Exception as e:
        print(f"[image_service] Gemini indisponible, fallback ModelsLab : {e}")

    # 2) ModelsLab (génération IA freemium)
    try:
        result = _generate_via_modelslab(prompt, size, style=style)
        if result:
            return result
    except Exception as e:
        print(f"[image_service] ModelsLab indisponible, fallback Pollinations : {e}")

    # 3) Pollinations.ai (génération IA gratuite, sans clé)
    try:
        result = _generate_via_pollinations(prompt, size, style=style)
        if result:
            return result
    except Exception as e:
        print(f"[image_service] Pollinations a échoué, fallback Unsplash : {e}")

    # 4) Unsplash (recherche photo existante)
    try:
        result = _generate_via_unsplash(prompt)
        if result:
            return result
    except Exception as e:
        print(f"[image_service] Unsplash a aussi échoué : {e}")

    # 5) Aucun fournisseur n'a fonctionné
    raise RuntimeError(
        "Aucun fournisseur d'images n'a répondu (Gemini, ModelsLab, "
        "Pollinations, Unsplash). Vérifie ta connexion Internet ou les logs backend."
    )


def list_styles() -> list[str]:
    """Liste les presets de style disponibles (utile pour l'UI)."""
    return list(STYLE_PRESETS.keys())
