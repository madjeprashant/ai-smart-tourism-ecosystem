"""
PHASE 1 - STEP 5
BACKEND CHAT API VALIDATION

This test validates the real FastAPI /api/chat boundary without calling Gemini.

Step 4 already validates the internal hybrid routing. Step 5 therefore focuses
on the API contract: authentication, successful response delivery, metadata,
and request validation.

The test is deliberately compatible with both supported chat architectures:
- chat.py calling answer_question(...)
- chat.py directly calling answer_with_knowledge(...) then
  answer_with_global_travel(...)

No Gemini, Google Search, FAISS, or real DB work is required.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.security import get_current_user
from app.routers import chat as chat_router


PRIVATE_RESULT = {
    "answer": "North Goa answer from approved project knowledge.",
    "sources": ["Community story — Chasing Sunsets and Coastal Cafes"],
    "source_type": "community_story",
    "grounded": True,
    "route": "private_knowledge",
    "web_grounded": False,
}

GLOBAL_RESULT = {
    "answer": "Tokyo is a worldwide travel destination with temples, museums, food, and modern districts.",
    "sources": ["Gemini general travel knowledge"],
    "source_type": "global_travel",
    "grounded": False,
    "route": "global_fallback",
    "web_grounded": False,
}


def fake_db():
    yield None


def fake_user():
    return {"sub": "step5-test@example.com"}


def _patch_chat_route(result):
    """
    Patch whichever chat architecture the actual project is using.

    We patch the route module's imported symbols and, when present, its
    answer_question symbol. This avoids accidentally testing a stale function
    reference and does not modify project files.
    """
    original = {}

    # Direct-function architecture.
    for name in ("answer_with_knowledge", "answer_with_global_travel"):
        if hasattr(chat_router, name):
            original[name] = getattr(chat_router, name)
            if name == "answer_with_knowledge":
                setattr(chat_router, name, lambda question, db=None: result)
            else:
                setattr(chat_router, name, lambda question: result)

    # Unified-router architecture.
    if hasattr(chat_router, "answer_question"):
        original["answer_question"] = chat_router.answer_question
        setattr(
            chat_router,
            "answer_question",
            lambda question, db=None: result,
        )

    # Some imported functions can be held in the chat endpoint's globals.
    # Update those references too, but only for names that actually exist.
    endpoint_globals = getattr(chat_router.chat, "__globals__", {})
    for name in ("answer_with_knowledge", "answer_with_global_travel", "answer_question"):
        if name in endpoint_globals:
            original[("globals", name)] = endpoint_globals[name]
            if name == "answer_with_knowledge":
                endpoint_globals[name] = lambda question, db=None: result
            elif name == "answer_with_global_travel":
                endpoint_globals[name] = lambda question: result
            else:
                endpoint_globals[name] = lambda question, db=None: result

    return original


def _restore_chat_route(original):
    for key, value in original.items():
        if isinstance(key, tuple):
            _, name = key
            chat_router.chat.__globals__[name] = value
        else:
            setattr(chat_router, key, value)


def run():
    print("=" * 65)
    print("PHASE 1 - STEP 5")
    print("BACKEND CHAT API VALIDATION")
    print("=" * 65)

    app.dependency_overrides.clear()

    # ------------------------------------------------------------
    # TEST 1: Authentication guard
    # ------------------------------------------------------------
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"question": "What is the best time to visit Tokyo?"},
        )

    print("\n--- Authentication guard ---")
    if response.status_code == 401:
        print("PASS")
    else:
        print("FAIL")
        print("Expected HTTP 401, got:", response.status_code)
        print("Response:", response.text)

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db

    try:
        # --------------------------------------------------------
        # TEST 2: Private response reaches API unchanged
        # --------------------------------------------------------
        original = _patch_chat_route(PRIVATE_RESULT)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/chat",
                    json={
                        "question":
                        "What does the traveller recommend for exploring North Goa?"
                    },
                )
        finally:
            _restore_chat_route(original)

        body = response.json()

        print("\n--- Private knowledge response ---")
        if (
            response.status_code == 200
            and body.get("route") == "private_knowledge"
            and body.get("source_type") == "community_story"
            and body.get("grounded") is True
        ):
            print("PASS")
        else:
            print("FAIL")
            print("Status:", response.status_code)
            print("Body:", body)

        # --------------------------------------------------------
        # TEST 3: Worldwide fallback response reaches API
        # --------------------------------------------------------
        original = _patch_chat_route(GLOBAL_RESULT)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/chat",
                    json={"question": "What are the best places to visit in Tokyo?"},
                )
        finally:
            _restore_chat_route(original)

        body = response.json()

        print("\n--- Worldwide fallback response ---")
        if (
            response.status_code == 200
            and body.get("route") == "global_fallback"
            and body.get("source_type") == "global_travel"
            and body.get("grounded") is False
        ):
            print("PASS")
        else:
            print("FAIL")
            print("Status:", response.status_code)
            print("Body:", body)

        # --------------------------------------------------------
        # TEST 4: Source metadata contract
        # --------------------------------------------------------
        print("\n--- Source metadata ---")
        required = {
            "answer",
            "sources",
            "source_type",
            "grounded",
            "route",
            "web_grounded",
        }
        missing = sorted(required - set(body.keys()))

        if not missing:
            print("PASS")
        else:
            print("FAIL")
            print("Missing fields:", missing)
            print("Body:", body)

        # --------------------------------------------------------
        # TEST 5: Pydantic request validation
        # --------------------------------------------------------
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"question": "Hi"},
            )

        print("\n--- Request validation ---")
        if response.status_code == 422:
            print("PASS")
        else:
            print("FAIL")
            print("Expected HTTP 422, got:", response.status_code)
            print("Response:", response.text)

        print("\n" + "=" * 65)
        print("RESULT: 5/5 API CONTRACT TESTS EXPECTED")
        print("=" * 65)
        print("No Gemini quota was consumed by this test.")
        print("Step 4 remains responsible for testing the internal hybrid router.")
        print("If all five tests show PASS, Step 5 is complete.")

    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    run()
