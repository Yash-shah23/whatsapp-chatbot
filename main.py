# main.py
import os
import requests
import uvicorn
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
RASA_API_URL = "http://localhost:5005/webhooks/rest/webhook"

app = FastAPI()

def mark_message_as_read(message_id: str):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"Error marking message as read: {e}")

def show_typing_indicator(to_number: str):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "type": "typing"}
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"Error sending typing indicator: {e}")

def send_whatsapp_message(to_number: str, message: str):
    if not message: return
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": message}}
    
    if not all([ACCESS_TOKEN, PHONE_NUMBER_ID]):
        print("Missing WhatsApp credentials.")
        return
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print("Sent message response:", response.json())
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

def get_rasa_response(sender_id: str, message: str):
    payload = {"sender": sender_id, "message": message}
    try:
        response = requests.post(RASA_API_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling Rasa: {e}")
        return [{"text": "Sorry, my main brain is taking a break right now. Please try again later."}]

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        return Response(content=challenge, status_code=200)
    else:
        return Response(status_code=403)

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print("Received message body:", body)

    try:
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        message_info = value.get("messages", [{}])[0]
        
        if message_info:
            from_number = message_info["from"]
            msg_body = message_info.get("text", {}).get("body")
            message_id = message_info.get("id")

            show_typing_indicator(from_number)
            

            if message_id: mark_message_as_read(message_id)
            
            if msg_body:
                rasa_response = get_rasa_response(from_number, msg_body)
                for reply in rasa_response:
                    send_whatsapp_message(from_number, reply.get("text"))

    except Exception as e:
        print(f"Error processing webhook: {e}")
        pass

    return Response(status_code=200)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)