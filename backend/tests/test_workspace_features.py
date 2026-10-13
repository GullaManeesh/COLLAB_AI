import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.workspaces import CreateWorkspaceRequest, UpdateWorkspaceRequest
from app.services import email_service, invitation_service, notification_service, workspace_service


class WorkspaceServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.user_id = ObjectId()
        self.user = {
            "_id": self.user_id,
            "email": "owner@collabai.com",
            "name": "Workspace Owner",
        }
        self.other_user_id = ObjectId()
        self.other_user = {
            "_id": self.other_user_id,
            "email": "member@collabai.com",
            "name": "Team Member",
        }

    def test_create_workspace_success(self):
        ws_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ws_id))
        mock_db.channels.insert_many = AsyncMock()
        created_doc = {
            "_id": ws_id,
            "name": "New Team Room",
            "description": "Room description",
            "owner_id": self.user_id,
            "members": [{"user_id": self.user_id, "role": "owner"}],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.workspaces.find_one = AsyncMock(return_value=created_doc)

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            req = CreateWorkspaceRequest(name="New Team Room", description="Room description")
            result = asyncio.run(workspace_service.create_workspace(req, self.user))

        self.assertEqual(result["id"], str(ws_id))
        self.assertEqual(result["name"], "New Team Room")
        self.assertEqual(result["role"], "owner")
        mock_db.channels.insert_many.assert_awaited_once()

    def test_list_workspaces_owned_or_member(self):
        ws_id = ObjectId()
        doc = {
            "_id": ws_id,
            "name": "Collab Workspace",
            "description": "Desc",
            "owner_id": self.user_id,
            "members": [{"user_id": self.user_id, "role": "owner"}],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        async def async_iter():
            yield doc

        cursor_mock = MagicMock()
        cursor_mock.__aiter__ = lambda s: async_iter()
        cursor_mock.sort = MagicMock(return_value=cursor_mock)

        mock_db = MagicMock()
        mock_db.workspaces.find = MagicMock(return_value=cursor_mock)

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            result = asyncio.run(workspace_service.list_workspaces(self.user))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["workspaces"][0]["id"], str(ws_id))

    def test_update_workspace_owner_only(self):
        ws_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        updated_doc = {
            "_id": ws_id,
            "name": "Updated Name",
            "description": "Updated Desc",
            "owner_id": self.user_id,
            "members": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.workspaces.find_one = AsyncMock(return_value=updated_doc)

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            payload = UpdateWorkspaceRequest(name="Updated Name", description="Updated Desc")
            result = asyncio.run(workspace_service.update_workspace(str(ws_id), payload, self.user))

        self.assertEqual(result["name"], "Updated Name")

    def test_update_workspace_non_owner_forbidden(self):
        ws_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
        # Workspace exists, but owned by someone else
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": ws_id, "owner_id": ObjectId()})

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            payload = UpdateWorkspaceRequest(name="Updated Name")
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(workspace_service.update_workspace(str(ws_id), payload, self.user))
            self.assertEqual(exc.exception.status_code, 403)

    def test_delete_workspace_owner_success(self):
        ws_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": ws_id, "owner_id": self.user_id})
        mock_db.workspaces.delete_one = AsyncMock()
        mock_db.channels.delete_many = AsyncMock()
        mock_db.messages.delete_many = AsyncMock()
        mock_db.documents.delete_many = AsyncMock()
        mock_db.invitations.delete_many = AsyncMock()
        mock_db.notifications.delete_many = AsyncMock()
        mock_db.notifications.insert_many = AsyncMock()

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            result = asyncio.run(workspace_service.delete_workspace(str(ws_id), self.user))

        self.assertEqual(result["message"], "Workspace deleted successfully")
        mock_db.workspaces.delete_one.assert_awaited_once_with({"_id": ws_id})
        mock_db.channels.delete_many.assert_awaited_once_with({"workspace_id": ws_id})
        mock_db.invitations.delete_many.assert_awaited_once_with({"workspace_id": ws_id})

    def test_delete_workspace_non_owner_forbidden(self):
        ws_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": ws_id, "owner_id": ObjectId()})

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(workspace_service.delete_workspace(str(ws_id), self.user))
            self.assertEqual(exc.exception.status_code, 403)

    def test_search_teammates_excludes_self(self):
        user_b = {"_id": self.other_user_id, "email": "teammate@example.com", "name": "Teammate", "username": "team1"}
        async def async_iter():
            yield user_b

        cursor_mock = MagicMock()
        cursor_mock.__aiter__ = lambda s: async_iter()
        cursor_mock.limit = MagicMock(return_value=cursor_mock)

        mock_db = MagicMock()
        mock_db.users.find = MagicMock(return_value=cursor_mock)

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            results = asyncio.run(workspace_service.search_teammates("team", self.user))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "teammate@example.com")
        # Ensure query strictly excluded current user
        find_query = mock_db.users.find.call_args[0][0]
        self.assertEqual(find_query["$and"][0]["_id"]["$ne"], self.user_id)

    def test_remove_member_revokes_membership_and_creates_event_notification(self):
        ws_id = ObjectId()
        member_id = self.other_user_id
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={
            "_id": ws_id, "name": "AI Lab", "owner_id": self.user_id,
            "members": [{"user_id": self.user_id, "role": "owner"}, {"user_id": member_id, "role": "member"}],
        })
        mock_db.workspaces.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        mock_db.notifications.insert_one = AsyncMock()

        with patch("app.services.workspace_service.get_database", return_value=mock_db):
            result = asyncio.run(workspace_service.remove_workspace_member(str(ws_id), str(member_id), self.user))

        self.assertEqual(result["message"], "Workspace member removed")
        self.assertEqual(mock_db.workspaces.update_one.call_args.args[1]["$pull"]["members"]["user_id"], member_id)
        event = mock_db.notifications.insert_one.call_args.args[0]
        self.assertEqual(event["event_type"], "workspace.member_removed")
        self.assertEqual(event["recipient_user_id"], member_id)


