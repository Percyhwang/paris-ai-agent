from fastapi import HTTPException

from parser_api.parsers.llm import LLMStructuredOutputError
from parser_api.schemas import AgentRunRequest, AgentRunResponse
from parser_api.services.orchestration_service import default_orchestrator


def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    try:
        return default_orchestrator.run(payload)
    except LLMStructuredOutputError as exc:
        raise HTTPException(status_code=500, detail=f"Parser failed: {exc}") from exc
