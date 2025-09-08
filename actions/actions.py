# actions/actions.py
import os
import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

# Import our new libraries
from sentence_transformers import SentenceTransformer, util
from thefuzz import process

# -----------------------------------------------------------------------------
# --- ADVANCED FALLBACK ACTION ---
# This is the new "brain" that uses local models instead of external APIs
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
                "answer": "You can find us at 123 Tech Park, Ahmedabad, Gujarat."
            },
            # You can add more knowledge here, for example:
            # "ask_services": {
            #     "questions": ["What services do you offer?", "What can you do for me?"],
            #     "answer": "We offer a wide range of services including..."
            # }
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
        if highest_similarity > 0.75: # High confidence threshold
            answer = self.knowledge_base[best_match_intent]["answer"]
            dispatcher.utter_message(text=f"I think you're asking about our {best_match_intent.replace('_', ' ')}. Here is the answer: {answer}")
            return []

        # --- 2. Fuzzy Search (for typos) ---
        all_questions = [q for data in self.knowledge_base.values() for q in data["questions"]]
        best_fuzzy_match, fuzzy_score = process.extractOne(user_message, all_questions)

        if fuzzy_score > 85: # High confidence threshold for typos
            for intent, data in self.knowledge_base.items():
                if best_fuzzy_match in data["questions"]:
                    answer = data["answer"]
                    dispatcher.utter_message(text=f"Did you mean to ask about '{best_fuzzy_match}'? If so, here is the answer: {answer}")
                    return []

        # --- 3. Final Fallback (The Guardrail) ---
        dispatcher.utter_message(text="I'm sorry, that question is outside of my current business knowledge. I can assist with our hours and location.")

        return []

# -----------------------------------------------------------------------------
# -- Your other existing actions --
# -----------------------------------------------------------------------------
class ActionTellTime(Action):
    def name(self) -> Text: return "action_tell_time"
    # ... (rest of the code is the same) ...
    def run(self, dispatcher, tracker, domain):
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        dispatcher.utter_message(text=f"The current time is {current_time}.")
        return []

class ActionCheckHours(Action):
    def name(self) -> Text: return "action_check_hours"
    # ... (rest of the code is the same) ...
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