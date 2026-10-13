
from app.services import workspace_service


async def create_workspace_controller(payload, user):
    return await workspace_service.create_workspace(payload, user)


async def list_workspaces_controller(user):
    return await workspace_service.list_workspaces(user)


async def get_workspace_details_controller(workspace_id, user):
    return await workspace_service.get_workspace_details(workspace_id, user)


async def update_workspace_controller(workspace_id, payload, user):
    return await workspace_service.update_workspace(workspace_id, payload, user)


async def delete_workspace_controller(workspace_id, user):
    return await workspace_service.delete_workspace(workspace_id, user)


async def remove_workspace_member_controller(workspace_id, member_user_id, user):
    return await workspace_service.remove_workspace_member(workspace_id, member_user_id, user)


async def search_teammates_controller(query, user):
    return await workspace_service.search_teammates(query, user)
