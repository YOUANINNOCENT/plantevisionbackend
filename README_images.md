Activation rapide de l'API de génération d'images Google
===============================================

Résumé (rapide) — étapes pour activer la génération d'images (Image Bison / Generative AI) et obtenir une clé API utilisable avec ce projet :

1. Créer un projet Google Cloud
   - Ouvrez https://console.cloud.google.com/ et créez (ou sélectionnez) un projet.

2. Activer la facturation
   - La plupart des APIs de génération nécessitent un projet avec facturation activée.

3. Activer l'API de génération d'images / Generative AI
   - Dans la console, allez dans "APIs & Services" → "Library".
   - Recherchez "Generative" ou "Generative AI" / "Generative Language API" et activez les API liées à la génération de contenu et d'images (Image Bison ou l'équivalent disponible pour votre région).

4. Créer une clé API
   - Dans "APIs & Services" → "Credentials", cliquez sur "Create credentials" → "API key".
   - Restreignez la clé (recommandé) : référez-vous aux restrictions par adresse IP, référent HTTP ou aux APIs autorisées.

5. Tester l'endpoint depuis ce projet
   - Le service backend attend la clé via l'endpoint d'administration (dev only) :

    - Ensuite, demandez la génération d'image :

       curl -X POST http://127.0.0.1:8000/generate_image -H "Content-Type: application/json" -d '{"prompt":"Une feuille de menthe sur fond blanc, photographie réaliste","size":"512x512"}'

6. Vérifications et erreurs courantes
   - Si vous obtenez une erreur 404 depuis https://generativelanguage.googleapis.com, l'API image n'est probablement pas activée pour ce projet/clé.
   - Assurez-vous que la clé est autorisée à appeler l'API generative et que la facturation est active.
   - Pour la production, ne stockez pas la clé en clair ni ne l'exposez via un endpoint non protégé.

Remarque : selon votre compte et la région, le nom d'API exact (Image Bison / Generative Images) peut varier — cherchez "Generative" dans la bibliothèque d'APIs.
