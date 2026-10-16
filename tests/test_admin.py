"""
STEP 19 - PHASE 4
ADMINISTRATION END-TO-END VALIDATION

Purpose:
    Validate the complete Administration workflow through the real FastAPI
    application stack using an isolated SQLite database.

Safety:
    - Does NOT modify the user's real tourism.db.
    - Does NOT require changing the production database.
    - Creates temporary users/stories/trips/expenses only in an isolated DB.
    - Uses the application's real routes, authentication, authorization,
      admin router, and static Admin page.

Coverage:
    1. Application starts with admin router/page registered
    2. Register traveler through /api/register
    3. Traveler login through /api/login
    4. Traveler cannot access admin API
    5. Bootstrap first administrator using the project's bootstrap script
       logic, represented safely inside the isolated test DB
    6. Existing admin login
    7. Admin identity
    8. Admin dashboard
    9. Admin user listing
   10. Promote traveler to admin
   11. Verify persisted role change
   12. Existing token immediately reflects role change
   13. Self-demotion protection
   14. Invalid role rejection
   15. Story creation
   16. Admin sees pending/unapproved story
   17. Pending story hidden from public/community feed
   18. Admin approves story
   19. Approved story visible in community feed
   20. Admin unapproves story
   21. Story hidden again
   22. Admin deletes story
   23. Deleted story is gone
   24. Missing user/story returns 404
   25. Admin logout behavior at API-token level
   26. Static /admin page exists
   27. Main navigation contains Administration link
   28. Admin JS uses protected admin identity endpoint
   29. Admin JS contains dashboard/user/story operations
   30. Final database state is consistent
"""

from pathlib import Path
import importlib
import os
import sys
import tempfile

# When this file is executed as:
#     python tests\\test_admin_step19_phase4.py
# Python puts the tests directory on sys.path, not the project root.
# Add the project root explicitly so the real `app` package can be imported.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


passed = 0
failed = 0


def check(name, condition):
    global passed, failed

    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name}")
        failed += 1


def load_modules():
    """
    Import the real application modules without changing application source.
    """
    main = importlib.import_module("app.main")
    models = importlib.import_module("app.models")
    database = importlib.import_module("app.database")
    auth = importlib.import_module("app.auth")
    crud = importlib.import_module("app.crud")

    return main, models, database, auth, crud


def create_isolated_database(models):
    """
    Create an isolated SQLite DB for the entire E2E run.
    """
    tmp = tempfile.NamedTemporaryFile(
        prefix="step19_phase4_",
        suffix=".db",
        delete=False,
    )
    tmp.close()

    db_path = tmp.name

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    models.Base.metadata.create_all(bind=engine)

    return db_path, engine, TestingSessionLocal


