from typing import Optional

from parser_api.intents import Intent
from parser_api.parsers.llm import augment_payload_with_llm
from parser_api.parsers.workflow.request_bundle.detection import detect_requested_actions
from parser_api.parsers.workflow.request_bundle.utils import infer_action_dependencies
from parser_api.parsers.workflow.shared_context.parser import parse_shared_context
from parser_api.schemas import Clarify, RequestBundleAction, RequestBundlePayload


class RequestBundleParser:
    intent = Intent.REQUEST_BUNDLE

    def parse(self, message: str, context: Optional[dict] = None) -> RequestBundlePayload:
        payload = RequestBundlePayload()
        payload.shared_context = parse_shared_context(message, context)

        actions = detect_requested_actions(message, context)
        dependencies = infer_action_dependencies(actions, payload.shared_context)
        payload.actions = [
            RequestBundleAction(
                intent=action.value,
                order=index + 1,
                depends_on=dependencies[index],
            )
            for index, action in enumerate(actions)
        ]
        payload = augment_payload_with_llm(payload, message, context)

        missing_fields: list[str] = []
        if not payload.actions:
            missing_fields.append("actions")

        payload.clarify = Clarify(
            needed=len(missing_fields) > 0,
            missing_fields=missing_fields,
        )
        return payload


REQUEST_BUNDLE_PARSER = RequestBundleParser()


def parse_request_bundle(message: str, context: Optional[dict] = None) -> RequestBundlePayload:
    return REQUEST_BUNDLE_PARSER.parse(message, context)
