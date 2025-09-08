# actions/actions.py
import os
import datetime
import sqlite3
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.executor import CollectingDispatcher

# Make sure to run: pip install thefuzz sentence-transformers torch
from sentence_transformers import SentenceTransformer, util
from thefuzz import process

# -----------------------------------------------------------------------------
# --- ADVANCED FALLBACK ACTION ---
# -----------------------------------------------------------------------------
class ActionAdvancedFallback(Action):

    def name(self) -> Text:
        return "action_advanced_fallback"

    def __init__(self):
        super().__init__()
        # Load the local sentence transformer model once when the action server starts
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Define your business's knowledge base (questions and answers)
        self.knowledge_base = {
            "ask_hours": {
                "questions": [
                    "What are your hours?", "When are you open?", "What are your business hours?",
                    "When do you close?", "Timings please"
                ],
                "answer": "We are open from 9 AM to 6 PM, Monday through Saturday."
            },
            "ask_location": {
                "questions": [
                    "Where are you located?", "What is your address?", "Where is your office?"
                ],
                "answer": "You can find us at 123 Tech Park, Ahmedabad, Gujarat. Here is a direct link on Google Maps: https://maps.google.com/?q=123+Tech+Park+Ahmedabad"
            }
        }

        # Pre-compute the embeddings for our knowledge base questions for efficiency
        self.question_embeddings = {
            intent: self.model.encode(data["questions"], convert_to_tensor=True)
            for intent, data in self.knowledge_base.items()
        }

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get('text')
        
        if not user_message:
            return []

        # --- 1. Semantic Search ---
        user_embedding = self.model.encode(user_message, convert_to_tensor=True)
        best_match_intent = None
        highest_similarity = 0.0

        for intent, embeddings in self.question_embeddings.items():
            cos_scores = util.cos_sim(user_embedding, embeddings)[0]
            max_score = max(cos_scores)
            if max_score > highest_similarity:
                highest_similarity = max_score
                best_match_intent = intent

        # If we find a very similar question semantically, answer it
        if highest_similarity > 0.7:
            answer = self.knowledge_base[best_match_intent]["answer"]
            dispatcher.utter_message(text=answer)
            return []

        # --- 2. Final Fallback (The Guardrail) ---
        dispatcher.utter_message(text="I'm sorry, that question is outside of my current business knowledge. I can assist with our hours and location.")
        return []

# -----------------------------------------------------------------------------
# -- Your other existing actions --
# -----------------------------------------------------------------------------
class ActionTellTime(Action):
    def name(self) -> Text:
        return "action_tell_time"
    
    def run(self, dispatcher, tracker, domain):
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        dispatcher.utter_message(text=f"The current time is {current_time}.")
        return []

class ActionCheckHours(Action):
    def name(self) -> Text:
        return "action_check_hours"
    
    def run(self, dispatcher, tracker, domain):
        day_entity = next(tracker.get_latest_entity_values("day"), None)
        reply_text = "We are open from 9 AM to 6 PM, Monday through Saturday."
        if day_entity:
            day = day_entity.lower()
            if "sunday" in day:
                reply_text = "Sorry, we are closed on Sundays."
            elif "saturday" in day:
                reply_text = "Yes! We are open from 9 AM to 6 PM on Saturdays."
        dispatcher.utter_message(text=reply_text)
        return []

# -----------------------------------------------------------------------------
# --- APPOINTMENT FORM VALIDATION ACTION ---
# -----------------------------------------------------------------------------
class ValidateAppointmentForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_appointment_form"

    def validate_appointment_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate appointment_date value."""
        # In a real bot, you'd parse and validate the date here.
        print(f"Validated date: {value}")
        return {"appointment_date": value}

    def validate_appointment_time(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate appointment_time value and save to database upon success."""
        date = tracker.get_slot("appointment_date")
        
        if value:
            user_id = tracker.sender_id
            print(f"--- SAVING APPOINTMENT TO DATABASE ---")
            print(f"User: {user_id}, Date: {date}, Time: {value}")
            
            conn = None # Initialize conn to None
            try:
                conn = sqlite3.connect('appointments.db')
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS appointments (
                        id INTEGER PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        date TEXT NOT NULL,
                        time TEXT NOT NULL
                    )
                ''')
                cursor.execute(
                    "INSERT INTO appointments (user_id, date, time) VALUES (?, ?, ?)",
                    (user_id, date, value)
                )
                conn.commit()
                print("--- APPOINTMENT SAVED SUCCESSFULLY ---")
            
            except Exception as e:
                print(f"Database error: {e}")
            finally:
                # This check prevents the "referenced before assignment" error
                if conn:
                    conn.close()
            
            return {"appointment_time": value}
        
        return {"appointment_time": None}