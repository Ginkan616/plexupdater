import json
from fastapi import FastAPI, Request, HTTPException
import yagmail
import logging
import time
from configparser import ConfigParser
import schedule
import threading
import uvicorn

# Install chardet library for encoding detection (if not already installed)
# pip install chardet

# Configuration file path (replace with your actual path)
CONFIG_FILE = "config.ini"

# Configuration object
config = ConfigParser()

# Read configuration from file
config.read(CONFIG_FILE)


# Configuration (using sections and keys from config.ini)
PLEX_WEBHOOK_URL = config["plex"]["webhook_url"]

# Email Configuration
EMAIL_SECTION = "email"
EMAIL_USER = config[EMAIL_SECTION]["user"]
EMAIL_PASSWORD = config[EMAIL_SECTION]["password"]
EMAIL_HOST = config[EMAIL_SECTION]["host"]
EMAIL_RECIPIENTS = config[EMAIL_SECTION]["recipients"].split(",")  # Split recipients string into a list

# Create the yagmail object
yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASSWORD, EMAIL_HOST)

# List for storing new movies
new_movies = []

# Configuration of logging
logging.basicConfig(filename='app.log', level=logging.DEBUG)

# Create the FastAPI application
app = FastAPI()


# Function to send email (moved above scheduling)
def send_email():
    try:
        if new_movies:
            body = f"Nouveaux films ajoutés aujourd'hui:\n" + "\n".join(new_movies)
            logging.info(f"Sending email with body:\n{body}")
            yag.send(to=EMAIL_RECIPIENTS, subject="Nouveaux films ajoutés dans Plex", contents=body)
            new_movies.clear()
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de l'email: {e}", exc_info=True)


# Function to manage threads
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


# Launch scheduling in a separate thread
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.start()

# Schedule email sending at the end of each day
schedule.every().day.at("23:59").do(send_email)


@app.post(PLEX_WEBHOOK_URL)
async def handle_webhook(request: Request):
    try:
        # Check for non-empty payload
        if not request.body:
            logging.warning("Webhook reçu sans payload.")
            return {"message": "Empty payload received"}, 400

        # Decode JSON data with automatic encoding detection
        try:
            # Read raw bytes from the request
            raw_data = await request.body()

            # Detect encoding using chardet library
            import chardet
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')  # Default to UTF-8 if not detected

            # Decode JSON with detected encoding
            data = json.loads(raw_data.decode(encoding))
        except (json.JSONDecodeError, chardet.LegacyCharsetError) as e:
            logging.error(f"Erreur de décodage JSON: {e}")
            return {"message": "Invalid JSON payload"}, 400

        logging.info(f"Received webhook data: {data}")

        # Validate JSON payload and event
        if not data or "event" not in data or data["event"] != "library.new":
            logging.warning("Pas de payload JSON valide ou pas d'événement 'library.new'.")
            return {"message": "Invalid payload or event"}, 400

        # Extract movie information
        movie_title = data.get("Metadata", {}).get("title", "Inconnu")
        movie_year = data.get("Metadata", {}).get("year", "Inconnu")

        # Add the movie to the list
        new_movies.append(f"{movie_title} ({movie_year})")

        # **Fixed:** Return statement placed within the try block
        return {"message": "Webhook traité avec succès"}

    except Exception as e:
        logging.error(f"Erreur lors du traitement du webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")