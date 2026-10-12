
from app.services import invitation_service


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