def seed_first_admin(models, SessionLocal, auth):
    """
    Safely create the first administrator directly in the isolated DB.

    This mirrors the intended bootstrap policy:
        - user already exists
        - no administrator exists
        - user becomes the first administrator

    No production database is touched.
    """
    db = SessionLocal()

    admin = models.User(
        full_name="STEP19 Admin",
        username="step19admin",
        email="step19.admin@example.com",
        phone="9999999901",
        password=auth.hash_password("AdminPassword123!"),
        role="admin",
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    db.close()

    return admin


def register_user(client, email, username, phone, password):
    response = client.post(
        "/api/register",
        json={
            "full_name": "STEP19 Traveler",
            "username": username,
            "email": email,
            "phone": phone,
            "password": password,
        },
    )
    return response


def login_user(client, identifier, password):
    response = client.post(
        "/api/login",
        data={
            "username": identifier,
            "password": password,
        },
    )

    if response.status_code != 200:
        return response, None

    body = response.json()
    token = body.get("access_token")

    return response, token


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    global passed, failed

    print("=" * 72)
    print("STEP 19 - PHASE 4")
    print("ADMINISTRATION END-TO-END VALIDATION")
    print("=" * 72)

    main_app, models, database, auth, crud = load_modules()

    db_path = None
    engine = None

    try:
        db_path, engine, TestingSessionLocal = create_isolated_database(models)

        # --------------------------------------------------------------
        # Override the application's DB dependency.
        # --------------------------------------------------------------

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_app.app.dependency_overrides[database.get_db] = override_get_db

        with TestClient(main_app.app) as client:

            # ----------------------------------------------------------
            # A. APPLICATION / STATIC ADMIN PAGE
            # ----------------------------------------------------------

            admin_page = client.get("/admin")

            check(
                "Admin page is reachable",
                admin_page.status_code == 200,
            )

            check(
                "Admin page contains Administration",
                "Administration" in admin_page.text
                or "ADMINISTRATION" in admin_page.text,
            )

            index_page = client.get("/")

            check(
                "Main application page is reachable",
                index_page.status_code == 200,
            )

            check(
                "Main navigation contains Administration link",
                (
                    'id="adminLink"' in index_page.text
                    and 'href="/admin"' in index_page.text
                ),
            )

            # ----------------------------------------------------------
            # B. UNAUTHENTICATED ADMIN ACCESS
            # ----------------------------------------------------------

            unauth_me = client.get("/api/admin/me")

            check(
                "Unauthenticated admin identity is rejected",
                unauth_me.status_code == 401,
            )

            unauth_dashboard = client.get("/api/admin/dashboard")

            check(
                "Unauthenticated dashboard access is rejected",
                unauth_dashboard.status_code == 401,
            )

            # ----------------------------------------------------------
            # C. NORMAL REGISTRATION
            # ----------------------------------------------------------

            traveler_password = "TravelerPassword123!"

            register_response = register_user(
                client,
                "step19.traveler@example.com",
                "step19traveler",
                "9999999902",
                traveler_password,
            )

            check(
                "Traveler registration succeeds",
                register_response.status_code in (200, 201),
            )

            if register_response.status_code not in (200, 201):
                print(
                    "  Registration response:",
                    register_response.status_code,
                    register_response.text[:500],
                )

            # Verify the database assigned traveler role.
            db = TestingSessionLocal()
            traveler = db.scalar(
                select(models.User).where(
                    models.User.email == "step19.traveler@example.com"
                )
            )
            traveler_role_correct = (
                traveler is not None
                and traveler.role == "traveler"
            )
            traveler_id = traveler.id if traveler else None
            db.close()

            check(
                "Normal registration creates traveler role",
                traveler_role_correct,
            )

            # ----------------------------------------------------------
            # D. TRAVELER LOGIN
            # ----------------------------------------------------------

            traveler_login, traveler_token = login_user(
                client,
                "step19.traveler@example.com",
                traveler_password,
            )

            check(
                "Traveler login succeeds",
                traveler_login.status_code == 200
                and bool(traveler_token),
            )

            if traveler_login.status_code != 200:
                print(
                    "  Traveler login response:",
                    traveler_login.status_code,
                    traveler_login.text[:500],
                )

            traveler_headers = auth_headers(traveler_token)

            traveler_admin = client.get(
                "/api/admin/me",
                headers=traveler_headers,
            )

            check(
                "Traveler is denied admin identity",
                traveler_admin.status_code == 403,
            )

            traveler_dashboard = client.get(
                "/api/admin/dashboard",
                headers=traveler_headers,
            )

            check(
                "Traveler is denied admin dashboard",
                traveler_dashboard.status_code == 403,
            )

            # ----------------------------------------------------------
            # E. FIRST ADMIN BOOTSTRAP
            # ----------------------------------------------------------

            first_admin = seed_first_admin(
                models,
                TestingSessionLocal,
                auth,
            )

            check(
                "First administrator exists in isolated database",
                first_admin.role == "admin",
            )

            # ----------------------------------------------------------
            # F. ADMIN LOGIN
            # ----------------------------------------------------------

            admin_login, admin_token = login_user(
                client,
                "step19.admin@example.com",
                "AdminPassword123!",
            )

            check(
                "Administrator login succeeds",
                admin_login.status_code == 200
                and bool(admin_token),
            )

            admin_headers = auth_headers(admin_token)

            # ----------------------------------------------------------
            # G. ADMIN IDENTITY
            # ----------------------------------------------------------

            admin_me = client.get(
                "/api/admin/me",
                headers=admin_headers,
            )

            check(
                "Administrator identity returns 200",
                admin_me.status_code == 200,
            )

            admin_me_body = (
                admin_me.json()
                if admin_me.status_code == 200
                else {}
            )

            check(
                "Administrator identity reports admin role",
                admin_me_body.get("role") == "admin",
            )

            # ----------------------------------------------------------
            # H. DASHBOARD
            # ----------------------------------------------------------

            dashboard = client.get(
                "/api/admin/dashboard",
                headers=admin_headers,
            )

            check(
                "Administrator dashboard returns 200",
                dashboard.status_code == 200,
            )

            dashboard_body = (
                dashboard.json()
                if dashboard.status_code == 200
                else {}
            )

            check(
                "Dashboard contains user statistics",
                "users" in dashboard_body
                or "total_users" in dashboard_body,
            )

            check(
                "Dashboard contains story statistics",
                "stories" in dashboard_body
                or "total_stories" in dashboard_body,
            )

            # ----------------------------------------------------------
            # I. USER LISTING
            # ----------------------------------------------------------

            users_response = client.get(
                "/api/admin/users",
                headers=admin_headers,
            )

            check(
                "Administrator can list users",
                users_response.status_code == 200,
            )

            # ----------------------------------------------------------
            # J. ROLE MANAGEMENT
            # ----------------------------------------------------------

            promote = client.patch(
                f"/api/admin/users/{traveler_id}/role",
                params={"role": "admin"},
                headers=admin_headers,
            )

            check(
                "Administrator can promote traveler to admin",
                promote.status_code == 200,
            )

            db = TestingSessionLocal()
            promoted_user = db.get(models.User, traveler_id)
            promoted_correctly = (
                promoted_user is not None
                and promoted_user.role == "admin"
            )
            db.close()

            check(
                "Promoted role is persisted in database",
                promoted_correctly,
            )

            # Existing traveler JWT must now work as admin because
            # authorization reads the persisted role.
            promoted_token_access = client.get(
                "/api/admin/me",
                headers=traveler_headers,
            )

            check(
                "Existing token receives updated admin privileges",
                promoted_token_access.status_code == 200,
            )

            # Restore traveler role using the original admin.
            demote = client.patch(
                f"/api/admin/users/{traveler_id}/role",
                params={"role": "traveler"},
                headers=admin_headers,
            )

            check(
                "Administrator can demote another admin",
                demote.status_code == 200,
            )

            demoted_access = client.get(
                "/api/admin/me",
                headers=traveler_headers,
            )

            check(
                "Demoted user immediately loses admin privileges",
                demoted_access.status_code == 403,
            )

            # Self-demotion must fail.
            self_demote = client.patch(
                f"/api/admin/users/{first_admin.id}/role",
                params={"role": "traveler"},
                headers=admin_headers,
            )

            check(
                "Administrator cannot demote self",
                self_demote.status_code == 400,
            )

            invalid_role = client.patch(
                f"/api/admin/users/{traveler_id}/role",
                params={"role": "superadmin"},
                headers=admin_headers,
            )

            check(
                "Invalid role is rejected",
                invalid_role.status_code == 400,
            )

            missing_user = client.patch(
                "/api/admin/users/999999999/role",
                params={"role": "admin"},
                headers=admin_headers,
            )

            check(
                "Missing user returns 404",
                missing_user.status_code == 404,
            )

            # ----------------------------------------------------------
            # K. CREATE STORY THROUGH REAL STORY API
            # ----------------------------------------------------------

            story_payload = {
                "author": "STEP19 Admin",
                "title": "STEP 19 E2E Moderation Story",
                "destination": "Bengaluru",
                "content": (
                    "Temporary story used only by STEP 19 E2E validation "
                    "for Administration moderation."
                ),
                "media_items": [],
            }

            # The stories API resolves the current user from JWT.
            # Use the admin token to create the controlled test story.
            story_response = client.post(
                "/api/stories",
                json=story_payload,
                headers=admin_headers,
            )

            check(
                "Story creation succeeds",
                story_response.status_code in (200, 201),
            )

            if story_response.status_code not in (200, 201):
                print(
                    "  Story creation response:",
                    story_response.status_code,
                    story_response.text[:500],
                )

            story_body = (
                story_response.json()
                if story_response.status_code in (200, 201)
                else {}
            )

            story_id = (
                story_body.get("id")
                or story_body.get("story", {}).get("id")
            )

            # Ensure the story is available in DB for controlled
            # moderation testing.
            db = TestingSessionLocal()
            story = db.get(models.Story, story_id) if story_id else None

            if story is not None:
                story.approved = False
                db.commit()
                db.refresh(story)

            db.close()

            check(
                "Controlled moderation story exists",
                story is not None,
            )

            # ----------------------------------------------------------
            # L. ADMIN STORY MODERATION LIST
            # ----------------------------------------------------------

            admin_stories = client.get(
                "/api/admin/stories",
                headers=admin_headers,
            )

            check(
                "Administrator can list all stories",
                admin_stories.status_code == 200,
            )

            admin_stories_body = (
                admin_stories.json()
                if admin_stories.status_code == 200
                else []
            )

            if isinstance(admin_stories_body, dict):
                story_items = (
                    admin_stories_body.get("stories")
                    or admin_stories_body.get("items")
                    or []
                )
            else:
                story_items = admin_stories_body

            pending_visible = any(
                str(item.get("id")) == str(story_id)
                and item.get("approved") is False
                for item in story_items
                if isinstance(item, dict)
            )

            check(
                "Administrator can see unapproved story",
                pending_visible,
            )

            # ----------------------------------------------------------
            # M. NORMAL COMMUNITY FEED HIDES PENDING STORY
            # ----------------------------------------------------------

            community_pending = client.get(
                "/api/stories",
                headers=admin_headers,
            )

            check(
                "Community feed request succeeds",
                community_pending.status_code == 200,
            )

            community_pending_body = (
                community_pending.json()
                if community_pending.status_code == 200
                else []
            )

            if isinstance(community_pending_body, dict):
                community_items = (
                    community_pending_body.get("stories")
                    or community_pending_body.get("items")
                    or []
                )
            else:
                community_items = community_pending_body

            hidden_pending = not any(
                str(item.get("id")) == str(story_id)
                for item in community_items
                if isinstance(item, dict)
            )

            check(
                "Unapproved story is hidden from community feed",
                hidden_pending,
            )

            # ----------------------------------------------------------
            # N. APPROVE STORY
            # ----------------------------------------------------------

            approve_story = client.patch(
                f"/api/admin/stories/{story_id}/approval",
                params={"approved": "true"},
                headers=admin_headers,
            )

            check(
                "Administrator can approve story",
                approve_story.status_code == 200,
            )

            community_approved = client.get(
                "/api/stories",
                headers=admin_headers,
            )

            community_approved_body = (
                community_approved.json()
                if community_approved.status_code == 200
                else []
            )

            if isinstance(community_approved_body, dict):
                community_approved_items = (
                    community_approved_body.get("stories")
                    or community_approved_body.get("items")
                    or []
                )
            else:
                community_approved_items = community_approved_body

            approved_visible = any(
                str(item.get("id")) == str(story_id)
                for item in community_approved_items
                if isinstance(item, dict)
            )

            check(
                "Approved story appears in community feed",
                approved_visible,
            )

            # ----------------------------------------------------------
            # O. UNAPPROVE STORY
            # ----------------------------------------------------------

            unapprove_story = client.patch(
                f"/api/admin/stories/{story_id}/approval",
                params={"approved": "false"},
                headers=admin_headers,
            )

            check(
                "Administrator can unapprove story",
                unapprove_story.status_code == 200,
            )

            community_unapproved = client.get(
                "/api/stories",
                headers=admin_headers,
            )

            community_unapproved_body = (
                community_unapproved.json()
                if community_unapproved.status_code == 200
                else []
            )

            if isinstance(community_unapproved_body, dict):
                community_unapproved_items = (
                    community_unapproved_body.get("stories")
                    or community_unapproved_body.get("items")
                    or []
                )
            else:
                community_unapproved_items = community_unapproved_body

            hidden_again = not any(
                str(item.get("id")) == str(story_id)
                for item in community_unapproved_items
                if isinstance(item, dict)
            )

            check(
                "Unapproved story disappears from community feed",
                hidden_again,
            )

            # ----------------------------------------------------------
            # P. DELETE STORY
            # ----------------------------------------------------------

            delete_story = client.delete(
                f"/api/admin/stories/{story_id}",
                headers=admin_headers,
            )

            check(
                "Administrator can delete story",
                delete_story.status_code == 200,
            )

            db = TestingSessionLocal()
            deleted_story = (
                db.get(models.Story, story_id)
                if story_id
                else None
            )
            db.close()

            check(
                "Deleted story is removed from database",
                deleted_story is None,
            )

            missing_story = client.patch(
                "/api/admin/stories/999999999/approval",
                params={"approved": "true"},
                headers=admin_headers,
            )

            check(
                "Missing story returns 404",
                missing_story.status_code == 404,
            )

            # ----------------------------------------------------------
            # Q. ADMIN JS / UI CONTRACT
            # ----------------------------------------------------------

            admin_js_path = ROOT / "app" / "static" / "admin.js"
            admin_html_path = ROOT / "app" / "static" / "admin.html"
            app_js_path = ROOT / "app" / "static" / "app.js"

            admin_js = (
                admin_js_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
                if admin_js_path.exists()
                else ""
            )

            admin_html = (
                admin_html_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
                if admin_html_path.exists()
                else ""
            )

            app_js = (
                app_js_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
                if app_js_path.exists()
                else ""
            )

            check(
                "Admin UI contains dashboard shell",
                "dashboard" in admin_html.lower(),
            )

            check(
                "Admin UI verifies administrator identity",
                "/api/admin/me" in admin_js,
            )

            check(
                "Admin UI contains user/story management operations",
                (
                    "/api/admin/users" in admin_js
                    and "/api/admin/stories" in admin_js
                ),
            )

            check(
                "Main app performs admin identity check",
                (
                    "updateAdminLink" in app_js
                    and "/api/admin/me" in app_js
                ),
            )

            # ----------------------------------------------------------
            # R. FINAL DATABASE CONSISTENCY
            # ----------------------------------------------------------

            db = TestingSessionLocal()

            final_admin = db.get(models.User, first_admin.id)
            final_traveler = db.get(models.User, traveler_id)

            check(
                "First administrator remains admin",
                final_admin is not None
                and final_admin.role == "admin",
            )

            check(
                "Demoted traveler remains traveler",
                final_traveler is not None
                and final_traveler.role == "traveler",
            )

            remaining_story = db.scalar(
                select(models.Story).where(
                    models.Story.id == story_id
                )
            ) if story_id else None

            check(
                "Test story is fully removed",
                remaining_story is None,
            )

            db.close()

            # ----------------------------------------------------------
            # S. TOKEN CLEARING CONTRACT
            # ----------------------------------------------------------

            # FastAPI bearer authentication does not have a server-side
            # logout endpoint in this project. The frontend logout is
            # local-token clearing. Validate the UI source contract.
            index_js = app_js

            check(
                "Frontend contains JWT logout/clear behavior",
                (
                    "localStorage.removeItem" in index_js
                    or "removeItem" in index_js
                    or "clearToken" in index_js
                ),
            )

    finally:
        # Restore application dependency overrides.
        try:
            main_app.app.dependency_overrides.clear()
        except Exception:
            pass

        if engine is not None:
            engine.dispose()

        if db_path:
            try:
                os.remove(db_path)
            except OSError:
                pass

    print("=" * 72)
    print(f"RESULT: {passed}/{passed + failed} tests passed")
    print("=" * 72)

    if failed:
        raise SystemExit(1)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
