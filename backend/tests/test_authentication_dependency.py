import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pymongo.errors import PyMongoError
from starlette.requests import Request

from app.middleware import authentication
from app.services import auth_service


def make_request(cookie: str | None = None) -> Request:
    headers = [(b"origin", b"https://collabai.online")]
    if cookie:
        headers.append((b"cookie", f"collabai_session={cookie}".encode()))
    return Request({
        "type": "http", "http_version": "1.1", "method": "GET", "scheme": "https",
        "path": "/api/workspaces", "raw_path": b"/api/workspaces", "query_string": b"",
        "headers": headers, "client": ("127.0.0.1", 12345), "server": ("localhost", 443),
    })


class AuthenticationDependencyTests(unittest.TestCase):
    def test_missing_cookie_returns_401(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(authentication.get_current_user(make_request(), None))

        self.assertEqual(raised.exception.status_code, 401)

    def test_valid_session_queries_hashed_token_and_returns_user(self):
        stored_user = {"_id": "user-id", "email": "user@example.com"}
        sessions = SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "token_hash": auth_service.hash_session_token("raw-token"),
                    "user_id": "user-id",
                }
            )
        )
        users = SimpleNamespace(find_one=AsyncMock(return_value=stored_user))
        database = SimpleNamespace(sessions=sessions, users=users)

        with patch.object(auth_service, "get_database", return_value=database):
            result = asyncio.run(
                auth_service.get_user_from_session_token("raw-token")
            )

        self.assertEqual(result, stored_user)
        query = sessions.find_one.await_args.args[0]
        self.assertEqual(query["token_hash"], auth_service.hash_session_token("raw-token"))
        self.assertIn("expires_at", query)
        users.find_one.assert_awaited_once_with({"_id": "user-id"})

    def test_invalid_session_returns_401(self):
        with patch.object(
            authentication,
            "get_user_from_session_token",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user(make_request("invalid-token"), "invalid-token"))

        self.assertEqual(raised.exception.status_code, 401)

    def test_deleted_user_returns_401(self):
        with patch.object(
            authentication,
            "get_user_from_session_token",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user(make_request("valid-session"), "valid-session"))

        self.assertEqual(raised.exception.status_code, 401)

    def test_database_failure_returns_503(self):
        with patch.object(
            authentication,
            "get_user_from_session_token",
            new=AsyncMock(side_effect=PyMongoError("database unavailable")),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user(make_request("raw-token"), "raw-token"))

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
