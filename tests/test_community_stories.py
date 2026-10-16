"""
STEP 11 - PHASE 4
COMMUNITY STORIES END-TO-END VALIDATION

Purpose:
Validate the complete existing Community Stories flow using the real FastAPI
application, an isolated test database, isolated upload storage, and the
existing frontend contract.

Flow validated:
    Existing Stories UI contract
        -> POST /api/stories/media
        -> media response
        -> POST /api/stories
        -> database persistence / ownership
        -> GET /api/stories
        -> community feed visibility
        -> frontend rendering contract

The project's real database, real upload directory, and external services are
not used.

Run from the project root:
    python -m tests.test_community_stories_e2e_step11
"""

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Story, User
from app.routers.stories import get_current_user
from app.routers import stories


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"

# ----------------------------------------------------------------------
# Isolated in-memory database
# ----------------------------------------------------------------------
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_users():
    db = TestingSessionLocal()

    user_a = User(
        full_name="Stories E2E User A",
        username="stories_e2e_a",
        email="stories_e2e_a@example.com",
        phone="9011111111",
        password="test-password",
        role="traveler",
    )

    user_b = User(
        full_name="Stories E2E User B",
        username="stories_e2e_b",
        email="stories_e2e_b@example.com",
        phone="9022222222",
        password="test-password",
        role="traveler",
    )

    db.add_all([user_a, user_b])
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)

    result = (
        user_a.id,
        user_a.email,
        user_b.id,
        user_b.email,
    )

    db.close()
    return result


def read_static(filename):
    path = STATIC_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def set_authenticated_user(email):
    app.dependency_overrides[get_current_user] = lambda: {"sub": email}


def clear_story_auth():
    app.dependency_overrides.pop(get_current_user, None)


