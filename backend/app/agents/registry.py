from app.agents.base import Agent

_AGENTS: dict[str, Agent] = {}


def register_agent(agent: Agent) -> Agent:
    if not agent.agent_type:
        raise ValueError("An agent must have an agent_type")
    _AGENTS[agent.agent_type] = agent
    return agent


def get_agent(agent_type: str) -> Agent:
    try:
        return _AGENTS[agent_type]
    except KeyError as exc:
        raise LookupError(f"Agent '{agent_type}' is not registered") from exc
