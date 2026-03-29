# Carte Coach — Vérification de carte professionnelle d'éducateur sportif

Pipeline de vérification automatique des cartes professionnelles d'éducateur sportif.
Le coach envoie une photo de sa carte → extraction OCR locale → vérification officielle Ministère des Sports → stockage Supabase.

---

## Architecture

```
Photo de carte (JPG/PNG)
        │
        ▼
┌───────────────────┐
│  LM Studio local  │  VLM Qwen3-VL-8B (réseau local)
│  OCR + extraction │  Aucune donnée envoyée sur internet
└────────┬──────────┘
         │ nom, prénom, numéro de carte
         ▼
┌───────────────────────────────────┐
│  API Ministère des Sports (EME)   │  POST public, données déjà publiques
│  eme-api-core.sports.gouv.fr      │
└────────┬──────────────────────────┘
         │ valide: true/false
         ▼
┌───────────────────┐
│  Supabase cloud   │  Stockage structuré (région EU)
│  cartes_coach     │
└───────────────────┘
```

---

## Prérequis

- Python 3.12
- [LM Studio](https://lmstudio.ai) avec le modèle `qwen/qwen3-vl-8b` chargé
- Un projet [Supabase](https://supabase.com) en région EU (Frankfurt)

---

## Installation

```bash
# Créer l'environnement virtuel avec Python 3.12
uv venv .venv --python 3.12
.venv\Scripts\activate

# Installer les dépendances
uv pip install extract_thinker supabase python-dotenv requests python-magic-bin numpy
```

---

## Configuration

Créer un fichier `.env` à la racine du projet :

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=ta_clé_supabase
```

Adapter dans `carte_processor.py` l'adresse de LM Studio :

```python
LMSTUDIO_BASE_URL = "http://192.168.1.181:12000/v1"  # IP de ta machine LM Studio
MODEL_NAME = "qwen/qwen3-vl-8b"
```

---

## Base de données Supabase

Exécuter dans le **SQL Editor** de Supabase :

```sql
CREATE TABLE cartes_coach (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nom TEXT,
    prenom TEXT,
    nationalite TEXT,
    date_naissance TEXT,
    lieu_naissance TEXT,
    numero_carte TEXT UNIQUE,
    fichier TEXT,
    valide BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Utilisation

### Script autonome

Déposer l'image dans `carte_coach/files/cartes/` puis :

```bash
python carte_coach/carte_processor.py
```

### Intégration dans une application

```python
from carte_coach.carte_processor import process_carte

# Retourne un dict avec les données extraites et le champ valide: bool
result = process_carte("chemin/vers/carte.jpg")

if result and result["valide"]:
    print(f"Coach valide : {result['prenom']} {result['nom']}")
else:
    print("Carte non reconnue par le Ministère des Sports")
```

### Intégration dans une app mobile (React Native / Flutter)

Le pipeline s'expose comme une API REST. Exemple avec FastAPI :

```python
from fastapi import FastAPI, UploadFile
import shutil, uuid
from carte_coach.carte_processor import process_carte

app = FastAPI()

@app.post("/verifier-carte")
async def verifier(file: UploadFile):
    # Sauvegarde temporaire
    tmp_path = f"/tmp/{uuid.uuid4()}.jpg"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    result = process_carte(tmp_path)

    # Suppression immédiate de l'image (RGPD)
    os.remove(tmp_path)

    if not result:
        return {"valide": False, "erreur": "Extraction échouée"}
    return result
```

L'app mobile envoie un `multipart/form-data` avec la photo, et reçoit le JSON de résultat.

---

## Vérification officielle

L'API utilisée est l'API publique du Ministère des Sports (système EME) :

- **URL** : `https://eme-api-core.sports.gouv.fr/api/Educateur/GetAllPubliEdu`
- **Méthode** : POST
- **CORS** : ouvert (`access-control-allow-origin: *`)
- **Données envoyées** : nom, prénom, numéro de carte uniquement
- **Réponse** : `nbResults > 0` = carte valide

---

## Conformité RGPD

### Contexte
Le coach envoie lui-même sa carte professionnelle via l'application mobile.
Il est l'initiateur de la démarche — la base légale est le **consentement explicite**.

### Ce qui est traité

| Donnée | Traitement | Stockage |
|--------|-----------|---------|
| Photo de la carte | Analyse locale (LM Studio) | Non stockée — supprimée après extraction |
| Nom, prénom | Envoyé à l'API Ministère des Sports | Supabase EU |
| Numéro de carte | Envoyé à l'API Ministère des Sports | Supabase EU |
| Nationalité, lieu de naissance | Extraction locale uniquement | Supabase EU |

### Obligations

1. **Consentement** — Afficher avant le scan :
   > *"Votre carte sera analysée localement. Seuls votre nom, prénom et numéro de carte seront transmis au Ministère des Sports pour vérification. Ces données sont conservées [durée] et peuvent être supprimées sur demande."*

2. **Durée de conservation** — Définir une durée (recommandé : 12 mois) et purger automatiquement :
   ```sql
   DELETE FROM cartes_coach WHERE created_at < NOW() - INTERVAL '12 months';
   ```

3. **Droit à l'effacement** — Exposer un endpoint de suppression :
   ```python
   supabase.table("cartes_coach").delete().eq("numero_carte", numero).execute()
   ```

4. **Hébergement EU** — Le projet Supabase doit être en région `eu-west-1` (Frankfurt) pour rester dans l'UE.

5. **Politique de confidentialité** — Obligatoire pour publication sur App Store / Google Play. Doit mentionner :
   - Les données collectées
   - La finalité (vérification d'habilitation)
   - Le responsable de traitement (toi / ton entreprise)
   - Un email de contact DPO

6. **Pas de photo stockée** — L'image est supprimée immédiatement après extraction (voir endpoint FastAPI ci-dessus).

### Ce qui n'est PAS envoyé à un tiers cloud
- La photo de la carte
- Les données vers OpenAI ou tout autre LLM cloud
- Tout traitement d'image se fait sur le réseau local via LM Studio
