
from app.services import invitation_service


async def resolve_invitation_controller(token):
    return await invitation_service.resolve_invitation_token(token)


async def accept_invitation_token_controller(token, user):
    return await invitation_service.accept_invitation_token(token, user)


async def list_workspace_invitations_controller(workspace_id, user):
    return await invitation_service.list_workspace_invitations(workspace_id, user)


async def revoke_workspace_invitation_controller(workspace_id, invitation_id, user):
    return await invitation_service.revoke_workspace_invitation(workspace_id, invitation_id, user)


async def invite_teammate_controller(workspace_id, payload, user):
    return await invitation_service.invite_teammate(
        workspace_id, str(payload.email), user
    )


async def accept_invitation_controller(invitation_id, user):
    return await invitation_service.respond_to_invitation(
        invitation_id, user, accept=True
    )


async def decline_invitation_controller(invitation_id, user):
    return await invitation_service.respond_to_invitation(
        invitation_id, user, accept=False
    )
