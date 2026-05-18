# Codex Working Rules

This project is a Hybrid Travel Planning Agent, not a growing collection of rule-based travel recommendations.

The backend should evolve toward a clear separation of roles:

```text
User Request
-> Planning Brief
-> Memory Retrieval
-> Draft Plan
-> Evaluator
-> Replanner
-> Route Optimizer
-> Evaluator
-> MongoDB Persist
-> Feedback Memory Update
```

## Architecture Goals

- Build a Hybrid Travel Planning Agent that separates Planning Brief, Memory, Evaluator, Replanner, Route Optimizer, and persistence responsibilities.
- Do not keep adding ad hoc parser or optimizer rules for every failed sentence.
- Use structured `failure_type` values for evaluation failures.
- Use structured `repair_operation` functions for deterministic repairs.
- Keep existing API response shapes compatible unless a task explicitly requires a versioned response change.
- Prefer small, safe changes over large rewrites.

## Service Boundaries

- `route_optimizer_service.py` should handle objective calculations only: distance, travel time, route legs, schedule placement, and route feasibility.
- `plan_evaluator_service.py` should evaluate whether a plan satisfies user requests, hard constraints, and soft preferences.
- `plan_replanner_service.py` should modify an itinerary using Evaluator failures and repair operations.
- Memory retrieval and update should provide context and feedback history, not hard-code recommendation behavior.

## Constraints

- Hard constraints must be enforced by code.
- Soft preferences may be improved by an LLM Replanner.
- `must_avoid`, `must_include`, `final_anchor`, and `ordered_anchors` must not be broken.
- LLM-produced changes must pass code-based constraint checks before being accepted.
- Do not add broad new keyword `if` rules unless they are part of a structured parser/evaluator contract.
- Classify failures using `failure_type`; repair them using `repair_operation`.

## Testing

- Run relevant tests after changing backend agent logic.
- Tests must be deterministic and must not call real LLM APIs.
- Preserve existing test fixtures and API response compatibility whenever possible.

