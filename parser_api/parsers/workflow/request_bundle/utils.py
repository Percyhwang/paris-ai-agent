from parser_api.intents import Intent
from parser_api.schemas import SharedContextPayload


def make_action_ref(intent: Intent | str, order: int) -> str:
    intent_value = intent.value if isinstance(intent, Intent) else str(intent)
    return f"step_{order}_{intent_value.lower()}"


def infer_action_dependencies(
    actions: list[Intent],
    shared_context: SharedContextPayload,
) -> list[list[str]]:
    dependencies: list[list[str]] = []
    prior_refs: list[tuple[Intent, str]] = []
    has_existing_trip_id = bool(shared_context.trip_id)

    for index, intent in enumerate(actions, start=1):
        action_ref = make_action_ref(intent, index)
        current_dependencies: list[str] = []

        if intent is Intent.MODIFY_PLAN and not has_existing_trip_id:
            for prior_intent, prior_ref in reversed(prior_refs):
                if prior_intent is Intent.CREATE_PLAN:
                    current_dependencies.append(prior_ref)
                    break

        dependencies.append(current_dependencies)
        prior_refs.append((intent, action_ref))

    return dependencies
