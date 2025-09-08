from dotenv import load_dotenv
load_dotenv()

# main.py (Updated for Phase 4)
import os
import requests
import uvicorn
from fastapi import FastAPI, Request, Response

# --- Configuration ---
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
RASA_API_URL = "http://localhost:5005/webhooks/rest/webhook"

# --- FastAPI App Initialization ---
app = FastAPI()

# --- Webhook Verification Endpoint ---
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # --- OUR NEW DEBUG LINES ---
    print(f"--> TOKEN FROM META: '{token}'")
    print(f"--> TOKEN FROM MY CODE: '{VERIFY_TOKEN}'")
    # -------------------------

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return Response(content=challenge, status_code=200)
        else:
            return Response(status_code=403) # Forbidden
    return Response(status_code=404)

# --- Main Message Handling Endpoint ---
@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print("Received message body:", body)

    try:
        if body.get("object"):
            entry = body.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            message_info = value.get("messages", [{}])[0]
            
            if message_info:
                from_number = message_info["from"]
                msg_body = message_info.get("text", {}).get("body")

                if msg_body:
                    # --- NEW: Call Rasa to get a smart reply ---
                    rasa_response = get_rasa_response(from_number, msg_body)
                    
                    # Send each reply from Rasa back to the user
                    for reply in rasa_response:
                        send_whatsapp_message(from_number, reply.get("text"))

    except Exception as e:
        print(f"Error processing message: {e}")
        pass

    return Response(status_code=200)

# --- NEW: Helper Function to talk to Rasa ---
def get_rasa_response(sender_id: str, message: str):
    """
    Sends a message to the Rasa server and gets the bot's response.
    """
    payload = {"sender": sender_id, "message": message}
    try:
        response = requests.post(RASA_API_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling Rasa: {e}")
        return [{"text": "Sorry, my brain is taking a break right now. Please try again later."}]


# --- Helper Function to Send Messages ---
def send_whatsapp_message(to_number: str, message: str):
    if not message: # Don't send empty messages
        return

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": message},
    }
    
    if not all([ACCESS_TOKEN, PHONE_NUMBER_ID]):
        print("Missing WhatsApp credentials.")
        return

    response = requests.post(url, headers=headers, json=data)
    print("Sent message response:", response.json())
    response.raise_for_status()

# --- To run the app from the command line ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)