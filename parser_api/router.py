from parser_api.schemas import AgentRunRequest, AgentRunResponse
from parser_api.services.agent_service import run_agent


def agent_run(payload: AgentRunRequest) -> AgentRunResponse:
    return run_agent(payload)
