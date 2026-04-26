"""Configuration runtime simple pour les services.

Contient un flag `ai_mode`:
- 'auto' (par défaut): utilise OpenAI si `OPENAI_API_KEY` est définie, sinon fallback local.
- 'local': force le fallback local (utile pour dev sans clé).
- 'remote': force l'appel à l'API distante (nécessite clé sinon erreur).

Ce fichier est volontairement minimal et non sécurisé; pour la prod utilisez
une configuration plus robuste et des contrôles d'accès.
"""