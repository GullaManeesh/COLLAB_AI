from fastapi import APIRouter, status

from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.agents import SummarizerRequest
from app.services.agent_execution_service import execute_summarizer_request, recover_stale_agent_runs

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["Agents"])


@router.post("/summarizer", status_code=status.HTTP_200_OK)
async def summarize_workspace_route(
    workspace_id: str,
    payload: SummarizerRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await execute_summarizer_request(workspace_id, payload, user)
