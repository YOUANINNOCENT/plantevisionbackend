Mini API FastAPI pour le projet "plante"

Installation (recommandé dans un virtualenv) :

```bash
python -m venv .venv
source .venv/bin/activate   # ou .\.venv\Scripts\activate sur Windows
pip install -r backend/requirements.txt
```

Lancer le serveur (développement) :

```bash
uvicorn backend.main:app --reload
```

Endpoints disponibles :
- `GET /health` : check
- `POST /upload` : upload d'image; champs form : `file` (image) et `user_id` (int)
- `GET /analyses/{user_id}` : liste des analyses pour l'utilisateur
 - `POST /identify_plantnet` : identification via PlantNet. JSON: `{"images": ["<base64>"], "organs": ["leaf"], "lang": "fr"}`. Retourne `raw` (réponses PlantNet) et `formatted` (résumé lisible).

Le backend charge dynamiquement `models.py` et `backend/services/db_service.py` et crée la base de données si nécessaire.

Configuration PlantNet:
- Définir `PLANTNET_API_KEY` dans `backend/.env` (ou variables d'environnement).
- Optionnel: `PLANTNET_API_URL` pour redéfinir l'endpoint (par défaut: `https://my-api.plantnet.org/v2/identify`).

Exemple test curl:

```
curl -X POST http://localhost:8000/identify_plantnet \
	-H "Content-Type: application/json" \
	-d '{"images":["data:image/jpeg;base64,/9j/4AAQSk..."], "lang":"fr"}'
```