def main():
    reset_database()

    (
        user_a_id,
        user_a_email,
        user_b_id,
        user_b_email,
    ) = seed_users()

    app.dependency_overrides[get_db] = override_get_db

    # Never write E2E media into the project's real uploads directory.
    original_upload_dir = stories.UPLOAD_DIR
    temp_upload_dir = Path(tempfile.mkdtemp(prefix="stories_e2e_"))
    stories.UPLOAD_DIR = temp_upload_dir

    index_source = read_static("index.html")
    app_js_source = read_static("app.js")
    checks = []

    try:
        with TestClient(app) as client:

            # ==============================================================
            # 1. EXISTING UI -> API CONTRACT
            # ==============================================================
            checks.append((
                "Stories UI points to the existing media upload endpoint",
                'fetch("/api/stories/media"' in app_js_source,
            ))

            checks.append((
                "Stories UI points to the existing story creation endpoint",
                'api("/api/stories"' in app_js_source,
            ))

            checks.append((
                "Stories UI reloads the existing community feed endpoint",
                'api("/api/stories")' in app_js_source,
            ))

            checks.append((
                "Stories UI sends media_items after upload",
                "media_items" in app_js_source,
            ))

            checks.append((
                "Stories UI refreshes the feed after publishing",
                "await loadStories();" in app_js_source,
            ))

            checks.append((
                "Stories UI has the existing Stories form",
                'id="storyForm"' in index_source,
            ))

            # ==============================================================
            # 2. AUTHENTICATION BOUNDARY
            # ==============================================================
            clear_story_auth()

            response = client.get("/api/stories")
            checks.append((
                "Unauthenticated Stories feed is rejected",
                response.status_code in {401, 403},
            ))

            response = client.post(
                "/api/stories",
                json={
                    "author": "Unauthenticated",
                    "destination": "Goa",
                    "title": "Should Not Publish",
                    "content": "This story must not be created without authentication.",
                },
            )
            checks.append((
                "Unauthenticated story creation is rejected",
                response.status_code in {401, 403},
            ))

            response = client.post(
                "/api/stories/media",
                files=[
                    ("files", ("blocked.jpg", b"blocked-media", "image/jpeg")),
                ],
            )
            checks.append((
                "Unauthenticated media upload is rejected",
                response.status_code in {401, 403},
            ))

            # ==============================================================
            # 3. USER A: MEDIA UPLOAD -> STORY CREATION
            # ==============================================================
            set_authenticated_user(user_a_email)

            media_files = [
                ("files", ("goa-memory.jpg", b"e2e-image-bytes", "image/jpeg")),
                ("files", ("goa-memory.mp3", b"e2e-audio-bytes", "audio/mpeg")),
                ("files", ("goa-memory.mp4", b"e2e-video-bytes", "video/mp4")),
            ]

            media_response = client.post(
                "/api/stories/media",
                files=media_files,
            )

            media_data = (
                media_response.json()
                if media_response.status_code == 201
                else {}
            )
            media_items = media_data.get("media_items", [])

            checks.append((
                "Authenticated media upload succeeds",
                media_response.status_code == 201,
            ))

            checks.append((
                "Media upload returns all three media items",
                len(media_items) == 3,
            ))

            checks.append((
                "Uploaded image is classified as image",
                any(
                    item.get("media_type") == "image"
                    for item in media_items
                ),
            ))

            checks.append((
                "Uploaded audio is classified as audio",
                any(
                    item.get("media_type") == "audio"
                    for item in media_items
                ),
            ))

            checks.append((
                "Uploaded video is classified as video",
                any(
                    item.get("media_type") == "video"
                    for item in media_items
                ),
            ))

            checks.append((
                "Uploaded media files are written to isolated E2E storage",
                len(list(temp_upload_dir.iterdir())) == 3,
            ))

            # ==============================================================
            # 4. CREATE STORY THROUGH THE REAL API
            # ==============================================================
            story_payload = {
                "author": "Stories E2E User A",
                "destination": "Goa",
                "title": "Sunset at Fort Aguada",
                "content": (
                    "The sunset view from Fort Aguada was the highlight of "
                    "our Goa trip and made a great final travel memory."
                ),
                "media_items": media_items,
            }

            create_response = client.post(
                "/api/stories",
                json=story_payload,
            )

            created = (
                create_response.json()
                if create_response.status_code == 201
                else {}
            )

            checks.append((
                "Story creation succeeds after media upload",
                create_response.status_code == 201,
            ))

            checks.append((
                "Created story preserves the submitted destination",
                created.get("destination") == "Goa",
            ))

            checks.append((
                "Created story preserves the submitted title",
                created.get("title") == "Sunset at Fort Aguada",
            ))

            checks.append((
                "Created story preserves the submitted content",
                created.get("content") == story_payload["content"],
            ))

            checks.append((
                "Created story returns all uploaded media items",
                len(created.get("media_items", [])) == 3,
            ))

            checks.append((
                "Created story is linked to User A",
                created.get("user_id") == user_a_id,
            ))

            # ==============================================================
            # 5. DATABASE PERSISTENCE
            # ==============================================================
            db = TestingSessionLocal()
            persisted = None

            if created.get("id") is not None:
                persisted = db.scalar(
                    select(Story).where(Story.id == created["id"])
                )

            checks.append((
                "Created story is persisted in the database",
                persisted is not None,
            ))

            checks.append((
                "Persisted story has User A ownership",
                persisted is not None
                and persisted.user_id == user_a_id,
            ))

            checks.append((
                "Persisted story retains media_items",
                persisted is not None
                and isinstance(persisted.media_items, list)
                and len(persisted.media_items) == 3,
            ))

            db.close()

            # ==============================================================
            # 6. USER A FEED -> API -> FRONTEND CONTRACT
            # ==============================================================
            feed_a_response = client.get("/api/stories")
            feed_a = (
                feed_a_response.json()
                if feed_a_response.status_code == 200
                else []
            )

            checks.append((
                "User A can load the community Stories feed",
                feed_a_response.status_code == 200,
            ))

            checks.append((
                "User A feed contains the newly published story",
                any(
                    item.get("id") == created.get("id")
                    for item in feed_a
                ),
            ))

            checks.append((
                "Community feed returns the published story as approved",
                any(
                    item.get("id") == created.get("id")
                    and item.get("approved") is True
                    for item in feed_a
                ),
            ))

            checks.append((
                "Existing frontend renders destination from the feed response",
                'escapeHtml(item.destination)' in app_js_source,
            ))

            checks.append((
                "Existing frontend renders title from the feed response",
                'escapeHtml(item.title)' in app_js_source,
            ))

            checks.append((
                "Existing frontend renders content from the feed response",
                'escapeHtml(item.content)' in app_js_source,
            ))

            checks.append((
                "Existing frontend renders author from the feed response",
                'escapeHtml(item.author)' in app_js_source,
            ))

            checks.append((
                "Existing frontend renders story media",
                'class="story-media"' in app_js_source,
            ))

            # ==============================================================
            # 7. USER B -> SHARED COMMUNITY FEED
            # ==============================================================
            set_authenticated_user(user_b_email)

            feed_b_response = client.get("/api/stories")
            feed_b = (
                feed_b_response.json()
                if feed_b_response.status_code == 200
                else []
            )

            checks.append((
                "User B can load the shared community Stories feed",
                feed_b_response.status_code == 200,
            ))

            checks.append((
                "User B can see User A's approved story",
                any(
                    item.get("id") == created.get("id")
                    for item in feed_b
                ),
            ))

            checks.append((
                "Community feed is not incorrectly owner-isolated",
                any(
                    item.get("id") == created.get("id")
                    and item.get("user_id") == user_a_id
                    for item in feed_b
                ),
            ))

            # ==============================================================
            # 8. USER B CREATION -> SHARED FEED
            # ==============================================================
            user_b_payload = {
                "author": "Stories E2E User B",
                "destination": "Mysuru",
                "title": "Palace Evening Walk",
                "content": (
                    "An evening walk around Mysuru Palace was peaceful, "
                    "photogenic, and worth adding to the trip."
                ),
            }

            user_b_create = client.post(
                "/api/stories",
                json=user_b_payload,
            )

            user_b_story = (
                user_b_create.json()
                if user_b_create.status_code == 201
                else {}
            )

            checks.append((
                "User B can publish a community story",
                user_b_create.status_code == 201,
            ))

            checks.append((
                "User B story is linked to User B",
                user_b_story.get("user_id") == user_b_id,
            ))

            feed_after_b = client.get("/api/stories")
            feed_after_b_data = (
                feed_after_b.json()
                if feed_after_b.status_code == 200
                else []
            )

            checks.append((
                "User B story appears in the community feed",
                any(
                    item.get("id") == user_b_story.get("id")
                    for item in feed_after_b_data
                ),
            ))

            # ==============================================================
            # 9. APPROVAL VISIBILITY CONTRACT
            # ==============================================================
            db = TestingSessionLocal()

            hidden_story = Story(
                author="Hidden E2E Story",
                destination="Test Destination",
                title="Unapproved Story",
                content="This explicitly unapproved story must stay out of the feed.",
                approved=False,
                user_id=user_a_id,
            )

            db.add(hidden_story)
            db.commit()
            db.refresh(hidden_story)
            hidden_id = hidden_story.id
            db.close()

            set_authenticated_user(user_b_email)

            visibility_response = client.get("/api/stories")
            visibility_feed = (
                visibility_response.json()
                if visibility_response.status_code == 200
                else []
            )

            checks.append((
                "Explicitly unapproved story is hidden from the community feed",
                all(item.get("id") != hidden_id for item in visibility_feed),
            ))

            # ==============================================================
            # 10. FINAL PERSISTENCE / ORDERING CHECK
            # ==============================================================
            final_feed_response = client.get("/api/stories")
            final_feed = (
                final_feed_response.json()
                if final_feed_response.status_code == 200
                else []
            )

            published_ids = {
                created.get("id"),
                user_b_story.get("id"),
            }

            returned_published = [
                item.get("id")
                for item in final_feed
                if item.get("id") in published_ids
            ]

            checks.append((
                "Final community feed still contains both approved stories",
                len(returned_published) == 2,
            ))

            if len(final_feed) >= 2:
                checks.append((
                    "Community feed is newest-first",
                    final_feed[0].get("created_at")
                    >= final_feed[1].get("created_at"),
                ))
            else:
                checks.append((
                    "Community feed is newest-first",
                    False,
                ))

    finally:
        app.dependency_overrides.clear()
        stories.UPLOAD_DIR = original_upload_dir
        shutil.rmtree(temp_upload_dir, ignore_errors=True)

    print("=" * 72)
    print("STEP 11 - PHASE 4")
    print("COMMUNITY STORIES END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0
    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += int(bool(ok))

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    if passed == len(checks):
        print("STEP 11 PHASE 4 END-TO-END VALIDATION PASSED")
        print("COMMUNITY STORIES IS READY TO FREEZE")
        return 0

    print("STEP 11 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Fix only the failed E2E checks before freezing Community Stories.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
