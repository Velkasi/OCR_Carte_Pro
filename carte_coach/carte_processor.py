import os
import json
import yaml
from typing import Optional
from pydantic import Field
from dotenv import load_dotenv

import litellm
from supabase import create_client
from extract_thinker import Extractor, LLM, Contract
import requests

load_dotenv()

# LM Studio — VLM local, aucune donnée ne quitte le réseau
LMSTUDIO_BASE_URL = "http://192.168.1.181:12000/v1"
MODEL_NAME = "qwen/qwen3-vl-8b"

litellm.api_base = LMSTUDIO_BASE_URL
litellm.api_key = "local"

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def json_to_yaml(json_dict):
    if not isinstance(json_dict, dict):
        raise ValueError("json_dict must be a dictionary")
    return yaml.dump(json_dict, allow_unicode=True)


# Champs extraits de la carte par le VLM
class CarteCoachContract(Contract):
    nom: str = Field("Nom de famille")
    prenom: str = Field("Prénom")
    nationalite: Optional[str] = Field("Nationalité")
    date_naissance: Optional[str] = Field("Date de naissance au format JJ/MM/AAAA")
    lieu_naissance: Optional[str] = Field("Lieu de naissance")
    numero_carte: Optional[str] = Field("Numéro de carte professionnelle")


def verifier_carte(nom: str, prenom: str, numero_carte: str) -> bool:
    # API publique du Ministère des Sports (système EME)
    resp = requests.post(
        "https://eme-api-core.sports.gouv.fr/api/Educateur/GetAllPubliEdu",
        json={
            "nomFamille": nom,
            "prenom": prenom,
            "cartePro": numero_carte,
            "itemByPage": 10,
            "numeroPage": 0,
            "typeUser": "EducUser"
        },
        timeout=10
    )
    return resp.json().get("nbResults", 0) > 0


def setup_extractor():
    extractor = Extractor()
    llm = LLM(f"openai/{MODEL_NAME}")
    extractor.load_llm(llm)
    return extractor


def process_carte(carte_path: str):
    extractor = setup_extractor()
    print(f"\nTraitement : {os.path.basename(carte_path)}")

    # vision=True envoie l'image directement au VLM sans OCR intermédiaire
    result = extractor.extract(carte_path, CarteCoachContract, vision=True)

    try:
        carte_json = json.loads(result.model_dump_json())
        print(json_to_yaml(carte_json))

        # Vérification officielle puis sauvegarde
        carte_json["valide"] = verifier_carte(carte_json["nom"], carte_json["prenom"], carte_json["numero_carte"])
        print(f"Carte : {'✓ VALIDE' if carte_json['valide'] else '✗ INVALIDE'}")

        carte_json["fichier"] = os.path.basename(carte_path)
        supabase.table("cartes_coach").upsert(carte_json, on_conflict="numero_carte").execute()
        print("Sauvegardé dans Supabase.")

        return carte_json
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Erreur : {e}")
        return None


def main():
    carte_path = os.path.join("carte_coach", "files", "cartes", "carte-pro.jpg")
    if os.path.exists(carte_path):
        process_carte(carte_path)
    else:
        print(f"Carte introuvable : {carte_path}")


if __name__ == "__main__":
    main()
