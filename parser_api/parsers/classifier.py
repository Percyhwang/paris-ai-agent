from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.workflow.request_bundle.detection import detect_primary_intent


class IntentClassifier:
    def classify(self, message: str, context: Optional[dict] = None) -> Intent:
        return detect_primary_intent(message, context)


default_intent_classifier = IntentClassifier()


def extract_intent(message: str, context: Optional[dict] = None) -> Intent:
    return default_intent_classifier.classify(message, context)
