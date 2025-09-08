# actions/actions.py
import os
import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

# Make sure to run: pip install thefuzz sentence-transformers torch
from sentence_transformers import SentenceTransformer, util
from thefuzz import process

# -----------------------------------------------------------------------------
# --- ADVANCED FALLBACK ACTION (with "Did you mean...?" logic) ---
# -----------------------------------------------------------------------------
class ActionAdvancedFallback(Action):

    def name(self) -> Text:
        return "action_advanced_fallback"

    def __init__(self):
        super().__init__()
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
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
        # Flatten the questions for easier lookup later
        self.flat_knowledge_base = []
        for intent, data in self.knowledge_base.items():
            for question in data["questions"]:
                self.flat_knowledge_base.append({"intent": intent, "question": question})

        # Pre-compute the embeddings for our knowledge base questions
        self.question_embeddings = self.model.encode([item["question"] for item in self.flat_knowledge_base], convert_to_tensor=True)

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get('text')
        if not user_message: return []

        user_embedding = self.model.encode(user_message, convert_to_tensor=True)
        
        # Calculate cosine similarity between user message and all known questions
        cos_scores = util.cos_sim(user_embedding, self.question_embeddings)[0]
        
        # Get the top 3 best matches
        top_results = cos_scores.topk(3)

        highest_similarity = top_results.values[0].item()
        
        # High Confidence: Give a direct answer
        if highest_similarity > 0.75:
            best_match_index = top_results.indices[0].item()
            matched_intent = self.flat_knowledge_base[best_match_index]["intent"]
            answer = self.knowledge_base[matched_intent]["answer"]
            dispatcher.utter_message(text=answer)
            return []
        
        # Medium Confidence: Ask for clarification ("Did you mean...?")
        elif highest_similarity > 0.55:
            suggestions = []
            for i in range(len(top_results.values)):
                match_index = top_results.indices[i].item()
                question = self.flat_knowledge_base[match_index]["question"]
                suggestions.append(f"{i+1}. {question}")
            
            suggestions_text = "\n".join(suggestions)
            reply_text = f"I'm not completely sure what you mean. Did you want to ask one of these questions?\n{suggestions_text}"
            dispatcher.utter_message(text=reply_text)
            return []

        # Low Confidence: Final Fallback
        dispatcher.utter_message(text="I'm sorry, that question is outside of my current business knowledge. I can assist with our hours and location.")
        return []

# --- Your other actions (ActionTellTime, ActionCheckHours) remain below ---
# ... (rest of the file is the same)
class ActionTellTime(Action):
    def name(self) -> Text: return "action_tell_time"
    # ...
    def run(self, dispatcher, tracker, domain):
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        dispatcher.utter_message(text=f"The current time is {current_time}.")
        return []

class ActionCheckHours(Action):
    def name(self) -> Text: return "action_check_hours"
    # ...
    def run(self, dispatcher, tracker, domain):
        day_entity = next(tracker.get_latest_entity_values("day"), None)
        reply_text = "We are open from 9 AM to 6 PM, Monday through Saturday."
        if day_entity:
            day = day_entity.lower()
            if "sunday" or "Sunday" or "SUNDAY" in day:
                reply_text = "Sorry, we are closed on Sundays."
            elif "saturday" or "Saturday" or "SATURDAY" in day:
                reply_text = "Yes! We are open from 9 AM to 6 PM on Saturdays."
        dispatcher.utter_message(text=reply_text)
        return []