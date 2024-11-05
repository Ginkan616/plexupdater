import logging
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Request
from starlette.datastructures import Headers
from typing import Optional
from pydantic import BaseModel
import yagmail
import time
import configparser
import schedule
import threading
import json
import os

# Configuration du fichier (remplacez par votre chemin)
CONFIG_FILE = "config.ini"

# Objet de configuration
config = configparser.ConfigParser()

# fichier newmovies.txt pour stocker les titres et années des films pour la journée
newmoviestxt = open("newmovies.txt", "a")
newmoviessize = os.path.getsize('newmovies.txt')

# Lecture de la configuration à partir du fichier
config.read(CONFIG_FILE)

# Configuration (en utilisant des sections et des clés de config.ini)
PLEX_WEBHOOK_URL = config["plex"]["webhook_url"]

# Configuration de l'email
EMAIL_SECTION = "email"
EMAIL_USER = config[EMAIL_SECTION]["user"]
EMAIL_PASSWORD = config[EMAIL_SECTION]["password"]
EMAIL_HOST = config[EMAIL_SECTION]["host"]
EMAIL_RECIPIENTS = config[EMAIL_SECTION]["recipients"].split(",")

# Créer l'objet yagmail
yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASSWORD, EMAIL_HOST)

app = FastAPI()

logging.basicConfig(level=logging.DEBUG)

# Fonction pour envoyer un email en HTML avec les informations des films
def send_email():
    try:
        if os.path.getsize("newmovies.txt") > 0:
            # Construction du corps du mail en HTML avec une structure correcte
            body = """\
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title style="color:black">Plex News !</title>
</head>
<body>
    <h2 style="color:black;">Nouveaux films ajoutés aujourd'hui :</h2>
    <ul>"""
            attachments = []

            # Lire les données du fichier
            with open("newmovies.txt", "r") as newmoviestxt:
                for movie in newmoviestxt:
                    moviesplit = movie.strip().split(";")
                    title, year, image_path = moviesplit[0], moviesplit[1], moviesplit[2]
                
                # Ajout des informations dans le corps du mail HTML et la version texte
                body += f"<li style=\"color:black;\"><strong>{title} ({year})</strong><br>"
                
                if image_path:
                    # Référence de l'image dans le contenu HTML
                    body += f'<img src="cid:{title}_{year}" alt="{title}" width="200"><br>'
                    # Ajout de l'image en tant qu'attachemen
                    attachments.append(yagmail.inline(image_path))
                
                body += "</li><br>"
            
            body += "</ul></body></html>"

            # Envoi de l'email avec le contenu HTML et les images en inline, plus une version texte
            yag.send(
                to=EMAIL_RECIPIENTS, 
                subject="Nouveaux films ajoutés dans Plex", 
                contents=[body] + attachments
            )
            open("newmovies.txt", "w").close()
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de l'email: {e}", exc_info=True)

# Fonction pour gérer les threads
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Lancer la planification dans un thread séparé
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.start()

# Planifier l'envoi d'un email à la fin de chaque jour
schedule.every().day.at("19:30").do(send_email)

class Account(BaseModel):
    id: int
    thumb: str
    title: str

class Server(BaseModel):
    title: str
    uuid: str

class Metadata(BaseModel):
    librarySectionType: Optional[str] = None
    ratingKey: str
    key: str
    guid: str
    slug: str
    studio: Optional[str] = None
    type: str
    title: str
    titleSort: Optional[str] = None
    librarySectionTitle: Optional[str] = None
    librarySectionID: Optional[int] = None
    librarySectionKey: Optional[str] = None
    originalTitle: Optional[str] = None
    contentRating: Optional[str] = None
    summary: Optional[str] = None
    audienceRating: Optional[float] = None
    year: int
    tagline: Optional[str] = None
    thumb: Optional[str] = None
    art: Optional[str] = None
    duration: Optional[int] = None
    originallyAvailableAt: Optional[str] = None
    addedAt: Optional[int] = None
    updatedAt: Optional[int] = None

class WebhookPayload(BaseModel):
    event: str
    user: bool
    owner: bool
    Account: Account
    Server: Server
    Metadata: Metadata

@app.post("/plexupdater")
async def handle_webhook(
    payload: Optional[str] = Form(None),
    thumb: Optional[UploadFile] = File(None),
    request: Request = None
):
    logging.info(f"Requête reçue avec les en-têtes : {request.headers}")

    if not payload:
        logging.error("Aucune donnée payload reçue.")
        raise HTTPException(status_code=400, detail="Données manquantes : payload")

    try:
        # Charger les données du formulaire
        form_data = await request.form()
        logging.info(f"Données reçues : {form_data}")

        # Extraire et décoder les données de payload
        payload_data = form_data.get("payload")
        if not payload_data:
            logging.error("Données manquantes dans le payload.")
            raise HTTPException(status_code=400, detail="Données manquantes dans le payload")

        # Vérifier la présence de `contentRating` et autres champs optionnels
        payload_dict = json.loads(payload_data)
        payload_dict["Metadata"]["contentRating"] = payload_dict["Metadata"].get("contentRating", None)

        # Décodage du JSON payload
        payload_obj = WebhookPayload(**payload_dict)

        # Filtrer et ignorer les événements qui ne sont pas de type "library.new"
        if payload_obj.event != "library.new":
            logging.info(f"Événement ignoré : {payload_obj.event}")
            return {"message": f"Événement ignoré : {payload_obj.event}"}

        # Extraire le titre et l'année du film
        title = payload_obj.Metadata.title
        year = payload_obj.Metadata.year
        

        # Si une image est envoyée dans le formulaire
        image_path = None
        if thumb:
            image_bytes = await thumb.read()
            image_path = f"images/{title}_{year}.jpg"
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            logging.info(f"Image reçue et sauvegardée : {image_path}")

        # Ajouter les informations du film au fichier texte newmovies.txt
        with open("newmovies.txt", "a") as newmoviestxt:
            newmoviestxt.write(title + ";" + str(year) + ";" + image_path + "\n")

        logging.info(f"Traitement réussi : Titre = {title}, Année = {year}")

        return {"message": "Données reçues et traitées avec succès"}

    except Exception as e:
        logging.error(f"Erreur lors du traitement du webhook: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")

# Démarrer le serveur Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="192.168.1.35", port=8000)