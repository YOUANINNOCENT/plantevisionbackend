import json
import time
from typing import Tuple


def get_ai_answer(message: str, system_prompt: str | None = None) -> Tuple[str, int]:
    """Réponse IA locale de secours.

    Après suppression du support OpenAI/Gemini, cette fonction fournit
    uniquement des réponses locales simples utiles pour le développement
    hors-ligne. Elle ne dépend plus d'aucune clé externe.
    """
    m = (message or "").strip().lower()
    # salutations
    if any(w in m for w in ["bonjour", "salut", "coucou", "hello"]):
        return ("Bonjour ! Je suis votre assistant botanique hors-ligne — comment puis-je vous aider ?", 0)
    if "comment tu vas" in m or "ça va" in m or "ca va" in m:
        return ("Je vais bien, merci — prêt à vous aider avec des informations sur les plantes.", 0)
    # identifier une plante
    if any(w in m for w in ["identifier", "quelle plante", "c'est quelle plante", "quelle est cette plante"]):
        return (
            "Pour identifier une plante, envoyez une photo nette de la feuille et de la fleur si possible. "
            "Donnez aussi le lieu et la saison. Je proposerai des suggestions probables.",
            0,
        )
    # préparations (infusion / décoction)
    if any(w in m for w in ["décoction", "decoction", "infusion", "préparer", "préparation"]):
        return (
            "Infusion: verser eau chaude sur les parties tendres (feuilles, fleurs) et laisser 5–10 min. "
            "Décoction: faire bouillir les parties dures (racines, écorces) 10–30 min selon la matière.",
            0,
        )
    # sécurité / comestible
    if any(w in m for w in ["comestible", "manger", "toxique", "poison"]):
        return (
            "N'allez pas consommer une plante sans certitude. Recherchez des sources fiables ou demandez l'avis d'un expert. "
            "La même espèce peut comporter des variétés toxiques.",
            0,
        )

    # question générique: fournir piste utile
    return (
        "Je n'ai pas accès à une API distante ici. Je peux aider pour l'identification, les préparations (infusion/décoction) "
        "et les précautions. Posez une question précise.",
        0,
    )
