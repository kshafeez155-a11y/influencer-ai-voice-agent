"""SQLite persistence for influencers and call requests.

Uses a single file (``voice_agent.db`` by default) so the prototype
needs no external database. A thread lock guards all connections
because Twilio WebSocket paths run concurrently with API requests.
"""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from app.core.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS influencers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    tagline       TEXT    NOT NULL DEFAULT '',
    bio           TEXT    NOT NULL DEFAULT '',
    avatar_url    TEXT    NOT NULL DEFAULT '',
    voice_id      TEXT    NOT NULL DEFAULT '',
    system_prompt TEXT    NOT NULL DEFAULT '',
    owner_user_id INTEGER,
    is_published  INTEGER NOT NULL DEFAULT 1,
    review_status TEXT    NOT NULL DEFAULT 'approved',
    primary_language TEXT NOT NULL DEFAULT 'en',
    supported_languages_json TEXT NOT NULL DEFAULT '["en"]',
    call_enabled  INTEGER NOT NULL DEFAULT 1,
    max_call_seconds INTEGER NOT NULL DEFAULT 300,
    price_per_minute_paise INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS call_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id INTEGER,
    user_name     TEXT    NOT NULL DEFAULT '',
    user_phone    TEXT    NOT NULL,
    call_sid      TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'requested',
    error         TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS public_submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT    NOT NULL,
    name          TEXT    NOT NULL DEFAULT '',
    email         TEXT    NOT NULL DEFAULT '',
    phone         TEXT    NOT NULL DEFAULT '',
    subject       TEXT    NOT NULL DEFAULT '',
    message       TEXT    NOT NULL DEFAULT '',
    metadata_json TEXT    NOT NULL DEFAULT '{}',
    status        TEXT    NOT NULL DEFAULT 'new',
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    display_name  TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash    TEXT    PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL,
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS web_call_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id    INTEGER,
    user_id           INTEGER,
    caller_name       TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'active',
    duration_seconds  INTEGER NOT NULL DEFAULT 0,
    error              TEXT    NOT NULL DEFAULT '',
    started_at         TEXT    NOT NULL,
    ended_at           TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS voice_clone_consents (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id         INTEGER NOT NULL,
    user_id               INTEGER NOT NULL,
    provider              TEXT    NOT NULL DEFAULT 'cartesia',
    provider_voice_id     TEXT    NOT NULL,
    language              TEXT    NOT NULL,
    consent_version       TEXT    NOT NULL,
    rights_confirmed      INTEGER NOT NULL,
    synthetic_acknowledged INTEGER NOT NULL,
    created_at            TEXT    NOT NULL,
    FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    action        TEXT    NOT NULL,
    entity_type   TEXT    NOT NULL,
    entity_id     TEXT    NOT NULL DEFAULT '',
    summary       TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_asset_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id         INTEGER NOT NULL,
    actor_type            TEXT    NOT NULL,
    provider              TEXT    NOT NULL DEFAULT 'cartesia',
    provider_voice_id     TEXT    NOT NULL,
    language              TEXT    NOT NULL,
    rights_confirmed      INTEGER NOT NULL,
    synthetic_acknowledged INTEGER NOT NULL,
    created_at            TEXT    NOT NULL,
    FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creator_topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id INTEGER NOT NULL,
    name          TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creator_knowledge (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id INTEGER NOT NULL,
    title         TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    language      TEXT    NOT NULL DEFAULT 'en',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user
ON user_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_web_calls_influencer
ON web_call_sessions(influencer_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_web_calls_user
ON web_call_sessions(user_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_voice_clone_consents_creator
ON voice_clone_consents(influencer_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_created
ON admin_audit_log(id DESC);

CREATE INDEX IF NOT EXISTS idx_voice_asset_events_creator
ON voice_asset_events(influencer_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_creator_topics_creator
ON creator_topics(influencer_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_creator_knowledge_creator
ON creator_knowledge(influencer_id, id DESC);
"""


def _default_influencers() -> list[dict[str, str]]:
    """Seed personas used on first boot (no data exists yet)."""

    return [
        {
            "name": "Alex Morgan",
            "tagline": "Fitness coach who trains champions",
            "bio": (
                "Alex is a certified personal trainer who has coached "
                "marathon runners and Olympic hopefuls. He talks about "
                "training, nutrition, and staying consistent. He is "
                "energetic, motivating, and never pushes anyone beyond "
                "their limits."
            ),
            "avatar_url": "",
            "voice_id": "",
            "system_prompt": "",
        },
        {
            "name": "Priya Sharma",
            "tagline": "Marketing strategist for growing brands",
            "bio": (
                "Priya runs a boutique marketing agency that helps "
                "startups find their first ten thousand customers. She "
                "is warm, sharp, and gives practical, honest advice "
                "about positioning, content, and paid ads."
            ),
            "avatar_url": "",
            "voice_id": "",
            "system_prompt": "",
        },
        {
            "name": "Marco Reyes",
            "tagline": "Real estate advisor in your neighbourhood",
            "bio": (
                "Marco has closed over four hundred property deals and "
                "loves helping families find the right home. He is "
                "patient, detail oriented, and always asks about budget "
                "and location before recommending anything."
            ),
            "avatar_url": "",
            "voice_id": "",
            "system_prompt": "",
        },
    ]


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class VoiceDatabase:
    """Thin, safe SQLite wrapper for the voice agent."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)

        if not path.is_absolute():
            path = Path.cwd() / path

        path.parent.mkdir(parents=True, exist_ok=True)

        self.path = str(path)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(_SCHEMA)
        self._migrate_schema()
        self._connection.commit()

    def _migrate_schema(self) -> None:
        """Apply additive migrations for databases created by older builds."""

        columns = {
            row["name"]
            for row in self._connection.execute(
                "PRAGMA table_info(influencers)"
            ).fetchall()
        }

        if "owner_user_id" not in columns:
            self._connection.execute(
                "ALTER TABLE influencers ADD COLUMN owner_user_id INTEGER"
            )

        if "is_published" not in columns:
            self._connection.execute(
                "ALTER TABLE influencers "
                "ADD COLUMN is_published INTEGER NOT NULL DEFAULT 1"
            )

        if "review_status" not in columns:
            self._connection.execute(
                "ALTER TABLE influencers "
                "ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'"
            )

        influencer_additions = {
            "primary_language": "TEXT NOT NULL DEFAULT 'en'",
            "supported_languages_json": "TEXT NOT NULL DEFAULT '[\"en\"]'",
            "call_enabled": "INTEGER NOT NULL DEFAULT 1",
            "max_call_seconds": "INTEGER NOT NULL DEFAULT 300",
            "price_per_minute_paise": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in influencer_additions.items():
            if name not in columns:
                self._connection.execute(
                    f"ALTER TABLE influencers ADD COLUMN {name} {definition}"
                )

        user_columns = {
            row["name"]
            for row in self._connection.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }
        if "is_active" not in user_columns:
            self._connection.execute(
                "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

    # ---------------------------------------------------------
    # Influencers
    # ---------------------------------------------------------

    def seed_if_empty(self) -> None:
        with self._lock:
            count = self._connection.execute(
                "SELECT COUNT(*) FROM influencers"
            ).fetchone()[0]

            if count > 0:
                return

            for influencer in _default_influencers():
                self._connection.execute(
                    """
                    INSERT INTO influencers
                        (name, tagline, bio, avatar_url,
                         voice_id, system_prompt, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        influencer["name"],
                        influencer["tagline"],
                        influencer["bio"],
                        influencer["avatar_url"],
                        influencer["voice_id"],
                        influencer["system_prompt"],
                        _utc_now(),
                    ),
                )

            self._connection.commit()

    def list_influencers(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, name, tagline, bio, avatar_url,
                       primary_language, supported_languages_json,
                       call_enabled, max_call_seconds,
                       price_per_minute_paise, created_at,
                       (owner_user_id IS NULL) AS is_demo
                FROM influencers
                WHERE is_published = 1 AND call_enabled = 1
                ORDER BY id
                """
            ).fetchall()

        return [self._decode_influencer(dict(row)) for row in rows]

    def get_influencer(self, influencer_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, name, tagline, bio, avatar_url,
                       voice_id, system_prompt, owner_user_id,
                       is_published, review_status, primary_language,
                       supported_languages_json, call_enabled,
                       max_call_seconds, price_per_minute_paise,
                       created_at, updated_at
                FROM influencers
                WHERE id = ?
                """,
                (influencer_id,),
            ).fetchone()

        return self._decode_influencer(dict(row)) if row is not None else None

    @staticmethod
    def _decode_influencer(row: dict) -> dict:
        raw = row.pop("supported_languages_json", '["en"]')
        try:
            languages = json.loads(raw)
        except (TypeError, ValueError):
            languages = [row.get("primary_language") or "en"]
        row["supported_languages"] = [
            str(value) for value in languages if str(value).strip()
        ] or [row.get("primary_language") or "en"]
        for key in ("is_published", "call_enabled"):
            if key in row:
                row[key] = bool(row[key])
        return row

    def create_influencer(
        self,
        *,
        name: str,
        tagline: str,
        bio: str,
        avatar_url: str,
        voice_id: str,
        system_prompt: str,
        owner_user_id: int | None = None,
        is_published: bool = True,
        review_status: str = "approved",
        primary_language: str = "en",
        supported_languages: list[str] | None = None,
        call_enabled: bool = True,
        max_call_seconds: int = 300,
        price_per_minute_paise: int = 0,
    ) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO influencers
                    (name, tagline, bio, avatar_url,
                     voice_id, system_prompt, owner_user_id,
                     is_published, review_status, primary_language,
                     supported_languages_json, call_enabled,
                     max_call_seconds, price_per_minute_paise,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    tagline,
                    bio,
                    avatar_url,
                    voice_id,
                    system_prompt,
                    owner_user_id,
                    int(is_published),
                    review_status,
                    primary_language,
                    json.dumps(supported_languages or [primary_language]),
                    int(call_enabled),
                    max(60, min(int(max_call_seconds), 3600)),
                    max(0, int(price_per_minute_paise)),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            self._connection.commit()
            influencer_id = int(cursor.lastrowid)

        influencer = self.get_influencer(influencer_id)
        assert influencer is not None
        return influencer

    def delete_influencer(self, influencer_id: int) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM influencers WHERE id = ?",
                (influencer_id,),
            )
            self._connection.commit()

        return cursor.rowcount > 0

    # ---------------------------------------------------------
    # Accounts and creator ownership
    # ---------------------------------------------------------

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        role: str,
    ) -> dict:
        now = _utc_now()

        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO users
                    (email, display_name, password_hash, role,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    display_name,
                    password_hash,
                    role,
                    now,
                    now,
                ),
            )
            self._connection.commit()
            user_id = int(cursor.lastrowid)

        user = self.get_user(user_id)
        assert user is not None
        return user

    def get_user(self, user_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, email, display_name, password_hash, role, is_active,
                       created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return None
        user = dict(row)
        user["is_active"] = bool(user["is_active"])
        return user

    def get_user_by_email(self, email: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, email, display_name, password_hash, role, is_active,
                       created_at, updated_at
                FROM users
                WHERE email = ? COLLATE NOCASE
                """,
                (email,),
            ).fetchone()

        if row is None:
            return None
        user = dict(row)
        user["is_active"] = bool(user["is_active"])
        return user

    def update_user_name(self, user_id: int, display_name: str) -> dict:
        with self._lock:
            self._connection.execute(
                """
                UPDATE users
                SET display_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (display_name, _utc_now(), user_id),
            )
            self._connection.commit()

        user = self.get_user(user_id)
        assert user is not None
        return user

    def create_user_session(
        self,
        *,
        token_hash: str,
        user_id: int,
        expires_at: int,
    ) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM user_sessions WHERE expires_at <= ?",
                (int(time.time()),),
            )
            self._connection.execute(
                """
                INSERT INTO user_sessions
                    (token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, user_id, expires_at, _utc_now()),
            )
            self._connection.commit()

    def get_user_by_session(
        self,
        token_hash: str,
    ) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT u.id, u.email, u.display_name, u.password_hash,
                       u.role, u.is_active, u.created_at, u.updated_at
                FROM user_sessions AS s
                JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1
                """,
                (token_hash, int(time.time())),
            ).fetchone()

        if row is None:
            return None
        user = dict(row)
        user["is_active"] = bool(user["is_active"])
        return user

    def delete_user_session(self, token_hash: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?",
                (token_hash,),
            )
            self._connection.commit()

    def get_creator_profile(self, owner_user_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, name, tagline, bio, avatar_url, voice_id,
                       system_prompt, owner_user_id, is_published,
                       review_status, primary_language,
                       supported_languages_json, call_enabled,
                       max_call_seconds, price_per_minute_paise,
                       created_at, updated_at
                FROM influencers
                WHERE owner_user_id = ?
                LIMIT 1
                """,
                (owner_user_id,),
            ).fetchone()

        return self._decode_influencer(dict(row)) if row is not None else None

    def update_creator_profile(
        self,
        *,
        owner_user_id: int,
        name: str,
        tagline: str,
        bio: str,
        avatar_url: str,
        system_prompt: str,
        primary_language: str,
        supported_languages: list[str],
    ) -> dict:
        with self._lock:
            self._connection.execute(
                """
                UPDATE influencers
                SET name = ?, tagline = ?, bio = ?, avatar_url = ?,
                    system_prompt = ?, primary_language = ?,
                    supported_languages_json = ?, updated_at = ?
                WHERE owner_user_id = ?
                """,
                (
                    name,
                    tagline,
                    bio,
                    avatar_url,
                    system_prompt,
                    primary_language,
                    json.dumps(supported_languages),
                    _utc_now(),
                    owner_user_id,
                ),
            )
            self._connection.commit()

        profile = self.get_creator_profile(owner_user_id)
        assert profile is not None
        return profile

    def activate_creator_voice_clone(
        self,
        *,
        owner_user_id: int,
        provider_voice_id: str,
        language: str,
        consent_version: str,
        rights_confirmed: bool,
        synthetic_acknowledged: bool,
    ) -> dict:
        """Activate a cloned voice and retain the creator's consent receipt."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, supported_languages_json FROM influencers
                WHERE owner_user_id = ?
                LIMIT 1
                """,
                (owner_user_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Creator profile not found.")

            influencer_id = int(row["id"])
            try:
                supported_languages = json.loads(row["supported_languages_json"])
            except (TypeError, ValueError):
                supported_languages = []
            if language not in supported_languages:
                supported_languages.append(language)
            self._connection.execute(
                """
                UPDATE influencers
                SET voice_id = ?, primary_language = ?,
                    supported_languages_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    provider_voice_id, language,
                    json.dumps(supported_languages), _utc_now(), influencer_id,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO voice_clone_consents
                    (influencer_id, user_id, provider, provider_voice_id,
                     language, consent_version, rights_confirmed,
                     synthetic_acknowledged, created_at)
                VALUES (?, ?, 'cartesia', ?, ?, ?, ?, ?, ?)
                """,
                (
                    influencer_id,
                    owner_user_id,
                    provider_voice_id,
                    language,
                    consent_version,
                    int(rights_confirmed),
                    int(synthetic_acknowledged),
                    _utc_now(),
                ),
            )
            self._connection.commit()

        profile = self.get_creator_profile(owner_user_id)
        assert profile is not None
        return profile

    def set_creator_published(
        self,
        owner_user_id: int,
        is_published: bool,
    ) -> dict:
        with self._lock:
            self._connection.execute(
                """
                UPDATE influencers
                SET is_published = ?
                WHERE owner_user_id = ?
                """,
                (int(is_published), owner_user_id),
            )
            self._connection.commit()

        profile = self.get_creator_profile(owner_user_id)
        assert profile is not None
        return profile

    def set_creator_review_status(
        self,
        influencer_id: int,
        review_status: str,
    ) -> dict | None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE influencers
                SET review_status = ?,
                    is_published = CASE
                        WHEN ? = 'approved' THEN is_published
                        ELSE 0
                    END
                WHERE id = ? AND owner_user_id IS NOT NULL
                """,
                (review_status, review_status, influencer_id),
            )
            self._connection.commit()

        return self.get_influencer(influencer_id)

    def list_creator_reviews(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT i.id, i.name, i.tagline, i.bio, i.avatar_url,
                       i.review_status, i.is_published, i.created_at,
                       u.email AS owner_email,
                       u.display_name AS owner_name
                FROM influencers AS i
                JOIN users AS u ON u.id = i.owner_user_id
                WHERE i.review_status IN ('pending', 'rejected')
                ORDER BY CASE i.review_status
                    WHEN 'pending' THEN 0 ELSE 1 END, i.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()

        return [dict(row) for row in rows]

    # ---------------------------------------------------------
    # Studio control plane
    # ---------------------------------------------------------

    def list_all_influencers(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT i.id, i.name, i.tagline, i.bio, i.avatar_url,
                       i.voice_id, i.system_prompt, i.owner_user_id,
                       i.is_published, i.review_status,
                       i.primary_language, i.supported_languages_json,
                       i.call_enabled, i.max_call_seconds,
                       i.price_per_minute_paise, i.created_at, i.updated_at,
                       u.email AS owner_email,
                       COUNT(w.id) AS total_calls,
                       COALESCE(SUM(w.duration_seconds), 0) AS total_seconds
                FROM influencers AS i
                LEFT JOIN users AS u ON u.id = i.owner_user_id
                LEFT JOIN web_call_sessions AS w ON w.influencer_id = i.id
                GROUP BY i.id
                ORDER BY i.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._decode_influencer(dict(row)) for row in rows]

    def update_influencer_admin(
        self,
        influencer_id: int,
        *,
        name: str,
        tagline: str,
        bio: str,
        avatar_url: str,
        system_prompt: str,
        primary_language: str,
        supported_languages: list[str],
        call_enabled: bool,
        max_call_seconds: int,
        price_per_minute_paise: int,
        is_published: bool,
        review_status: str,
    ) -> dict | None:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE influencers
                SET name = ?, tagline = ?, bio = ?, avatar_url = ?,
                    system_prompt = ?, primary_language = ?,
                    supported_languages_json = ?, call_enabled = ?,
                    max_call_seconds = ?, price_per_minute_paise = ?,
                    is_published = ?, review_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name, tagline, bio, avatar_url, system_prompt,
                    primary_language, json.dumps(supported_languages),
                    int(call_enabled), max(60, min(max_call_seconds, 3600)),
                    max(0, price_per_minute_paise), int(is_published),
                    review_status, _utc_now(), influencer_id,
                ),
            )
            self._connection.commit()
        return self.get_influencer(influencer_id) if cursor.rowcount else None

    def activate_admin_voice(
        self,
        influencer_id: int,
        *,
        provider_voice_id: str,
        language: str,
        rights_confirmed: bool,
        synthetic_acknowledged: bool,
    ) -> dict | None:
        with self._lock:
            existing = self._connection.execute(
                "SELECT supported_languages_json FROM influencers WHERE id = ?",
                (influencer_id,),
            ).fetchone()
            if existing is None:
                return None
            try:
                supported_languages = json.loads(
                    existing["supported_languages_json"]
                )
            except (TypeError, ValueError):
                supported_languages = []
            if language not in supported_languages:
                supported_languages.append(language)
            cursor = self._connection.execute(
                """
                UPDATE influencers
                SET voice_id = ?, primary_language = ?,
                    supported_languages_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    provider_voice_id, language,
                    json.dumps(supported_languages), _utc_now(), influencer_id,
                ),
            )
            if not cursor.rowcount:
                return None
            self._connection.execute(
                """
                INSERT INTO voice_asset_events
                    (influencer_id, actor_type, provider, provider_voice_id,
                     language, rights_confirmed, synthetic_acknowledged,
                     created_at)
                VALUES (?, 'admin', 'cartesia', ?, ?, ?, ?, ?)
                """,
                (
                    influencer_id, provider_voice_id, language,
                    int(rights_confirmed), int(synthetic_acknowledged),
                    _utc_now(),
                ),
            )
            self._connection.commit()
        return self.get_influencer(influencer_id)

    def list_users(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT u.id, u.email, u.display_name, u.role, u.is_active,
                       u.created_at, u.updated_at,
                       i.id AS influencer_id, i.review_status,
                       i.is_published,
                       COUNT(w.id) AS total_calls
                FROM users AS u
                LEFT JOIN influencers AS i ON i.owner_user_id = u.id
                LEFT JOIN web_call_sessions AS w ON w.user_id = u.id
                GROUP BY u.id
                ORDER BY u.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["is_active"] = bool(item["is_active"])
            item["is_published"] = bool(item["is_published"] or 0)
            result.append(item)
        return result

    def update_user_admin(
        self,
        user_id: int,
        *,
        role: str,
        is_active: bool,
    ) -> dict | None:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE users SET role = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (role, int(is_active), _utc_now(), user_id),
            )
            if cursor.rowcount and not is_active:
                self._connection.execute(
                    "DELETE FROM user_sessions WHERE user_id = ?", (user_id,)
                )
            self._connection.commit()
        return self.get_user(user_id) if cursor.rowcount else None

    def list_web_calls(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT w.id, w.caller_name, w.status, w.duration_seconds,
                       w.error, w.started_at, w.ended_at,
                       i.id AS influencer_id, i.name AS influencer_name,
                       u.id AS user_id, u.email AS user_email
                FROM web_call_sessions AS w
                LEFT JOIN influencers AS i ON i.id = w.influencer_id
                LEFT JOIN users AS u ON u.id = w.user_id
                ORDER BY w.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def studio_overview(self) -> dict:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM influencers) AS creators,
                  (SELECT COUNT(*) FROM influencers WHERE is_published = 1) AS published,
                  (SELECT COUNT(*) FROM influencers WHERE review_status = 'pending') AS pending_reviews,
                  (SELECT COUNT(*) FROM users) AS users,
                  (SELECT COUNT(*) FROM web_call_sessions) AS calls,
                  (SELECT COALESCE(SUM(duration_seconds), 0) FROM web_call_sessions) AS seconds,
                  (SELECT COUNT(*) FROM public_submissions WHERE status = 'new') AS open_submissions
                """
            ).fetchone()
        return dict(row)

    def set_submission_status(self, submission_id: int, status: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE public_submissions SET status = ? WHERE id = ?",
                (status, submission_id),
            )
            self._connection.commit()
        return bool(cursor.rowcount)

    def record_admin_action(
        self, action: str, entity_type: str, entity_id: str, summary: str
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO admin_audit_log
                    (action, entity_type, entity_id, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action, entity_type, entity_id, summary[:500], _utc_now()),
            )
            self._connection.commit()

    def list_admin_actions(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, action, entity_type, entity_id, summary, created_at
                FROM admin_audit_log ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_creator_topics(self, influencer_id: int) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, influencer_id, name, description, is_active, created_at
                FROM creator_topics WHERE influencer_id = ? ORDER BY id DESC
                """,
                (influencer_id,),
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["is_active"] = bool(row["is_active"])
        return result

    def create_creator_topic(
        self, influencer_id: int, *, name: str, description: str
    ) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO creator_topics
                    (influencer_id, name, description, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (influencer_id, name, description, _utc_now()),
            )
            self._connection.commit()
            topic_id = int(cursor.lastrowid)
        return next(
            row for row in self.list_creator_topics(influencer_id)
            if row["id"] == topic_id
        )

    def delete_creator_topic(self, influencer_id: int, topic_id: int) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM creator_topics WHERE id = ? AND influencer_id = ?",
                (topic_id, influencer_id),
            )
            self._connection.commit()
        return bool(cursor.rowcount)

    def list_creator_knowledge(self, influencer_id: int) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, influencer_id, title, content, language,
                       is_active, created_at, updated_at
                FROM creator_knowledge WHERE influencer_id = ? ORDER BY id DESC
                """,
                (influencer_id,),
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["is_active"] = bool(row["is_active"])
        return result

    def create_creator_knowledge(
        self, influencer_id: int, *, title: str, content: str, language: str
    ) -> dict:
        now = _utc_now()
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO creator_knowledge
                    (influencer_id, title, content, language,
                     is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (influencer_id, title, content, language, now, now),
            )
            self._connection.commit()
            knowledge_id = int(cursor.lastrowid)
        return next(
            row for row in self.list_creator_knowledge(influencer_id)
            if row["id"] == knowledge_id
        )

    def delete_creator_knowledge(
        self, influencer_id: int, knowledge_id: int
    ) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM creator_knowledge WHERE id = ? AND influencer_id = ?",
                (knowledge_id, influencer_id),
            )
            self._connection.commit()
        return bool(cursor.rowcount)

    def retrieve_creator_knowledge(
        self, influencer_id: int, query: str, *, limit: int = 4
    ) -> str:
        """Return a small lexical retrieval bundle for the current user turn."""
        records = [
            row for row in self.list_creator_knowledge(influencer_id)
            if row["is_active"]
        ]
        query_terms = {
            term for term in re.findall(r"[\w']+", query.casefold())
            if len(term) > 2
        }
        scored = []
        for row in records:
            haystack = f"{row['title']} {row['content']}".casefold()
            score = sum(haystack.count(term) for term in query_terms)
            scored.append((score, row["id"], row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = [row for score, _, row in scored if score > 0][:limit]
        if not selected and records:
            selected = records[: min(2, limit)]
        if not selected:
            return ""
        return "\n\n".join(
            f"Source: {row['title']} ({row['language']})\n{row['content'][:4000]}"
            for row in selected
        )[:10000]

    # ---------------------------------------------------------
    # Web call sessions
    # ---------------------------------------------------------

    def start_web_call_session(
        self,
        *,
        influencer_id: int | None,
        user_id: int | None,
        caller_name: str,
    ) -> int:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO web_call_sessions
                    (influencer_id, user_id, caller_name, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (influencer_id, user_id, caller_name, _utc_now()),
            )
            self._connection.commit()

        return int(cursor.lastrowid)

    def finish_web_call_session(
        self,
        session_id: int,
        *,
        status: str,
        duration_seconds: int,
        error: str = "",
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE web_call_sessions
                SET status = ?, duration_seconds = ?, error = ?,
                    ended_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    max(0, duration_seconds),
                    error,
                    _utc_now(),
                    session_id,
                ),
            )
            self._connection.commit()

    def list_user_web_calls(
        self,
        user_id: int,
        limit: int = 20,
    ) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT w.id, w.status, w.duration_seconds, w.started_at,
                       i.id AS influencer_id, i.name AS influencer_name,
                       i.avatar_url
                FROM web_call_sessions AS w
                LEFT JOIN influencers AS i ON i.id = w.influencer_id
                WHERE w.user_id = ?
                ORDER BY w.id DESC
                LIMIT ?
                """,
                (user_id, max(1, min(limit, 100))),
            ).fetchall()

        return [dict(row) for row in rows]

    def creator_call_summary(
        self,
        influencer_id: int,
        limit: int = 20,
    ) -> dict:
        with self._lock:
            totals = self._connection.execute(
                """
                SELECT COUNT(*) AS total_calls,
                       COALESCE(SUM(duration_seconds), 0) AS total_seconds,
                       COALESCE(SUM(CASE WHEN status = 'completed'
                           THEN 1 ELSE 0 END), 0) AS completed_calls
                FROM web_call_sessions
                WHERE influencer_id = ?
                """,
                (influencer_id,),
            ).fetchone()
            rows = self._connection.execute(
                """
                SELECT id, caller_name, status, duration_seconds,
                       started_at
                FROM web_call_sessions
                WHERE influencer_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (influencer_id, max(1, min(limit, 100))),
            ).fetchall()

        return {
            "total_calls": int(totals["total_calls"]),
            "completed_calls": int(totals["completed_calls"]),
            "total_seconds": int(totals["total_seconds"]),
            "recent_calls": [dict(row) for row in rows],
        }

    # ---------------------------------------------------------
    # Call requests
    # ---------------------------------------------------------

    def record_call_request(
        self,
        *,
        influencer_id: int,
        user_name: str,
        user_phone: str,
        call_sid: str = "",
        status: str = "requested",
        error: str = "",
    ) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO call_requests
                    (influencer_id, user_name, user_phone,
                     call_sid, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    influencer_id,
                    user_name,
                    user_phone,
                    call_sid,
                    status,
                    error,
                    _utc_now(),
                ),
            )
            self._connection.commit()
            request_id = int(cursor.lastrowid)

        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, influencer_id, user_name, user_phone,
                       call_sid, status, error, created_at
                FROM call_requests
                WHERE id = ?
                """,
                (request_id,),
            ).fetchone()

        return dict(row)

    def list_call_requests(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, influencer_id, user_name, user_phone,
                       call_sid, status, error, created_at
                FROM call_requests
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()

        return [dict(row) for row in rows]

    # ---------------------------------------------------------
    # Public support, safety, and growth submissions
    # ---------------------------------------------------------

    def create_public_submission(
        self,
        *,
        kind: str,
        name: str,
        email: str,
        phone: str,
        subject: str,
        message: str,
        metadata_json: str,
    ) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO public_submissions
                    (kind, name, email, phone, subject, message,
                     metadata_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
                """,
                (
                    kind,
                    name,
                    email,
                    phone,
                    subject,
                    message,
                    metadata_json,
                    _utc_now(),
                ),
            )
            self._connection.commit()
            submission_id = int(cursor.lastrowid)
            row = self._connection.execute(
                """
                SELECT id, kind, name, email, phone, subject, message,
                       metadata_json, status, created_at
                FROM public_submissions
                WHERE id = ?
                """,
                (submission_id,),
            ).fetchone()

        return dict(row)

    def list_public_submissions(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, kind, name, email, phone, subject, message,
                       metadata_json, status, created_at
                FROM public_submissions
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()

        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()


_database: VoiceDatabase | None = None


def get_database() -> VoiceDatabase:
    """Return the process-wide database instance."""

    global _database

    if _database is None:
        _database = VoiceDatabase(get_settings().database_path)
        _database.seed_if_empty()

    return _database
