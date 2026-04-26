import asyncio
import json
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import cast, List, Optional

from fastapi import FastAPI, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import func

import sys
from pathlib import Path

# Add backend folder and plante (parent) folder to path
# This allows imports to work whether run from backend/ or from plante/
backend_dir = Path(__file__).parent
plante_dir = backend_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(plante_dir))

# Charge le fichier .env (DATABASE_URL, SMTP_*, PLANTNET_API_*, etc.) avant
# tout import qui pourrait lire ces variables. python-dotenv est dépendance
# transitive d'uvicorn[standard] donc déjà disponible.
try:
    from dotenv import load_dotenv
    _env_path = backend_dir / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=False)
        print(f"[startup] .env chargé depuis {_env_path}")
except Exception as _env_err:
    print(f"[startup] python-dotenv non disponible ({_env_err}) — .env non chargé")

from services import db_service, plant_service, ai_service, image_service, plantnet_service

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# =========================
# 🔐 AUTH HELPERS
# =========================
import hashlib
import hmac
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash le mot de passe avec PBKDF2-HMAC-SHA256. Format stocké: pbkdf2_sha256$iter$salt_hex$hash_hex."""
    if salt is None:
        salt = secrets.token_bytes(16)
    iterations = 120_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def _send_reset_email(to_email: str, code: str, full_name: Optional[str]) -> bool:
    """Envoie le code de réinitialisation par email via SMTP.

    Renvoie True si l'envoi a réussi. Si SMTP_USER n'est pas configuré dans .env,
    log le code dans la console et renvoie False (pas d'erreur — fallback dev).
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    mail_from = os.getenv("SMTP_FROM", smtp_user) or smtp_user
    from_name = os.getenv("SMTP_FROM_NAME", "Vision — Botaniste Digital")

    if not smtp_user or not smtp_password:
        print(
            f"[forgot_password] SMTP non configuré — code pour {to_email} : {code} "
            f"(ajoute SMTP_USER et SMTP_PASSWORD dans backend/.env pour activer l'envoi)"
        )
        return False

    name_part = (full_name or to_email).split("@")[0]
    subject = "Réinitialisation de votre mot de passe Vision"
    text_body = (
        f"Bonjour {name_part},\n\n"
        f"Tu as demandé à réinitialiser ton mot de passe Vision.\n\n"
        f"Ton code de vérification est :\n\n"
        f"    {code}\n\n"
        f"Ce code expire dans 30 minutes. Saisis-le dans l'application pour "
        f"définir un nouveau mot de passe.\n\n"
        f"Si tu n'es pas à l'origine de cette demande, ignore simplement cet email — "
        f"ton mot de passe actuel reste valable.\n\n"
        f"— L'équipe Vision"
    )
    html_body = f"""\
<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#fbfbe2;font-family:Inter,Arial,sans-serif;color:#1b1d0e;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fbfbe2;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="520" cellspacing="0" cellpadding="0"
             style="background:#f5f5dc;border-radius:24px;overflow:hidden;max-width:520px;">
        <tr><td style="padding:32px 32px 16px 32px;">
          <p style="margin:0 0 8px 0;font-weight:800;letter-spacing:4px;color:#0d631b;">VISION</p>
          <h1 style="margin:8px 0 16px 0;font-family:Manrope,Arial,sans-serif;font-size:26px;color:#1b1d0e;">
            Réinitialisation du mot de passe
          </h1>
          <p style="margin:0 0 24px 0;color:#40493d;line-height:1.55;">
            Bonjour <b>{name_part}</b>,<br/>
            Saisis le code ci-dessous dans l'application pour choisir un nouveau mot de passe.
          </p>
          <div style="background:#eaead1;border-radius:14px;padding:24px;text-align:center;margin:0 0 20px 0;">
            <span style="font-family:Manrope,Arial,sans-serif;font-size:36px;font-weight:800;letter-spacing:12px;color:#0d631b;">
              {code}
            </span>
          </div>
          <p style="margin:0 0 8px 0;font-size:13px;color:#576251;">
            Ce code expire dans <b>30 minutes</b>.
          </p>
          <p style="margin:24px 0 0 0;font-size:12px;color:#707a6c;">
            Si tu n'es pas à l'origine de cette demande, ignore cet email — ton mot de passe actuel reste valable.
          </p>
        </td></tr>
        <tr><td style="padding:16px 32px 32px 32px;border-top:1px solid #bfcaba;">
          <p style="margin:0;font-size:11px;color:#707a6c;letter-spacing:1.5px;">
            DIGITAL BOTANIST — EDITION 2026
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{mail_from}>"
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"[forgot_password] Email de réinitialisation envoyé à {to_email}")
        return True
    except Exception as e:
        traceback.print_exc()
        print(f"[forgot_password] Échec envoi SMTP à {to_email} : {e}")
        return False


def _verify_password(password: str, stored: str) -> bool:
    """Vérifie qu'un mot de passe correspond au hash stocké."""
    try:
        if not stored or "$" not in stored:
            return False
        parts = stored.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
async def auth_register(payload: RegisterRequest = Body(...)):
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    full_name = (payload.full_name or "").strip() or None

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide")
    if len(password) < 6:
        raise HTTPException(
            status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères"
        )

    # Vérifie qu'aucun utilisateur n'existe déjà avec cet email
    existing = db_service.get_user_by_email(email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")

    hashed = _hash_password(password)
    try:
        user = db_service.create_user(
            email=email, full_name=full_name, hashed_password=hashed
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création: {e}")

    return {
        "status": "ok",
        "user": {
            "id": _to_int(getattr(user, "id")),
            "email": user.email,
            "full_name": user.full_name,
        },
    }


@app.post("/auth/login")
async def auth_login(payload: LoginRequest = Body(...)):
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email et mot de passe requis")

    user = db_service.get_user_by_email(email)
    # Erreur spécifique : email inconnu
    if user is None:
        raise HTTPException(status_code=404, detail="Email incorrect")

    stored = getattr(user, "hashed_password", None) or ""
    if not _verify_password(password, stored):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")

    return {
        "status": "ok",
        "user": {
            "id": _to_int(getattr(user, "id")),
            "email": user.email,
            "full_name": user.full_name,
        },
    }


@app.on_event("startup")
async def _run_startup_migrations():
    """Au démarrage d'uvicorn : s'assurer que les tables et les colonnes récentes existent.

    Quand le backend est lancé via `python -m uvicorn main:app` (pas via
    `run_backend.ps1`), la fonction `init_db()` n'est pas appelée sans cela,
    et les colonnes latitude/longitude/location_label ajoutées récemment
    manquent dans la base SQLite existante — ce qui fait échouer les INSERT
    et les SELECT sur analyses.
    """
    try:
        from models import init_db
        init_db()
        print("[startup] init_db + migration colonnes OK")
    except Exception as e:
        traceback.print_exc()
        print(f"[startup] init_db a échoué : {e}")


@app.get("/admin/ai_info")
async def ai_info():
    try:
        from services import config as svc_config

        # Consider an OpenAI/Gemini key present either in process config or in env
        has_key = bool(getattr(svc_config, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY"))
        return {"ai_mode": svc_config.ai_mode, "has_openai_key": has_key}
    except Exception:
        return {"ai_mode": "unknown", "has_openai_key": False}


class AiModeBody(BaseModel):
    mode: str


@app.post("/admin/ai_mode")
async def set_ai_mode(body: AiModeBody):
    from services import config as svc_config

    mode = (body.mode or "").strip().lower()
    if mode not in ("auto", "local", "remote"):
        raise HTTPException(status_code=400, detail="mode must be one of: auto, local, remote")
    svc_config.ai_mode = mode
    return {"ai_mode": svc_config.ai_mode}


class AiKeyBody(BaseModel):
    key: str


@app.post("/admin/openai_key")
async def set_openai_key(body: AiKeyBody):
    """Set an OpenAI key in memory for the running process (dev only).

    WARNING: this stores the key in process memory only. Do not use in
    production without proper security/ACL.
    """
    from services import config as svc_config

    key = (body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    svc_config.openai_api_key = key
    # also set process environment so child calls and reloads can see it
    try:
        os.environ["OPENAI_API_KEY"] = key
    except Exception:
        pass
    return {"status": "ok", "stored": bool(svc_config.openai_api_key)}


class UnsplashKeyBody(BaseModel):
    key: str


@app.post("/admin/unsplash_key")
async def set_unsplash_key(body: UnsplashKeyBody):
    """Store an Unsplash API key in memory for testing (dev only)."""
    from services import config as svc_config

    key = (body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    # store in svc_config and env to be visible to other parts
    try:
        svc_config.unsplash_key = key
    except Exception:
        pass
    try:
        os.environ["UNSPLASH_KEY"] = key
    except Exception:
        pass
    return {"status": "ok", "stored": True}


# Plant.id integration removed — admin endpoint deleted.



# =========================
# ✅ ROUTE TEST
# =========================
@app.get("/health")
async def health():
    return {"status": "ok"}


# =========================
# 🔧 UTILITAIRE
# =========================
def _analysis_to_dict(a):
    # Rétrocompat : le front lit 'plant_id' comme un nom de plante depuis longtemps.
    # On renvoie plant_name dedans pour ne rien casser, en plus du vrai plant_name.
    pname = getattr(a, "plant_name", None)
    return {
        "id": a.id,
        "user_id": a.user_id,
        "plant_id": pname if pname is not None else a.plant_id,
        "plant_name": pname,
        "category": getattr(a, "category", None),
        "image_path": str(a.image_path) if getattr(a, "image_path", None) else None,
        "result": a.result,
        "latitude": getattr(a, "latitude", None),
        "longitude": getattr(a, "longitude", None),
        "location_label": getattr(a, "location_label", None),
        "created_at": a.created_at.isoformat()
        if getattr(a, "created_at", None)
        else None,
    }


def _to_int(x):
    """Robustly convert an ORM id-like value to int for JSON/DB calls.

    This tries to return an int when possible and falls back to str->int.
    It's defensive against static type checkers that may view ORM attributes
    as Column[...] objects.
    """
    try:
        if isinstance(x, int):
            return x
        return int(x)
    except Exception:
        try:
            return int(str(x))
        except Exception:
            # give up and return 0 as a safe fallback
            return 0


# =========================
# 📤 UPLOAD IMAGE
# =========================
@app.post("/upload")
async def upload_image(file: UploadFile = File(...), user_id: int = Form(...)):

    # Some UploadFile implementations may have no content_type set
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted")

    # Ensure filename is a string (UploadFile.filename can be None in some types)
    filename = file.filename or f"upload_{int(time.time() * 1000)}.jpg"
    dest = UPLOAD_DIR / filename

    i = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{dest.stem}_{i}{dest.suffix}"
        i += 1

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    analysis = db_service.create_analysis(
        user_id=user_id, image_path=str(dest), plant_id=None, result=None
    )

    return {"status": "ok", "analysis": _analysis_to_dict(analysis)}


# =========================
# 📊 LISTE ANALYSES
# =========================
# IMPORTANT: /analyses/locations doit être déclarée AVANT /analyses/{user_id}
# sinon FastAPI essaie de parser "locations" comme user_id:int et renvoie 422.
@app.get("/analyses/locations")
async def analyses_locations(limit: int = 50, user_id: Optional[int] = None):
    """Renvoie les N derniers scans géolocalisés.

    Si user_id est fourni, ne renvoie que les scans de cet utilisateur.
    Sinon (compatibilité), renvoie tous les scans géolocalisés.
    """
    try:
        items = db_service.list_recent_locations(limit=limit, user_id=user_id)
        return {
            "items": [
                {
                    "id": _to_int(getattr(a, 'id')),
                    # plant_id renvoie ici le nom (rétrocompat Flutter), plant_name aussi
                    "plant_id": getattr(a, 'plant_name', None) or a.plant_id,
                    "plant_name": getattr(a, 'plant_name', None),
                    "latitude": getattr(a, 'latitude', None),
                    "longitude": getattr(a, 'longitude', None),
                    "location_label": getattr(a, 'location_label', None),
                    "created_at": a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
                }
                for a in items
            ]
        }
    except Exception as e:
        traceback.print_exc()
        return {"items": [], "error": str(e)}


@app.get("/analyses/{user_id}")
async def list_analyses(user_id: int):
    analyses = db_service.list_analyses_for_user(user_id=user_id)
    return {"results": [_analysis_to_dict(a) for a in analyses]}


# =========================
# 👤 USERS
# =========================


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


@app.put("/users/{user_id}")
async def update_user_endpoint(user_id: int, payload: UserUpdate = Body(...)):
    u = db_service.get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    fields: dict = {}
    if payload.full_name is not None:
        fields["full_name"] = payload.full_name.strip() or None
    if payload.email is not None:
        e = payload.email.strip().lower()
        if e and "@" not in e:
            raise HTTPException(status_code=400, detail="Email invalide")
        # Vérifie qu'aucun autre utilisateur n'a déjà cet email
        if e:
            other = db_service.get_user_by_email(e)
            if other is not None and _to_int(getattr(other, "id")) != user_id:
                raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
            fields["email"] = e
    # phone is not persisted (pas de colonne) — on l'ignore silencieusement
    try:
        updated = db_service.update_user(user_id, **fields)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "status": "ok",
        "user": {
            "id": _to_int(getattr(updated, "id")),
            "email": updated.email,
            "full_name": updated.full_name,
        },
    }


@app.delete("/users/{user_id}")
async def delete_user_endpoint(user_id: int):
    ok = db_service.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


# Durée de validité du code de réinitialisation
RESET_TOKEN_TTL = timedelta(minutes=30)


@app.post("/auth/forgot_password")
async def forgot_password(payload: ForgotPasswordRequest = Body(...)):
    """Génère un code de réinitialisation à 6 chiffres, le stocke en base
    avec une expiration de 30 minutes, et l'envoie par email.

    Pour des raisons de sécurité (éviter l'énumération d'emails), on renvoie
    toujours le même message quel que soit le résultat — un attaquant ne peut
    pas savoir si l'email existe.
    """
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide")

    user = db_service.get_user_by_email(email)
    if user is not None:
        # 6 chiffres aléatoires (100000-999999), facile à taper depuis l'email
        code = f"{secrets.randbelow(900000) + 100000}"
        expires = datetime.now(timezone.utc) + RESET_TOKEN_TTL
        # Stocke en base
        try:
            from models import get_session, User
            with get_session() as session:
                u = session.get(User, _to_int(getattr(user, "id")))
                if u is not None:
                    u.reset_token = code
                    u.reset_token_expires = expires
                    session.add(u)
                    session.flush()
        except Exception:
            traceback.print_exc()
        # Envoi de l'email (best-effort, pas bloquant si SMTP non configuré)
        await asyncio.to_thread(
            _send_reset_email, email, code, getattr(user, "full_name", None)
        )

    return {
        "status": "ok",
        "message": (
            "Si un compte existe avec cet email, un code de réinitialisation "
            "a été envoyé."
        ),
    }


@app.post("/auth/reset_password")
async def reset_password(payload: ResetPasswordRequest = Body(...)):
    """Définit un nouveau mot de passe à partir du code reçu par email.

    Vérifie : 1) le code correspond à celui stocké, 2) il n'est pas expiré,
    3) le nouveau mot de passe respecte la longueur minimale.
    Le code est consommé (effacé) après usage.
    """
    email = (payload.email or "").strip().lower()
    code = (payload.code or "").strip()
    new_password = payload.new_password or ""

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide")
    if not code:
        raise HTTPException(status_code=400, detail="Code de vérification requis")
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Le mot de passe doit contenir au moins 6 caractères",
        )

    try:
        from models import get_session, User
        with get_session() as session:
            u = session.query(User).filter(User.email == email).first()
            if u is None:
                # Anti-énumération : message vague et non spécifique
                raise HTTPException(
                    status_code=400,
                    detail="Code invalide ou expiré",
                )
            stored_code = getattr(u, "reset_token", None)
            expires = getattr(u, "reset_token_expires", None)
            if not stored_code or stored_code != code:
                raise HTTPException(
                    status_code=400,
                    detail="Code invalide ou expiré",
                )
            # Vérifie expiration. Les datetimes en base peuvent être naives
            # (sans tz info) selon le driver — on les considère UTC.
            if expires is not None:
                exp_aware = expires
                if exp_aware.tzinfo is None:
                    exp_aware = exp_aware.replace(tzinfo=timezone.utc)
                if exp_aware < datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=400,
                        detail="Code expiré, demande un nouveau code",
                    )
            # Tout OK : applique le nouveau mot de passe et consomme le code
            u.hashed_password = _hash_password(new_password)
            u.reset_token = None
            u.reset_token_expires = None
            session.add(u)
            session.flush()
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "message": "Mot de passe mis à jour"}


@app.post("/users/{user_id}/change_password")
async def change_password(user_id: int, payload: ChangePasswordRequest = Body(...)):
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Le nouveau mot de passe doit contenir au moins 6 caractères",
        )
    u = db_service.get_user(user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    stored = getattr(u, "hashed_password", None) or ""
    if not _verify_password(payload.current_password, stored):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    new_hash = _hash_password(payload.new_password)
    try:
        db_service.update_user(user_id, hashed_password=new_hash)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}


@app.get("/users/{user_id}")
async def get_user_endpoint(user_id: int):
    u = db_service.get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    # basic stats
    analyses = db_service.list_analyses_for_user(user_id=user_id)
    scans_total = len(analyses)
    # placeholder for rare plants / precision — compute basic values if possible
    rare_plants = 0
    try:
        plant_ids = {a.plant_id for a in analyses if getattr(a, 'plant_id', None)}
        rare_plants = len(plant_ids)
    except Exception:
        rare_plants = 0

    return {
        "id": _to_int(getattr(u, 'id')),
        "email": getattr(u, 'email', None),
        "full_name": getattr(u, 'full_name', None),
        "is_active": getattr(u, 'is_active', True),
        "scans_total": scans_total,
        "rare_plants": rare_plants,
        "is_premium": False,
    }


# =========================
# 🖼️ IMAGE ANALYSE
# =========================
@app.get("/analyses/{analysis_id}/image")
async def get_analysis_image(analysis_id: int):
    analysis = db_service.get_analysis_by_id(analysis_id)

    if not analysis:
        raise HTTPException(status_code=404, detail="Not found")

    image_path = getattr(analysis, "image_path", None)
    if not image_path:
        raise HTTPException(status_code=404, detail="No image for this analysis")

    # static type checkers see SQLAlchemy Columns as Column[str]; cast to str for FileResponse
    path_str = cast(str, image_path)
    return FileResponse(path_str)


# =========================
# ❌ DELETE ANALYSE
# =========================
@app.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: int):
    db_service.delete_analysis(analysis_id)
    return {"status": "deleted"}


class AnalysisPatch(BaseModel):
    category: Optional[str] = None
    plant_name: Optional[str] = None


@app.patch("/analyses/{analysis_id}")
async def patch_analysis(analysis_id: int, payload: AnalysisPatch = Body(...)):
    """Mettre à jour certaines colonnes d'une analyse (utilisé pour pousser
    la catégorie déduite par Groq côté client)."""
    try:
        from models import get_session, Analysis
        with get_session() as session:
            a = session.get(Analysis, analysis_id)
            if a is None:
                raise HTTPException(status_code=404, detail="Analyse introuvable")
            if payload.category is not None:
                cat = payload.category.strip().lower()
                # Normalise accents pour rester cohérent
                cat = (
                    cat.replace('é', 'e')
                    .replace('è', 'e')
                    .replace('ê', 'e')
                )
                # Mappe les variantes vers les 4 valeurs canoniques
                if cat in ('comestible', 'comestibles'):
                    a.category = 'comestible'
                elif cat in ('medicinale', 'medicinal', 'medicinales'):
                    a.category = 'medicinale'
                elif cat in ('toxique', 'toxiques'):
                    a.category = 'toxique'
                else:
                    a.category = 'inconnu'
            if payload.plant_name is not None:
                a.plant_name = payload.plant_name.strip() or None
            session.add(a)
            session.flush()
            return {"status": "ok", "analysis": _analysis_to_dict(a)}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# 🤖 IDENTIFICATION PLANTE
# =========================
@app.post("/identify")
async def identify(images: List[str] = Body(...), user_id: Optional[int] = Body(0)):

    if not images:
        raise HTTPException(status_code=400, detail="No images")

    image_b64 = images[0]

    # Sauvegarde image
    image_path = plant_service.save_base64_image(image_b64, UPLOAD_DIR)

    # Appel API externe (PlantNet-like) via wrapper with retries
    data = plant_service.call_plant_api(image_b64)
    # If call_plant_api returns an error dict, map to HTTP statuses
    if isinstance(data, dict) and data.get("error"):
        err = data.get("error", "Erreur API")
        if "Clé API invalide" in err:
            raise HTTPException(status_code=401, detail=err)
        if "Accès refusé" in err:
            raise HTTPException(status_code=403, detail=err)
        if "Trop de requêtes" in err:
            raise HTTPException(status_code=429, detail=err)
        if "Timeout" in err:
            raise HTTPException(status_code=504, detail="Le serveur ne répond pas (timeout)")
        if "Serveur API indisponible" in err:
            raise HTTPException(status_code=502, detail=err)
        # default
        raise HTTPException(status_code=502, detail=err)

    # Format result if possible (fallback to raw JSON)
    try:
        result_text = plant_service.format_result(data)
    except Exception:
        result_text = json.dumps(data)

    # Extraire nom plante
    plant_name = None
    try:
        plant_name = data["result"]["classification"]["suggestions"][0]["name"]
    except Exception:
        # ignore parsing errors and keep plant_name as None
        pass

    # Sauvegarde DB
    uid: int = user_id if user_id is not None else 0
    analysis = db_service.create_analysis(
        user_id=uid, image_path=image_path, plant_id=plant_name, result=json.dumps(data)
    )

    return {
        "status": "ok",
        "result": result_text,
        "analysis": _analysis_to_dict(analysis),
    }


@app.post("/identify_plantnet")
async def identify_plantnet(
    images: List[str] = Body(...),
    user_id: Optional[int] = Body(0),
    latitude: Optional[float] = Body(None),
    longitude: Optional[float] = Body(None),
    location_label: Optional[str] = Body(None),
):
    if not images:
        raise HTTPException(status_code=400, detail="No images")

    image_b64 = images[0]

    # Save image on disk (under backend/uploads) and keep a path for DB
    image_path = plantnet_service.save_base64_image(image_b64, UPLOAD_DIR)

    # Run the blocking HTTP call in a thread to avoid blocking the event loop
    try:
        data = await asyncio.to_thread(plantnet_service.call_plantnet_api, image_b64)
    except Exception as e:
        print(f"[identify_plantnet] Exception pendant call_plantnet_api: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Erreur PlantNet: {e}")

    # Log what came back from the service (helps diagnose 502s)
    try:
        if isinstance(data, dict) and data.get("error"):
            print(f"[identify_plantnet] plantnet_service a renvoyé une erreur: {data.get('error')!r}")
            if data.get("url"):
                print(f"[identify_plantnet] URL utilisée: {data.get('url')}")
        else:
            print("[identify_plantnet] plantnet_service a répondu sans erreur (clé 'results' attendue)")
    except Exception:
        pass

    # Map error dict coming from the service to proper HTTP statuses
    if isinstance(data, dict) and data.get("error"):
        err = str(data.get("error", "Erreur API"))
        if "401" in err or "Clé API invalide" in err:
            raise HTTPException(status_code=401, detail=err)
        if "403" in err or "Accès refusé" in err:
            raise HTTPException(status_code=403, detail=err)
        if "429" in err or "Trop de requêtes" in err:
            raise HTTPException(status_code=429, detail=err)
        if "Timeout" in err or "timed out" in err.lower():
            raise HTTPException(status_code=504, detail="Le serveur ne répond pas (timeout)")
        raise HTTPException(status_code=502, detail=err)

    # =====================================================
    # Vérification de précision : l'image est-elle bien une plante,
    # et le résultat est-il fiable ?
    # =====================================================
    # PlantNet renvoie un score (0 à 1) pour chaque match. On combine :
    #   1) le score absolu du top-1 (rejet si trop bas → pas une plante)
    #   2) l'écart entre top-1 et top-2 (gap faible = identification ambiguë)
    #   3) un niveau de confiance qualitatif (very_low / low / medium / high)
    NOT_PLANT_THRESHOLD = 0.15  # < 0.15 → on considère que ce n'est pas une plante
    LOW_CONFIDENCE_THRESHOLD = 0.30  # < 0.30 → confiance faible
    HIGH_CONFIDENCE_THRESHOLD = 0.60  # ≥ 0.60 → confiance élevée
    AMBIGUOUS_GAP = 0.05  # si top1 - top2 < 0.05, identification ambiguë

    results_list = []
    top_score = 0.0
    second_score = 0.0
    try:
        results_list = data.get("results") or []
        if results_list:
            top_score = float(results_list[0].get("score") or 0.0)
        if len(results_list) >= 2:
            second_score = float(results_list[1].get("score") or 0.0)
    except Exception:
        results_list = []
        top_score = 0.0

    if not results_list or top_score < NOT_PLANT_THRESHOLD:
        # L'image n'est probablement pas une plante reconnaissable.
        # On NE crée PAS d'analyse en base (rien à stocker d'utile).
        try:
            from pathlib import Path as _P
            _P(image_path).unlink(missing_ok=True)
        except Exception:
            pass
        print(
            f"[identify_plantnet] image rejetée (top_score={top_score:.3f}) — "
            f"pas une plante reconnaissable"
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Ce n'est pas une plante, ou la photo n'est pas assez claire. "
                "Réessaye avec une photo nette d'une feuille, fleur ou fruit "
                "centré dans le cadre, en bonne lumière."
            ),
        )

    # Niveau de confiance qualitatif
    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        confidence_level = "high"
    elif top_score >= LOW_CONFIDENCE_THRESHOLD:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # Ambiguïté : top-1 et top-2 trop proches → on n'est pas sûr
    is_ambiguous = (top_score - second_score) < AMBIGUOUS_GAP and second_score > 0.0

    # Construit la liste des top-3 espèces candidates (utile UI)
    candidates = []
    for r in results_list[:3]:
        try:
            sp = r.get("species") or {}
            candidates.append({
                "scientific_name": sp.get("scientificNameWithoutAuthor")
                    or sp.get("scientificName"),
                "common_names": [str(n) for n in (sp.get("commonNames") or [])][:3],
                "family": (sp.get("family") or {}).get("scientificNameWithoutAuthor"),
                "genus": (sp.get("genus") or {}).get("scientificNameWithoutAuthor"),
                "score": float(r.get("score") or 0.0),
            })
        except Exception:
            continue

    print(
        f"[identify_plantnet] top_score={top_score:.3f} "
        f"second_score={second_score:.3f} "
        f"level={confidence_level} ambiguous={is_ambiguous}"
    )

    # Format result if possible (fallback to raw JSON)
    try:
        result_text = plantnet_service.format_result(data)
    except Exception:
        result_text = json.dumps(data)

    # Try to extract a top species name for storage
    plant_name = None
    try:
        species = results_list[0].get("species") or {}
        plant_name = (
            species.get("scientificNameWithoutAuthor")
            or species.get("scientificName")
        )
    except Exception:
        pass

    # Persist in DB (best effort)
    try:
        uid: int = user_id if user_id is not None else 0
        analysis = db_service.create_analysis(
            user_id=uid,
            image_path=image_path,
            plant_name=plant_name,
            result=json.dumps(data),
            latitude=latitude,
            longitude=longitude,
            location_label=location_label,
        )
        analysis_dict = _analysis_to_dict(analysis)
    except Exception:
        traceback.print_exc()
        analysis_dict = None

    return {
        "status": "ok",
        "result": result_text,
        "analysis": analysis_dict,
        "confidence": top_score,
        "confidence_level": confidence_level,  # high | medium | low
        "low_confidence": confidence_level != "high",
        "ambiguous": is_ambiguous,
        "candidates": candidates,  # top-3 alternatives avec leur score
    }


