from fastapi import APIRouter, status

from app.controllers import invitation_controller as controller
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.invitations_schema import CreateInvitationRequest, InvitationResponse
from app.schemas.workspaces import InvitationActionResponse

router = APIRouter(prefix="/workspaces", tags=["Invitations"])


@router.post(
    "/{workspace_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationResponse,
)
async def invite_teammate(
    workspace_id: str,
    payload: CreateInvitationRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> InvitationResponse:
    result = await controller.invite_teammate_controller(
        workspace_id, payload, user
    )
    return InvitationResponse(**result)


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=InvitationActionResponse,
)
async def accept_invitation(
    invitation_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> InvitationActionResponse:
    result = await controller.accept_invitation_controller(invitation_id, user)
    return InvitationActionResponse(**result)


@router.post(
    "/invitations/{invitation_id}/decline",
    response_model=InvitationActionResponse,
)
async def decline_invitation(
    invitation_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> InvitationActionResponse:
    result = await controller.decline_invitation_controller(invitation_id, user)
    return InvitationActionResponse(**result)
