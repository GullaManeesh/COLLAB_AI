from fastapi import APIRouter, status

from app.controllers import invitation_controller as controller
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.invitations_schema import (
    CreateInvitationRequest,
    InvitationListItem,
    InvitationPreviewResponse,
    InvitationResponse,
    InvitationTokenRequest,
)
from app.schemas.workspaces import InvitationActionResponse

router = APIRouter(prefix="/workspaces", tags=["Invitations"])


@router.post("/invitations/resolve", response_model=InvitationPreviewResponse)
async def resolve_invitation(payload: InvitationTokenRequest):
    return await controller.resolve_invitation_controller(payload.token)


@router.post("/invitations/accept-token", response_model=InvitationActionResponse)
async def accept_invitation_token(
    payload: InvitationTokenRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> InvitationActionResponse:
    result = await controller.accept_invitation_token_controller(payload.token, user)
    return InvitationActionResponse(**result)


@router.get("/{workspace_id}/invitations", response_model=list[InvitationListItem])
async def list_invitations(workspace_id: str, user: CurrentUser):
    return await controller.list_workspace_invitations_controller(workspace_id, user)


@router.delete("/{workspace_id}/invitations/{invitation_id}")
async def revoke_invitation(
    workspace_id: str,
    invitation_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.revoke_workspace_invitation_controller(workspace_id, invitation_id, user)


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
