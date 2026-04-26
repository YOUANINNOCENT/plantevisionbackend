"""Small compatibility shim so `backend` can import models.

This re-exports the main SQLAlchemy objects from the parent plante/models.py
so that `from models import engine, SessionLocal, ...` works inside the backend package.
"""
import sys
import importlib.util
from pathlib import Path

# Load the plante/models.py file directly by path to avoid circular imports
plante_models_path = Path(__file__).parent.parent / "models.py"
spec = importlib.util.spec_from_file_location("plante_models", plante_models_path)
plante_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plante_models)

# Re-export everything
engine = plante_models.engine
SessionLocal = plante_models.SessionLocal
get_session = plante_models.get_session
init_db = plante_models.init_db
Base = plante_models.Base
User = plante_models.User
Plant = plante_models.Plant
Analysis = plante_models.Analysis
Conversation = plante_models.Conversation
Message = plante_models.Message

__all__ = [
    "engine",
    "SessionLocal",
    "get_session",
    "init_db",
    "Base",
    "User",
    "Plant",
    "Analysis",
    "Conversation",
    "Message",
]