class InvitationAndNotificationUnitTests(unittest.TestCase):
    def setUp(self):
        self.owner_id = ObjectId()
        self.owner = {"_id": self.owner_id, "email": "owner@collabai.com", "name": "Owner"}
        self.user_id = self.owner_id
        self.user = self.owner
        self.recipient_id = ObjectId()
        self.recipient = {"_id": self.recipient_id, "email": "invitee@collabai.com", "name": "Invitee"}
        self.ws_id = ObjectId()

    def test_invite_teammate_success(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=self.recipient)
        mock_db.invitations.find_one = AsyncMock(return_value=None)
        inv_id = ObjectId()
        mock_db.invitations.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=inv_id))
        mock_db.notifications.insert_one = AsyncMock()
        mock_db.email_outbox.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
        mock_db.email_outbox.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))

        with patch("app.services.invitation_service.get_database", return_value=mock_db), \
             patch("app.services.invitation_service.send_email", new=AsyncMock(return_value={"provider": "smtp", "status": "accepted_by_smtp", "message_id": None})):
            res = asyncio.run(invitation_service.invite_teammate(str(self.ws_id), "invitee@collabai.com", self.owner))

        self.assertEqual(res["status"], "pending")
        self.assertEqual(res["email_status"], "accepted_by_smtp")
        mock_db.notifications.insert_one.assert_awaited_once()

    def test_invite_unregistered_email_stores_only_token_hash_and_uses_configured_frontend(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=None)
        mock_db.invitations.find_one = AsyncMock(return_value=None)
        mock_db.invitations.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
        mock_db.notifications.insert_one = AsyncMock()
        mock_db.email_outbox.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
        mock_db.email_outbox.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
        email_sender = AsyncMock(return_value={"provider": "resend", "status": "accepted_by_provider", "message_id": "mail-1"})

        with patch("app.services.invitation_service.get_database", return_value=mock_db), \
             patch("app.services.invitation_service.send_email", new=email_sender), \
             patch.object(invitation_service.settings, "FRONTEND_URL", "https://collabai.online"):
            result = asyncio.run(invitation_service.invite_teammate(str(self.ws_id), " New.Person@Example.com ", self.owner))

        invite_doc = mock_db.invitations.insert_one.call_args.args[0]
        outbox_doc = mock_db.email_outbox.insert_one.call_args.args[0]
        sent_body = email_sender.call_args.args[2]
        self.assertEqual(result["email_status"], "accepted_by_provider")
        self.assertEqual(invite_doc["recipient_email"], "new.person@example.com")
        self.assertEqual(invite_doc["recipient_user_id"], None)
        self.assertEqual(len(invite_doc["token_hash"]), 64)
        self.assertNotIn("token", invite_doc)
        self.assertNotIn("body", outbox_doc)
        self.assertIn("https://collabai.online/invite#", sent_body)
        self.assertIn("expires", sent_body)
        self.assertEqual(mock_db.notifications.insert_one.await_count, 0)

    def test_invitation_token_preview_and_acceptance_require_matching_verified_email(self):
        token = "secure-token-value"
        invitation = {
            "_id": ObjectId(), "workspace_id": self.ws_id,
            "workspace_name": "AI Lab", "sender_user_id": self.owner_id,
            "sender_name": "Owner", "recipient_email": self.recipient["email"],
            "token_hash": invitation_service._hash_invitation_token(token),
            "status": "pending", "expires_at": datetime.now(timezone.utc) + timedelta(days=2),
        }
        workspace = {"_id": self.ws_id, "name": "AI Lab", "members": []}
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value=invitation)
        mock_db.workspaces.find_one = AsyncMock(return_value=workspace)
        mock_db.invitations.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
        mock_db.workspaces.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        mock_db.notifications.update_many = AsyncMock()
        mock_db.notifications.insert_one = AsyncMock()

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            preview = asyncio.run(invitation_service.resolve_invitation_token(token))
            with self.assertRaises(HTTPException) as mismatch:
                asyncio.run(invitation_service.accept_invitation_token(token, {"_id": ObjectId(), "email": "other@example.com", "email_verified": True}))
            self.assertEqual(mismatch.exception.status_code, 403)
            result = asyncio.run(invitation_service.accept_invitation_token(token, {
                "_id": self.recipient_id, "email": self.recipient["email"], "email_verified": True, "name": "Invitee",
            }))

        self.assertEqual(preview["workspace_name"], "AI Lab")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["workspace_id"], str(self.ws_id))
        self.assertEqual(mock_db.workspaces.update_one.await_count, 1)

    def test_concurrent_invitation_acceptance_only_adds_member_once(self):
        token = "race-safe-token"
        invitation = {
            "_id": ObjectId(), "workspace_id": self.ws_id, "recipient_email": self.recipient["email"],
            "token_hash": invitation_service._hash_invitation_token(token), "status": "pending",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=2),
        }
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value=invitation)
        mock_db.invitations.update_one = AsyncMock(side_effect=[
            SimpleNamespace(modified_count=1), SimpleNamespace(modified_count=0),
        ])
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "members": []})
        mock_db.workspaces.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        mock_db.notifications.update_many = AsyncMock()
        mock_db.notifications.insert_one = AsyncMock()
        user = {"_id": self.recipient_id, "email": self.recipient["email"], "email_verified": True}

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            first = asyncio.run(invitation_service.accept_invitation_token(token, user))
            with self.assertRaises(HTTPException) as duplicate:
                asyncio.run(invitation_service.accept_invitation_token(token, user))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(duplicate.exception.status_code, 409)
        self.assertEqual(mock_db.workspaces.update_one.await_count, 1)

    def test_acceptance_rejects_user_who_is_already_a_member(self):
        token = "already-member-token"
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value={
            "_id": ObjectId(), "workspace_id": self.ws_id, "recipient_email": self.recipient["email"],
            "token_hash": invitation_service._hash_invitation_token(token), "status": "pending",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        })
        mock_db.invitations.update_one = AsyncMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={
            "_id": self.ws_id, "name": "AI Lab", "members": [{"user_id": self.recipient_id}],
        })
        user = {"_id": self.recipient_id, "email": self.recipient["email"], "email_verified": True}
        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(invitation_service.accept_invitation_token(token, user))
        self.assertEqual(error.exception.status_code, 409)
        mock_db.invitations.update_one.assert_not_awaited()

    def test_expired_revoked_and_reused_invitation_tokens_cannot_be_accepted(self):
        token = "one-time-token"
        expired = {
            "_id": ObjectId(), "workspace_id": self.ws_id, "recipient_email": self.recipient["email"],
            "token_hash": invitation_service._hash_invitation_token(token), "status": "pending",
            "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
        }
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value=expired)
        mock_db.invitations.update_one = AsyncMock()
        user = {"_id": self.recipient_id, "email": self.recipient["email"], "email_verified": True}
        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as expired_error:
                asyncio.run(invitation_service.resolve_invitation_token(token))
            self.assertEqual(expired_error.exception.status_code, 410)
            with self.assertRaises(HTTPException):
                asyncio.run(invitation_service.accept_invitation_token(token, user))

            expired["status"] = "revoked"
            expired["expires_at"] = datetime.now(timezone.utc) + timedelta(days=1)
            with self.assertRaises(HTTPException) as revoked_error:
                asyncio.run(invitation_service.resolve_invitation_token(token))
            self.assertEqual(revoked_error.exception.status_code, 410)

    def test_invitation_email_validation_rejects_invalid_address(self):
        from app.schemas.invitations_schema import CreateInvitationRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CreateInvitationRequest(email="not-an-email")

    def test_tampered_invitation_token_is_rejected(self):
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value=None)
        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(invitation_service.resolve_invitation_token("tampered-token"))
        self.assertEqual(error.exception.status_code, 404)

    def test_resend_provider_uses_https_api_and_idempotency_key(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"id": "resend-message-id"}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response)

        with patch.object(email_service.settings, "EMAIL_PROVIDER", "resend"), \
             patch.object(email_service.settings, "RESEND_API_KEY", "test-api-key"), \
             patch.object(email_service.settings, "RESEND_FROM_EMAIL", "CollabAI <noreply@example.com>"), \
             patch("app.services.email_service.httpx.AsyncClient", return_value=client):
            result = asyncio.run(email_service.send_email(
                "invitee@example.com", "Invite", "Join us", idempotency_key="outbox-123"
            ))

        self.assertEqual(result, {
            "provider": "resend", "status": "accepted_by_provider", "message_id": "resend-message-id"
        })
        self.assertEqual(client.post.call_args.kwargs["headers"]["Idempotency-Key"], "outbox-123")

    def test_failed_pending_invitation_retries_existing_outbox(self):
        invitation_id = ObjectId()
        outbox_id = ObjectId()
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=self.recipient)
        mock_db.invitations.find_one = AsyncMock(return_value={
            "_id": invitation_id, "status": "pending", "recipient_email": self.recipient["email"],
            "workspace_name": "AI Lab", "sender_name": "Owner", "sender_email": self.owner["email"],
        })
        mock_db.invitations.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
        mock_db.email_outbox.find_one = AsyncMock(return_value={
            "_id": outbox_id, "invitation_id": invitation_id, "to": self.recipient["email"],
            "subject": "Invite", "body": "Join", "status": "failed",
        })
        mock_db.email_outbox.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))

        with patch("app.services.invitation_service.get_database", return_value=mock_db), \
             patch("app.services.invitation_service.send_email", new=AsyncMock(return_value={
                 "provider": "resend", "status": "accepted_by_provider", "message_id": "msg-1"
             })) as sender:
            result = asyncio.run(invitation_service.invite_teammate(str(self.ws_id), self.recipient["email"], self.owner))

        self.assertEqual(result["email_status"], "accepted_by_provider")
        sender.assert_awaited_once()
        mock_db.invitations.insert_one.assert_not_called()
        mock_db.email_outbox.update_one.assert_awaited()

    def test_invitation_smtp_failure_is_recorded_without_losing_invitation(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=self.recipient)
        mock_db.invitations.find_one = AsyncMock(return_value=None)
        mock_db.invitations.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
        mock_db.notifications.insert_one = AsyncMock()
        outbox_id = ObjectId()
        mock_db.email_outbox.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=outbox_id))
        mock_db.email_outbox.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))

        with patch("app.services.invitation_service.get_database", return_value=mock_db), \
             patch("app.services.invitation_service.send_email", new=AsyncMock(side_effect=RuntimeError("SMTP unavailable"))):
            result = asyncio.run(invitation_service.invite_teammate(str(self.ws_id), "invitee@collabai.com", self.owner))

        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["email_status"], "failed")
        mock_db.invitations.insert_one.assert_awaited_once()
        self.assertEqual(mock_db.email_outbox.update_one.await_count, 2)
        update = mock_db.email_outbox.update_one.call_args
        self.assertEqual(update.args[0], {"_id": outbox_id, "status": "sending"})
        self.assertEqual(update.args[1]["$set"]["status"], "failed")

    def test_create_workspace_invites_each_initial_member_and_returns_outcomes(self):
        ws_id = ObjectId()
        now = datetime.now(timezone.utc)
        created = {"_id": ws_id, "name": "Team", "description": "", "owner_id": self.owner_id,
                   "members": [{"user_id": self.owner_id}], "created_at": now, "updated_at": now}
        mock_db = MagicMock()
        mock_db.workspaces.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ws_id))
        mock_db.channels.insert_many = AsyncMock()
        mock_db.workspaces.find_one = AsyncMock(return_value=created)
        outcomes = [
            {"message": "Invitation created", "invitation_id": str(ObjectId()), "status": "pending", "email_status": "accepted_by_smtp"},
            {"message": "Invitation created", "invitation_id": str(ObjectId()), "status": "pending", "email_status": "failed"},
        ]
        with patch("app.services.workspace_service.get_database", return_value=mock_db), \
             patch("app.services.workspace_service.invitation_service.invite_teammate", new=AsyncMock(side_effect=outcomes)) as invite:
            payload = CreateWorkspaceRequest(name="Team", initial_members=["one@example.com", "two@example.com"])
            result = asyncio.run(workspace_service.create_workspace(payload, self.user))

        self.assertEqual(len(result["invitation_results"]), 2)
        self.assertEqual(invite.await_count, 2)

    def test_create_workspace_with_one_initial_member(self):
        ws_id = ObjectId()
        now = datetime.now(timezone.utc)
        created = {"_id": ws_id, "name": "Team", "description": "", "owner_id": self.user_id,
                   "members": [{"user_id": self.user_id}], "created_at": now, "updated_at": now}
        mock_db = MagicMock()
        mock_db.workspaces.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ws_id))
        mock_db.channels.insert_many = AsyncMock()
        mock_db.workspaces.find_one = AsyncMock(return_value=created)
        invite = AsyncMock(return_value={"status": "pending", "email_status": "accepted_by_smtp"})
        with patch("app.services.workspace_service.get_database", return_value=mock_db), \
             patch("app.services.workspace_service.invitation_service.invite_teammate", new=invite):
            result = asyncio.run(workspace_service.create_workspace(
                CreateWorkspaceRequest(name="Team", initial_members=["one@example.com"]), self.user
            ))
        self.assertEqual(len(result["invitation_results"]), 1)
        invite.assert_awaited_once()

    def test_cannot_invite_self(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=self.owner)

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(invitation_service.invite_teammate(str(self.ws_id), "owner@collabai.com", self.owner))
            self.assertEqual(exc.exception.status_code, 400)

    def test_duplicate_pending_invitation_rejected(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={"_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id, "members": []})
        mock_db.users.find_one = AsyncMock(return_value=self.recipient)
        mock_db.invitations.find_one = AsyncMock(return_value={"_id": ObjectId(), "status": "pending"})
        mock_db.email_outbox.find_one = AsyncMock(return_value=None)

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(invitation_service.invite_teammate(str(self.ws_id), "invitee@collabai.com", self.owner))
            self.assertEqual(exc.exception.status_code, 409)

    def test_inviting_existing_member_returns_conflict(self):
        mock_db = MagicMock()
        mock_db.workspaces.find_one = AsyncMock(return_value={
            "_id": self.ws_id, "name": "AI Lab", "owner_id": self.owner_id,
            "members": [{"user_id": self.recipient_id, "email": self.recipient["email"]}],
        })
        mock_db.users.find_one = AsyncMock(return_value=self.recipient)
        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(invitation_service.invite_teammate(str(self.ws_id), self.recipient["email"], self.owner))
        self.assertEqual(error.exception.status_code, 409)
        mock_db.invitations.insert_one.assert_not_called()

    def test_accept_invitation_adds_member_and_updates_notification(self):
        inv_id = ObjectId()
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value={
            "_id": inv_id,
            "workspace_id": self.ws_id,
            "workspace_name": "AI Lab",
            "sender_user_id": self.owner_id,
            "recipient_user_id": self.recipient_id,
            "status": "pending",
        })
        mock_db.invitations.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
        mock_db.workspaces.update_one = AsyncMock()
        mock_db.notifications.insert_one = AsyncMock()
        mock_db.notifications.update_many = AsyncMock()

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            res = asyncio.run(invitation_service.respond_to_invitation(str(inv_id), self.recipient, accept=True))

        self.assertEqual(res["status"], "accepted")
        mock_db.workspaces.update_one.assert_awaited_once()
        self.assertEqual(mock_db.notifications.insert_one.call_args.args[0]["event_type"], "workspace.member_added")
        mock_db.notifications.update_many.assert_awaited_once()

    def test_decline_invitation_does_not_add_member(self):
        inv_id = ObjectId()
        mock_db = MagicMock()
        mock_db.invitations.find_one = AsyncMock(return_value={
            "_id": inv_id,
            "workspace_id": self.ws_id,
            "recipient_user_id": self.recipient_id,
            "status": "pending",
        })
        mock_db.invitations.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
        mock_db.workspaces.update_one = AsyncMock()
        mock_db.notifications.update_many = AsyncMock()

        with patch("app.services.invitation_service.get_database", return_value=mock_db):
            res = asyncio.run(invitation_service.respond_to_invitation(str(inv_id), self.recipient, accept=False))

        self.assertEqual(res["status"], "declined")
        mock_db.workspaces.update_one.assert_not_awaited()

    def test_notifications_privacy_and_unread_count(self):
        mock_db = MagicMock()
        async def notif_iter():
            yield {
                "_id": ObjectId(),
                "title": "Invitation",
                "message": "Invited",
                "is_read": False,
                "recipient_user_id": self.recipient_id,
                "created_at": datetime.now(timezone.utc),
            }

        cursor = MagicMock()
        cursor.__aiter__ = lambda s: notif_iter()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.skip = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)

        mock_db.notifications.find = MagicMock(return_value=cursor)
        mock_db.notifications.count_documents = AsyncMock(return_value=1)

        with patch("app.services.notification_service.get_database", return_value=mock_db):
            res = asyncio.run(notification_service.list_notifications(self.recipient))
            unread = asyncio.run(notification_service.get_unread_count(self.recipient))

        self.assertEqual(res["unread_count"], 1)
        self.assertEqual(len(res["notifications"]), 1)
        self.assertEqual(unread["unread_count"], 1)

    def test_notification_naive_mongodb_datetime_is_serialized_as_utc(self):
        created = datetime(2026, 10, 13, 5, 0, 0)
        record = notification_service.serialize_notification({"_id": ObjectId(), "created_at": created})
        self.assertEqual(record["created_at"], "2026-10-13T05:00:00Z")

    def test_unconfigured_smtp_raises_instead_of_claiming_success(self):
        with patch.object(email_service.settings, "SMTP_HOST", ""), \
             patch.object(email_service.settings, "SMTP_USERNAME", ""), \
             patch.object(email_service.settings, "SMTP_PASSWORD", ""), \
             patch.object(email_service.settings, "SMTP_FROM_EMAIL", ""):
            with self.assertRaisesRegex(RuntimeError, "SMTP is not configured"):
                asyncio.run(email_service.send_email("to@example.com", "Subject", "Body"))


class WorkspaceApiSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unauthenticated_request_rejected(self):
        # Without session cookie, should return 401
        res = self.client.get("/api/workspaces")
        self.assertEqual(res.status_code, 401)

        res_notif = self.client.get("/api/notifications")
        self.assertEqual(res_notif.status_code, 401)

    def test_unauthorized_user_cannot_create_invitation(self):
        response = self.client.post(
            f"/api/workspaces/{ObjectId()}/invitations",
            json={"email": "newperson@example.com"},
        )
        self.assertEqual(response.status_code, 401)

    def test_cors_preflight_allows_both_production_origins_with_credentials(self):
        for origin in ("https://www.collabai.online", "https://collabai.online"):
            response = self.client.options(
                "/api/workspaces",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-csrf-token",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
            self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")

    def test_mutation_without_csrf_rejected(self):
        # Even with mock authenticated user, missing CSRF token returns 403
        from app.middleware.authentication import get_current_user
        app.dependency_overrides[get_current_user] = lambda: {"_id": ObjectId(), "email": "test@test.com"}
        try:
            res = self.client.post("/api/workspaces", json={"name": "Test Room"})
            self.assertEqual(res.status_code, 403)
        finally:
            app.dependency_overrides.clear()
