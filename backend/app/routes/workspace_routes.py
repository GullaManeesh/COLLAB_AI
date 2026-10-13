
from fastapi import APIRouter, Query, status

from app.controllers import workspace_controller as controller
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.workspaces import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.create_workspace_controller(payload, user)


@router.get("")
async def list_workspaces(user: CurrentUser):
    return await controller.list_workspaces_controller(user)


@router.get("/teammates/search")
async def search_teammates(
    user: CurrentUser,
    q: str = Query(min_length=2, max_length=100),
):
    suggestions = await controller.search_teammates_controller(q, user)
    return {"suggestions": suggestions}


@router.get("/{workspace_id}")
async def workspace_details(workspace_id: str, user: CurrentUser):
    return await controller.get_workspace_details_controller(workspace_id, user)


@router.patch("/{workspace_id}")
async def edit_workspace(
    workspace_id: str,
    payload: UpdateWorkspaceRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.update_workspace_controller(
        workspace_id, payload, user
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_200_OK)
async def remove_workspace(
    workspace_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.delete_workspace_controller(workspace_id, user)


@router.delete("/{workspace_id}/members/{member_user_id}")
async def remove_workspace_member(
    workspace_id: str,
    member_user_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.remove_workspace_member_controller(workspace_id, member_user_id, user)