# =========================
# 💬 ASK ENDPOINTS (développement)
# =========================


class AskRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    user_id: Optional[int] = 0


@app.get("/ask")
async def ask_get(request: Request):
    client = request.client.host if request.client else "unknown"
    print(f"[ASK GET] from {client}")
    return {
        "status": "ok",
        "message": 'POST /ask with JSON {"message":"..."} to get a reply',
    }


@app.post("/ask")
async def ask_post(request: Request, payload: AskRequest = Body(...)):
    client = request.client.host if request.client else "unknown"
    print(f"[ASK POST] from {client} payload={payload.dict()}")
    q = (payload.message or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        # store user message into a conversation (create if needed)
        conv_id = payload.conversation_id or None
        uid = int(payload.user_id or 0)
        if not conv_id:
            conv = db_service.create_conversation(user_id=uid, title=(q[:120] if q else None))
            conv_id = _to_int(getattr(conv, "id"))
        # add user message
        try:
            db_service.add_message(_to_int(conv_id), "user", q)
        except Exception:
            # non-fatal: continue even if message storage fails
            traceback.print_exc()

        # appeler la fonction bloquante dans un thread pour éviter de bloquer l'event loop
        result = await asyncio.to_thread(ai_service.get_ai_answer, q)
        # `get_ai_answer` retourne désormais (text, tokens)
        if isinstance(result, tuple) and len(result) == 2:
            answer_text, tokens_used = result
        else:
            answer_text = result
            tokens_used = 0

        # store assistant reply
        try:
            db_service.add_message(_to_int(conv_id), "assistant", answer_text or "")
        except Exception:
            traceback.print_exc()
    except Exception as e:
        print(f"[ASK ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=str(e))

    return JSONResponse({"status": "ok", "answer": answer_text, "tokens_used": tokens_used, "conversation_id": conv_id})


class ImageRequest(BaseModel):
    prompt: str
    # Format "WxH" (ex. "1024x1024", "768x768"). None = défaut serveur.
    size: Optional[str] = None
    # Style à appliquer parmi : botanical_realistic, botanical_illustration,
    # watercolor, oil_painting, pencil_sketch, vintage_engraving, studio_photo,
    # none. None = défaut serveur (botanical_realistic).
    style: Optional[str] = None


@app.post("/generate_image")
async def generate_image(request: Request, payload: ImageRequest = Body(...)):
    q = (payload.prompt or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="prompt is required")
    try:
        img_b64 = await asyncio.to_thread(
            image_service.generate_image, q, payload.size, payload.style
        )
    except Exception as e:
        print(f"[IMAGE ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=str(e))

    return JSONResponse({"status": "ok", "image_b64": img_b64})


@app.get("/generate_image/styles")
async def list_image_styles():
    """Liste les presets de style disponibles (pour l'UI)."""
    return {"styles": image_service.list_styles()}


# =========================
# 🗂️ Conversations / Messages
# =========================


class ConversationCreate(BaseModel):
    user_id: Optional[int] = 0
    title: Optional[str] = None


class MessageCreate(BaseModel):
    role: str
    content: str


@app.post("/conversations")
async def create_conversation_endpoint(payload: ConversationCreate = Body(...)):
    conv = db_service.create_conversation(user_id=payload.user_id or 0, title=payload.title)
    return {"status": "ok", "conversation": {"id": _to_int(getattr(conv, 'id')), "user_id": conv.user_id, "title": conv.title, "created_at": conv.created_at.isoformat()}}


@app.get("/conversations/{user_id}")
async def list_conversations(user_id: int):
    convs = db_service.list_conversations_for_user(user_id=user_id)
    out = []
    for c in convs:
        # try to grab last message summary
        last = None
        try:
            msgs = db_service.list_messages_for_conversation(_to_int(getattr(c, 'id')), limit=1, offset=max(0, 0))
            if msgs:
                m = msgs[-1]
                # ensure content is a plain string before len/slicing to satisfy static checkers
                raw = getattr(m, 'content', '') or ''
                content = str(raw)
                summary = (content[:200] + '...') if len(content) > 200 else content
                last = {"role": m.role, "content": summary, "created_at": m.created_at.isoformat()}
        except Exception:
            last = None
        out.append({"id": _to_int(getattr(c, 'id')), "user_id": c.user_id, "title": c.title, "created_at": c.created_at.isoformat(), "last_message": last})
    return {"results": out}


@app.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(conv_id: int):
    msgs = db_service.list_messages_for_conversation(conv_id)
    out = []
    for m in msgs:
        out.append({"id": _to_int(getattr(m, 'id')), "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()})
    return {"results": out}


@app.post("/conversations/{conv_id}/messages")
async def post_conversation_message(conv_id: int, payload: MessageCreate = Body(...)):
    msg = db_service.add_message(conv_id, payload.role or "user", payload.content or "")
    return {"status": "ok", "message": {"id": _to_int(getattr(msg, 'id')), "role": msg.role, "content": msg.content, "created_at": msg.created_at.isoformat()}}


# =========================
# 🌿 PLANTS
# =========================


@app.get("/plants")
async def list_plants_endpoint(category: Optional[str] = None):
    # accept category (e.g. 'comestible' or 'médicinale') to filter
    plants = db_service.list_plants(category=category)
    out = []
    for p in plants:
        out.append({
            "id": _to_int(getattr(p, 'id')),
            "scientific_name": getattr(p, 'scientific_name', None),
            "common_name": getattr(p, 'common_name', None),
            "category": getattr(p, 'category', None),
            "description": getattr(p, 'description', None),
        })
    return {"results": out}


# =========================
# 🍽️ MENU CONFIGURATION
# =========================


@app.get("/menu")
async def get_menu():
    """Return a structured menu configuration used by the frontend.

    The menu is intentionally simple: a set of static entries plus
    dynamic category entries derived from plants present in the DB.
    Each menu item contains: id, label, icon (material icon name),
    route (frontend route or special action), order and optional
    permission (e.g. 'premium').
    """
    try:
        plants = db_service.list_plants()
    except Exception:
        plants = []

    # collect categories (preserve insertion order)
    seen = []
    for p in plants:
        try:
            c = (getattr(p, 'category', '') or '').strip()
            if c and c not in seen:
                seen.append(c)
        except Exception:
            continue

    menu = []
    # static primary items
    menu.append({"id": "home", "label": "ACCUEIL", "icon": "home", "route": "/", "order": 10})
    menu.append({"id": "profile", "label": "PROFIL", "icon": "person", "route": "/profile", "order": 20})
    menu.append({"id": "history", "label": "HISTORIQUE", "icon": "history", "route": "/history", "order": 30})
    menu.append({"id": "dashboard", "label": "TABLEAU DE BORD", "icon": "dashboard", "route": "/dashboard", "order": 40})

    # dynamic categories
    base_order = 100
    for i, c in enumerate(seen):
        menu.append({
            "id": "cat_${i}",
            "label": c.capitalize(),
            "icon": "local_florist",
            "route": "/plants?category=${c}",
            "order": base_order + i,
        })

    # footer items
    menu.append({"id": "settings", "label": "PARAMÈTRES", "icon": "settings", "route": "/settings", "order": 1000})
    menu.append({"id": "help", "label": "AIDE", "icon": "help", "route": "/help", "order": 1010})

    # sort by order and return
    try:
        menu_sorted = sorted(menu, key=lambda x: x.get("order", 9999))
    except Exception:
        menu_sorted = menu

    return {"items": menu_sorted}


@app.get("/dashboard")
async def get_dashboard(user_id: Optional[int] = None):
    """Return dashboard data for a specific user (or global if user_id omitted).

    Si user_id est fourni, toutes les statistiques (total_scans, espèces,
    donut, alertes) sont calculées UNIQUEMENT sur les analyses de cet
    utilisateur. Un utilisateur fraîchement inscrit voit donc des compteurs
    à zéro et un donut vide.
    """
    try:
        try:
            from models import get_session, Analysis, Plant
        except Exception:
            from backend.models import get_session, Analysis, Plant

        with get_session() as session:
            base_q = session.query(Analysis)
            if user_id is not None:
                base_q = base_q.filter(Analysis.user_id == user_id)

            total_scans = int(
                base_q.with_entities(func.count(Analysis.id)).scalar() or 0
            )

            sp_q = session.query(
                func.count(func.distinct(Analysis.plant_name))
            ).filter(Analysis.plant_name != None)
            if user_id is not None:
                sp_q = sp_q.filter(Analysis.user_id == user_id)
            species_count = int(sp_q.scalar() or 0)

            # Compteurs par catégorie pour le user demandé
            cat_q = session.query(
                func.lower(func.coalesce(Analysis.category, 'inconnu')),
                func.count(Analysis.id),
            )
            if user_id is not None:
                cat_q = cat_q.filter(Analysis.user_id == user_id)
            q = (
                cat_q.group_by(
                    func.lower(func.coalesce(Analysis.category, 'inconnu'))
                ).all()
            )
            counts = {(c or 'inconnu'): int(n) for c, n in q}
            com = counts.get('comestible', 0)
            med = counts.get('medicinale', 0) + counts.get('medicinal', 0)
            tox = counts.get('toxique', 0)

            # donut percentages relative to category-known analyses
            cat_total = com + med + tox
            def pct(n, base=total_scans):
                try:
                    return f"{(n * 100.0 / base):.1f}%" if base and base > 0 else '—'
                except Exception:
                    return '—'

            percent_toxic = pct(tox, total_scans)

            donut = {
                'comestible': pct(com, cat_total),
                'medicinal': pct(med, cat_total),
                'toxic': pct(tox, cat_total),
                'dominant': '—',
            }

            # determine dominant
            if cat_total > 0:
                dom = max(
                    ('comestible', 'medicinal', 'toxic'),
                    key=lambda k: {'comestible': com, 'medicinal': med, 'toxic': tox}.get(k, 0),
                )
                names = {'comestible': 'Comestible', 'medicinal': 'Médicinales', 'toxic': 'Toxiques'}
                donut['dominant'] = names.get(dom, dom)

            # simple alert rules (best-effort)
            alerts = []
            try:
                if total_scans > 0 and tox * 100.0 / max(1, total_scans) > 10.0:
                    alerts.append({
                        'title': 'Taux de plantes toxiques élevé',
                        'subtitle': f'{percent_toxic} des analyses récentes sont signalées toxiques.',
                        'actionLabel': 'Vérifier',
                        'color': str(0xFFba1a1a),
                        'time': "AUJOURD'HUI",
                    })
                if species_count > 50:
                    alerts.append({
                        'title': 'Grande diversité détectée',
                        'subtitle': f'{species_count} espèces identifiées récemment.',
                        'actionLabel': 'Explorer',
                        'color': str(0xFF2e7d32),
                        'time': 'HIER',
                    })
            except Exception:
                alerts = []

            return {
                "stats": {
                    "total_scans": total_scans,
                    "percent_toxic": percent_toxic,
                    "species_count": species_count,
                },
                "donut": donut,
                "alerts": alerts,
            }
    except Exception:
        traceback.print_exc()
        # tolerant defaults when DB/tables are missing or a query fails
        return {
            "stats": {"total_scans": 0, "percent_toxic": '—', "species_count": 0},
            "donut": {
                "comestible": '—',
                "medicinal": '—',
                "toxic": '—',
                "dominant": '—',
            },
            "alerts": [],
        }


@app.get("/plants/{plant_id}")
async def get_plant_endpoint(plant_id: int):
    p = db_service.get_plant_by_id(plant_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": _to_int(getattr(p, 'id')),
        "scientific_name": p.scientific_name,
        "common_name": p.common_name,
        "description": p.description,
    }


# =========================
# 🚀 LANCEMENT
# =========================
if __name__ == "__main__":
    import uvicorn

    # Expose the server on all interfaces so emulators/devices can reach it
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
