
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
)
from app.services.document_service import (
    delete_document,
    get_document,
    list_documents,
    search_workspace_chunks,
    upload_document,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/documents",
    tags=["Documents"],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def upload_document_route(
    workspace_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
    file: UploadFile = File(...),
) -> DocumentResponse:
    filename = (file.filename or "").strip()
    extension = (
        "." + filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Supported formats: PDF, DOCX, TXT, and MD",
        )

    file_size = file.size
    file_source = file.file
    if file_size is None:
        # Older Starlette versions may not expose UploadFile.size. In that
        # fallback, keep the existing strict limit while reading at most 10 MB.
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        file_size = len(file_bytes)
        file_source = file_bytes

    if file_size == 0:
        await file.close()
        raise HTTPException(status_code=400, detail="The file is empty")

    if file_size > MAX_UPLOAD_BYTES:
        await file.close()
        raise HTTPException(
            status_code=413,
            detail="Maximum file size is 10 MB",
        )

    if file_source is file.file:
        await file.seek(0)
    try:
        result = await upload_document(
            workspace_id=workspace_id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_source,
            file_size=file_size,
            user=user,
        )
    finally:
        await file.close()
    return DocumentResponse(**result)


@router.get("", response_model=DocumentListResponse)
async def list_documents_route(
    workspace_id: str,
    user: CurrentUser,
) -> DocumentListResponse:
    result = await list_documents(workspace_id, user)
    return DocumentListResponse(**result)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_route(
    workspace_id: str,
    document_id: str,
    user: CurrentUser,
) -> DocumentResponse:
    result = await get_document(workspace_id, document_id, user)
    return DocumentResponse(**result)


@router.delete("/{document_id}")
async def delete_document_route(
    workspace_id: str,
    document_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await delete_document(workspace_id, document_id, user)


@router.post(
    "/search",
    response_model=DocumentSearchResponse,
)
async def search_documents_route(
    workspace_id: str,
    payload: DocumentSearchRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> DocumentSearchResponse:
    result = await search_workspace_chunks(
        workspace_id=workspace_id,
        query=payload.query,
        limit=payload.limit,
        user=user,
    )
    return DocumentSearchResponse(**result)
