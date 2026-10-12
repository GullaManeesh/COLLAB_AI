import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.middleware import authentication
from app.services import auth_service


class AuthenticationDependencyTests(unittest.TestCase):
    def test_missing_cookie_returns_401(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(authentication.get_current_user(None))

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
                asyncio.run(authentication.get_current_user("invalid-token"))

        self.assertEqual(raised.exception.status_code, 401)

    def test_deleted_user_returns_401(self):
        with patch.object(
            authentication,
            "get_user_from_session_token",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user("valid-session"))

        self.assertEqual(raised.exception.status_code, 401)

    def test_database_failure_returns_503(self):
        with patch.object(
            authentication,
            "get_user_from_session_token",
            new=AsyncMock(side_effect=PyMongoError("database unavailable")),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(authentication.get_current_user("raw-token"))

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
