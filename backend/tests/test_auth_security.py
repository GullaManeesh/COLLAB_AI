import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response
from pymongo.errors import PyMongoError
from pydantic import ValidationError

from app import main
from app.controllers import auth_controller
from app.database.mongodb import get_database
from app.middleware import authentication
from app.middleware.csrf import require_csrf_token
from app.models.user_model import UsernameRequest
from app.routes import auth_routes as auth_router
from app.services import auth_service
from app.services.auth_service import hash_session_token
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request


def make_csrf_request(cookie_token: str, header_token: str) -> Request:
    return Request({
        "type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
        "path": "/api/workspaces", "raw_path": b"/api/workspaces", "query_string": b"",
        "headers": [
            (b"cookie", f"collabai_csrf={cookie_token}".encode()),
            (b"x-csrf-token", header_token.encode()),
        ],
        "client": ("127.0.0.1", 12345), "server": ("localhost", 443),
    })


class AuthSecurityTests(unittest.TestCase):
    def test_csrf_requires_matching_cookie_and_header(self):
        valid_request = make_csrf_request("csrf-value", "csrf-value")
        require_csrf_token(valid_request)

        invalid_request = make_csrf_request("csrf-value", "wrong-value")
        with self.assertRaises(HTTPException) as raised:
            require_csrf_token(invalid_request)
        self.assertEqual(raised.exception.status_code, 403)

    def test_username_schema_rejects_invalid_values(self):
        with self.assertRaises(ValidationError):
            UsernameRequest(username="Bad Name")
        with self.assertRaises(ValidationError):
            UsernameRequest(username="ab")
        self.assertEqual(UsernameRequest(username="valid_user").username, "valid_user")

    def test_valid_credential_claims_are_returned(self):
        claims = {"sub": "google-sub", "email": "user@example.com", "email_verified": True}
        with patch.object(auth_service.id_token, "verify_oauth2_token", return_value=claims):
            self.assertEqual(auth_service.verify_credential("credential"), claims)

    def test_invalid_credential_is_rejected(self):
        with patch.object(
            auth_service.id_token,
            "verify_oauth2_token",
            side_effect=ValueError("invalid token"),
        ):
            with self.assertRaises(HTTPException) as raised:
                auth_service.verify_credential("invalid")
        self.assertEqual(raised.exception.status_code, 401)

    def test_session_restoration_returns_user(self):
        stored_user = {
            "_id": "user-id",
            "email": "user@example.com",
            "username": "valid_user",
            "email_verified": True,
        }
        result = asyncio.run(auth_controller.current_user(Response(), stored_user))
        self.assertEqual(result.user.username, "valid_user")
        self.assertFalse(result.needs_username)

    def test_duplicate_username_is_returned_as_conflict(self):
        with patch.object(
            auth_service,
            "update_username",
            new=AsyncMock(side_effect=DuplicateKeyError("duplicate username")),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    auth_controller.save_username(
                        UsernameRequest(username="taken_name"),
                        {"_id": "user-id"},
                    )
                )
        self.assertEqual(raised.exception.status_code, 409)

    def test_logout_requires_csrf_and_deletes_server_session(self):
        sessions = SimpleNamespace(delete_one=AsyncMock())
        fake_database = SimpleNamespace(sessions=sessions)
        response = Response()

        with patch.object(auth_service, "get_database", return_value=fake_database):
            asyncio.run(
                auth_controller.logout(
                    response,
                    "raw-session-token",
                )
            )

        sessions.delete_one.assert_awaited_once_with(
            {"token_hash": hash_session_token("raw-session-token")}
        )
        set_cookies = "\n".join(response.headers.getlist("set-cookie"))
        self.assertIn("collabai_session=", set_cookies)
        self.assertIn("collabai_csrf=", set_cookies)

    def test_logout_database_failure_is_not_reported_as_success(self):
        with patch.object(
            auth_service,
            "revoke_session",
            new=AsyncMock(side_effect=PyMongoError("database unavailable")),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(auth_controller.logout(Response(), "raw-token"))
        self.assertEqual(raised.exception.status_code, 503)

    def test_current_user_database_failure_returns_service_unavailable(self):
        with patch.object(
            auth_service,
            "get_user_from_session_token",
            new=AsyncMock(side_effect=PyMongoError("database unavailable")),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user(
                    Request({
                        "type": "http", "http_version": "1.1", "method": "GET", "scheme": "https",
                        "path": "/", "raw_path": b"/", "query_string": b"", "headers": [],
                        "client": ("127.0.0.1", 12345), "server": ("localhost", 443),
                    }),
                    "raw-token",
                ))
        self.assertEqual(raised.exception.status_code, 503)

    def test_lifespan_closes_database_when_index_creation_fails(self):
        close_database = AsyncMock()

        async def fail_indexes():
            raise RuntimeError("index creation failed")

        with patch.object(main, "connect_to_mongodb", new=AsyncMock()), patch.object(
            main, "create_indexes", new=fail_indexes
        ), patch.object(main, "close_mongodb_connection", new=close_database):
            with self.assertRaises(RuntimeError):
                asyncio.run(self._run_lifespan())

        close_database.assert_awaited_once()

    async def _run_lifespan(self):
        async with main.lifespan(main.app):
            self.fail("lifespan should not yield when index creation fails")


if __name__ == "__main__":
    unittest.main()
