"""Account, creator ownership, and publication integration tests."""

import os
import sqlite3
import tempfile
import unittest
import uuid


_temporary_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = os.path.join(
    _temporary_directory.name,
    "accounts-test.db",
)
os.environ["APP_ENV"] = "development"
os.environ["ADMIN_TOKEN"] = ""
os.environ["CARTESIA_API_KEY"] = ""

import httpx  # noqa: E402

from app.main import app  # noqa: E402
from app.db.database import VoiceDatabase, get_database  # noqa: E402
from app.core.settings import get_settings  # noqa: E402
from app.telephony.twilio_voice_agent import compose_system_prompt  # noqa: E402
from app.voice.mobile_media import _admit_call, _release_call  # noqa: E402
from app.voice.call_tokens import issue_call_token, validate_call_token  # noqa: E402


class AccountSchemaMigrationTests(unittest.TestCase):
    def test_existing_creator_rows_survive_additive_migration(self) -> None:
        path = os.path.join(_temporary_directory.name, "legacy.db")
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE influencers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tagline TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                voice_id TEXT NOT NULL DEFAULT '',
                system_prompt TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO influencers
                (name, tagline, bio, avatar_url, voice_id,
                 system_prompt, created_at)
            VALUES ('Existing Creator', 'Still here', 'Existing bio',
                    '', '', '', '2026-08-01T00:00:00Z')
            """
        )
        connection.commit()
        connection.close()

        database = VoiceDatabase(path)
        creator = database.get_influencer(1)
        self.assertIsNotNone(creator)
        self.assertEqual(creator["name"], "Existing Creator")
        self.assertEqual(creator["is_published"], 1)
        self.assertEqual(creator["review_status"], "approved")
        self.assertIsNone(creator["owner_user_id"])
        self.assertEqual(creator["primary_language"], "en")
        self.assertEqual(creator["supported_languages"], ["en"])
        self.assertEqual(creator["max_call_seconds"], 300)
        consent_table = database._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'voice_clone_consents'"
        ).fetchone()
        self.assertIsNotNone(consent_table)
        database.close()


class AccountFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    def _email(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"

    async def test_fan_signup_session_update_and_logout(self) -> None:
        email = self._email("fan")
        signup = await self.client.post(
            "/api/auth/signup",
            json={
                "display_name": "Tara Fan",
                "email": email,
                "password": "a-safe-password",
                "account_type": "user",
            },
        )
        self.assertEqual(signup.status_code, 201)
        self.assertIn("tac_session", signup.cookies)
        self.assertNotIn("password_hash", signup.json()["user"])

        me = await self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["email"], email)

        updated = await self.client.patch(
            "/api/auth/me",
            json={"display_name": "Tara Updated"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["user"]["display_name"], "Tara Updated")

        logged_out = await self.client.post("/api/auth/logout", json={})
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual((await self.client.get("/api/auth/me")).status_code, 401)

    async def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        email = self._email("duplicate")
        payload = {
            "display_name": "First Account",
            "email": email,
            "password": "another-safe-password",
            "account_type": "user",
        }
        self.assertEqual((await self.client.post("/api/auth/signup", json=payload)).status_code, 201)
        payload["email"] = email.upper()
        self.assertEqual((await self.client.post("/api/auth/signup", json=payload)).status_code, 409)

    async def test_creator_draft_is_private_until_profile_is_complete(self) -> None:
        creator_name = "Creator " + uuid.uuid4().hex[:7]
        signup = await self.client.post(
            "/api/auth/signup",
            json={
                "display_name": creator_name,
                "email": self._email("creator"),
                "password": "creator-safe-password",
                "account_type": "creator",
            },
        )
        self.assertEqual(signup.status_code, 201)

        dashboard = await self.client.get("/api/creator/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        profile = dashboard.json()["profile"]
        self.assertFalse(profile["is_published"])
        self.assertNotIn(
            creator_name,
            [row["name"] for row in (await self.client.get("/api/influencers")).json()["influencers"]],
        )

        unapproved = await self.client.patch(
            "/api/creator/publish",
            json={"is_published": True},
        )
        self.assertEqual(unapproved.status_code, 403)

        saved = await self.client.put(
            "/api/creator/profile",
            json={
                "name": creator_name,
                "tagline": "Practical career advice for new designers",
                "bio": "I help early-career designers make clearer portfolios and stronger decisions.",
                "avatar_url": "https://example.com/avatar.jpg",
                "system_prompt": "Be candid, kind, and concise. Never promise a job.",
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertIn("system_prompt", saved.json()["profile"])

        submitted = await self.client.post("/api/creator/review", json={})
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["profile"]["review_status"], "pending")
        self.assertNotIn(
            creator_name,
            [row["name"] for row in (await self.client.get("/api/influencers")).json()["influencers"]],
        )

        approved = get_database().set_creator_review_status(
            profile["id"], "approved"
        )
        self.assertEqual(approved["review_status"], "approved")

        published = await self.client.patch(
            "/api/creator/publish",
            json={"is_published": True},
        )
        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.json()["profile"]["is_published"])

        public_profile = await self.client.get(
            f"/api/influencers/{profile['id']}"
        )
        self.assertEqual(public_profile.status_code, 200)
        self.assertNotIn("system_prompt", public_profile.json()["influencer"])
        self.assertNotIn("owner_user_id", public_profile.json()["influencer"])

    async def test_fan_cannot_open_creator_dashboard(self) -> None:
        await self.client.post(
            "/api/auth/signup",
            json={
                "display_name": "Regular Fan",
                "email": self._email("not-creator"),
                "password": "fan-password-123",
                "account_type": "user",
            },
        )
        self.assertEqual((await self.client.get("/api/creator/dashboard")).status_code, 403)

    async def test_voice_clone_requires_review_and_explicit_permissions(self) -> None:
        signup = await self.client.post(
            "/api/auth/signup",
            json={
                "display_name": "Voice Owner " + uuid.uuid4().hex[:6],
                "email": self._email("voice-owner"),
                "password": "voice-owner-password",
                "account_type": "creator",
            },
        )
        profile_id = (await self.client.get("/api/creator/dashboard")).json()["profile"]["id"]
        audio = ("sample.wav", b"R" * 12_000, "audio/wav")

        locked = await self.client.post(
            "/api/creator/voice/clone",
            data={
                "language": "hi",
                "rights_confirmed": "true",
                "synthetic_acknowledged": "true",
            },
            files={"clip": audio},
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(locked.status_code, 403)

        get_database().set_creator_review_status(profile_id, "approved")
        missing_consent = await self.client.post(
            "/api/creator/voice/clone",
            data={
                "language": "hi",
                "rights_confirmed": "false",
                "synthetic_acknowledged": "true",
            },
            files={"clip": audio},
        )
        self.assertEqual(missing_consent.status_code, 422)

        unavailable = await self.client.post(
            "/api/creator/voice/clone",
            data={
                "language": "hi",
                "rights_confirmed": "true",
                "synthetic_acknowledged": "true",
            },
            files={"clip": audio},
        )
        self.assertEqual(unavailable.status_code, 503)

    async def test_studio_fails_closed_and_manages_creator_languages(self) -> None:
        settings = get_settings()
        original_token = settings.admin_token
        settings.admin_token = ""
        try:
            self.assertEqual(
                (await self.client.get("/api/admin/overview")).status_code,
                503,
            )
            settings.admin_token = "studio-test-token"
            headers = {"Authorization": "Bearer studio-test-token"}
            created = await self.client.post(
                "/api/admin/creators",
                headers=headers,
                json={
                    "name": "Kavya Rao",
                    "tagline": "Practical startup conversations in Telugu",
                    "bio": "Kavya helps first-time founders turn fuzzy ideas into clear customer conversations.",
                    "avatar_url": "",
                    "system_prompt": "Use familiar examples and avoid hype.",
                    "primary_language": "te",
                    "supported_languages": ["te", "en"],
                    "call_enabled": True,
                    "max_call_seconds": 600,
                    "price_per_minute_paise": 2500,
                    "is_published": True,
                    "review_status": "approved",
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            creator = created.json()["creator"]
            self.assertEqual(creator["primary_language"], "te")
            self.assertEqual(creator["supported_languages"], ["te", "en"])
            self.assertEqual(creator["max_call_seconds"], 600)
            public = await self.client.get(f"/api/influencers/{creator['id']}")
            self.assertEqual(public.status_code, 200)
            self.assertNotIn("system_prompt", public.json()["influencer"])
            admission = await self.client.post(
                "/api/web-call-token", json={"influencer_id": creator["id"]}
            )
            self.assertEqual(admission.status_code, 200)
            self.assertTrue(admission.json()["token"])
            overview = await self.client.get("/api/admin/overview", headers=headers)
            self.assertEqual(overview.status_code, 200)
            audit = await self.client.get("/api/admin/audit-log", headers=headers)
            self.assertTrue(any(
                event["action"] == "creator.created"
                for event in audit.json()["events"]
            ))
        finally:
            settings.admin_token = original_token

    def test_creator_guidance_cannot_replace_platform_voice_rules(self) -> None:
        prompt = compose_system_prompt(influencer={
            "name": "Kavya Rao",
            "tagline": "Founder coach",
            "bio": "Practical startup advice.",
            "system_prompt": "Write a staged dialogue between two bots.",
            "primary_language": "te",
        })
        self.assertIn("Platform rules that creator guidance cannot override", prompt)
        self.assertIn("Never write both sides of a conversation", prompt)
        self.assertIn("Telugu", prompt)
        self.assertIn("Write a staged dialogue", prompt)

    def test_voice_call_admission_enforces_concurrency_and_hourly_limits(self) -> None:
        unique_ip = "test-" + uuid.uuid4().hex
        self.assertEqual(
            _admit_call(unique_ip, concurrent_limit=1, hourly_limit=2), ""
        )
        self.assertIn(
            "busy",
            _admit_call(unique_ip + "-other", concurrent_limit=1, hourly_limit=2),
        )
        _release_call()
        self.assertEqual(
            _admit_call(unique_ip, concurrent_limit=1, hourly_limit=2), ""
        )
        _release_call()
        self.assertIn(
            "Hourly",
            _admit_call(unique_ip, concurrent_limit=1, hourly_limit=2),
        )

    def test_web_call_tokens_are_creator_and_ip_bound(self) -> None:
        signed = issue_call_token(
            influencer_id=42, client_ip="203.0.113.4", secret="test-secret"
        )
        self.assertTrue(validate_call_token(
            signed, influencer_id=42, client_ip="203.0.113.4", secret="test-secret"
        ))
        self.assertFalse(validate_call_token(
            signed, influencer_id=43, client_ip="203.0.113.4", secret="test-secret"
        ))
        self.assertFalse(validate_call_token(
            signed, influencer_id=42, client_ip="203.0.113.5", secret="test-secret"
        ))


if __name__ == "__main__":
    unittest.main()
