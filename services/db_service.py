from typing import List, Optional, Any
from sqlalchemy import func
import sys
from pathlib import Path

# Add backend folder to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import get_session, User, Plant, Analysis, init_db, Conversation, Message


def create_user(
    email: str, full_name: Optional[str] = None, hashed_password: Optional[str] = None
) -> User:
    """Create and return a new User."""
    with get_session() as session:
        user = User(email=email, full_name=full_name, hashed_password=hashed_password)
        session.add(user)
        session.flush()
        session.refresh(user)
        return user


def get_user_by_email(email: str) -> Optional[User]:
    with get_session() as session:
        return session.query(User).filter(User.email == email).first()


def get_user(user_id: int) -> Optional[User]:
    with get_session() as session:
        return session.get(User, user_id)


def update_user(user_id: int, **fields: Any) -> Optional[User]:
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return None
        for k, v in fields.items():
            if hasattr(user, k):
                setattr(user, k, v)
        session.add(user)
        session.flush()
        session.refresh(user)
        return user


def delete_user(user_id: int) -> bool:
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return False
        session.delete(user)
        return True


# Plants
def create_plant(
    scientific_name: Optional[str] = None,
    common_name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
) -> Plant:
    with get_session() as session:
        plant = Plant(
            scientific_name=scientific_name,
            common_name=common_name,
            category=category,
            description=description,
        )
        session.add(plant)
        session.flush()
        session.refresh(plant)
        return plant


def get_plant_by_id(plant_id: int) -> Optional[Plant]:
    with get_session() as session:
        return session.get(Plant, plant_id)


def get_plant_by_name(name: str) -> Optional[Plant]:
    with get_session() as session:
        return session.query(Plant).filter(Plant.scientific_name == name).first()


def update_plant(plant_id: int, **fields: Any) -> Optional[Plant]:
    with get_session() as session:
        plant = session.get(Plant, plant_id)
        if not plant:
            return None
        for k, v in fields.items():
            if hasattr(plant, k):
                setattr(plant, k, v)
        session.add(plant)
        session.flush()
        session.refresh(plant)
        return plant


def delete_plant(plant_id: int) -> bool:
    with get_session() as session:
        plant = session.get(Plant, plant_id)
        if not plant:
            return False
        session.delete(plant)
        return True


def list_plants(limit: int = 200, offset: int = 0, category: Optional[str] = None) -> List[Plant]:
    with get_session() as session:
        q = session.query(Plant)
        if category:
            # normalize simple accents and case for matching
            cat_norm = category.lower().replace('é', 'e').replace('è', 'e').replace('ê', 'e').strip()
            q = q.filter(
                func.lower(func.replace(func.replace(func.replace(Plant.category, 'é', 'e'), 'è', 'e'), 'ê', 'e')) == cat_norm
            )
        return (
            q.order_by(Plant.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )


# Analyses
def create_analysis(
    user_id: int,
    plant_id: Optional[int] = None,
    plant_name: Optional[str] = None,
    image_path: Optional[str] = None,
    result: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_label: Optional[str] = None,
) -> Analysis:
    with get_session() as session:
        analysis = Analysis(
            user_id=user_id,
            plant_id=plant_id,
            plant_name=plant_name,
            image_path=image_path,
            result=result,
            latitude=latitude,
            longitude=longitude,
            location_label=location_label,
        )
        session.add(analysis)
        session.flush()
        session.refresh(analysis)
        return analysis


def list_recent_locations(limit: int = 50, user_id: Optional[int] = None) -> List[Analysis]:
    """Renvoie les analyses récentes ayant des coordonnées GPS.

    Si user_id est fourni, filtre uniquement les analyses de cet utilisateur.
    """
    with get_session() as session:
        q = (
            session.query(Analysis)
            .filter(Analysis.latitude.isnot(None))
            .filter(Analysis.longitude.isnot(None))
        )
        if user_id is not None:
            q = q.filter(Analysis.user_id == user_id)
        return (
            q.order_by(Analysis.created_at.desc())
            .limit(limit)
            .all()
        )


def get_analysis_by_id(analysis_id: int) -> Optional[Analysis]:
    with get_session() as session:
        return session.get(Analysis, analysis_id)


def list_analyses_for_user(
    user_id: int, limit: int = 50, offset: int = 0
) -> List[Analysis]:
    with get_session() as session:
        return (
            session.query(Analysis)
            .filter(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def update_analysis_result(analysis_id: int, result: str) -> Optional[Analysis]:
    with get_session() as session:
        analysis = session.get(Analysis, analysis_id)
        if not analysis:
            return None
        # Use setattr to avoid static typing issues with SQLAlchemy Column descriptors
        setattr(analysis, 'result', result)
        session.add(analysis)
        session.flush()
        session.refresh(analysis)
        return analysis


def delete_analysis(analysis_id: int) -> bool:
    with get_session() as session:
        analysis = session.get(Analysis, analysis_id)
        if not analysis:
            return False
        session.delete(analysis)
        return True


# Conversations / Messages
def create_conversation(user_id: Optional[int] = None, title: Optional[str] = None) -> Conversation:
    with get_session() as session:
        conv = Conversation(user_id=user_id, title=title)
        session.add(conv)
        session.flush()
        session.refresh(conv)
        return conv


def get_conversation(conv_id: int) -> Optional[Conversation]:
    with get_session() as session:
        return session.get(Conversation, conv_id)


def list_conversations_for_user(user_id: int, limit: int = 50, offset: int = 0) -> List[Conversation]:
    with get_session() as session:
        return (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def add_message(conversation_id: int, role: str, content: str) -> Message:
    with get_session() as session:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        session.add(msg)
        session.flush()
        session.refresh(msg)
        return msg


def list_messages_for_conversation(conversation_id: int, limit: int = 500, offset: int = 0) -> List[Message]:
    with get_session() as session:
        return (
            session.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def initialize_database(drop_existing: bool = False) -> None:
    """Convenience wrapper to initialize DB tables."""
    init_db(drop_existing=drop_existing)
