"""
STEP 12 - PHASE 4
AI/RAG TRAVEL ASSISTANT END-TO-END VALIDATION

Run from project root:
    python -m tests.test_ai_rag_assistant_step12_phase4

Deterministic: external Gemini/Google calls are mocked.
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


class Step12Phase4E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.js = (STATIC / "app.js").read_text(encoding="utf-8")
        from app.main import app
        cls.app = app

    def test_01_frontend_backend_contract(self):
        self.assertIn('id="chatForm"', self.index)
        self.assertIn('id="question"', self.index)
        self.assertIn('id="chatAnswer"', self.index)
        self.assertIn('api("/api/chat"', self.js)
        self.assertIn("JSON.stringify({ question:", self.js)

    def test_02_frontend_auth_guard_precedes_api(self):
        self.assertLess(self.js.find("getToken()"), self.js.find('api("/api/chat"'))
        self.assertIn("Please sign in first", self.js)
        self.assertIn('bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show()', self.js)

    def test_03_frontend_renders_answer_and_sources_safely(self):
        self.assertIn("response.answer", self.js)
        self.assertIn("escapeHtml(response.answer)", self.js)
        self.assertIn("response.sources", self.js)
        self.assertIn("answer-sources", self.js)
        self.assertIn("escapeHtml(response.sources.join", self.js)
        self.assertNotIn("${response.answer}", self.js)

    def test_04_frontend_handles_loading_and_errors(self):
        self.assertIn('answer.textContent = "Thinking..."', self.js)
        self.assertIn("catch (error)", self.js)
        self.assertIn("answer.textContent = error.message", self.js)

    def test_05_api_route_is_post(self):
        routes = [r for r in self.app.routes if getattr(r, "path", None) == "/api/chat"]
        self.assertTrue(routes)
        methods = set()
        for route in routes:
            methods.update(getattr(route, "methods", set()) or set())
        self.assertIn("POST", methods)

    def test_06_scope_guard_e2e_service(self):
        from app.services.knowledge_base import answer_question
        result = answer_question("Write Python code to sort a list")
        self.assertEqual(result["route"], "scope_guard")
        self.assertEqual(result["sources"], [])
        self.assertFalse(result["grounded"])

    def test_07_private_rag_priority_e2e_service(self):
        from app.services import knowledge_base
        expected = {
            "answer": "Project-grounded answer.",
            "sources": ["Uploaded project knowledge"],
            "source_type": "private_rag",
            "grounded": True,
            "route": "private_rag",
            "web_grounded": False,
        }
        with patch.object(knowledge_base, "answer_with_knowledge",
                          return_value=expected),              patch.object(knowledge_base, "answer_with_global_travel",
                          side_effect=AssertionError("Global fallback was incorrectly used")):
            result = knowledge_base.answer_question("Tell me about the project")
        self.assertEqual(result, expected)

    def test_08_web_route_e2e_service(self):
        from app.services import knowledge_base
        expected = {
            "answer": "Web-grounded travel answer.",
            "sources": ["Google Search"],
            "source_type": "web_travel",
            "grounded": True,
            "route": "web_search",
            "web_grounded": True,
        }
        with patch.object(knowledge_base, "answer_with_knowledge", return_value=None),              patch.object(knowledge_base, "answer_with_global_travel", return_value=expected):
            result = knowledge_base.answer_question("Best places to visit in Japan")
        self.assertEqual(result, expected)

    def test_09_global_fallback_e2e_service(self):
        from app.services import knowledge_base
        expected = {
            "answer": "General travel answer.",
            "sources": ["Gemini general travel knowledge"],
            "source_type": "global_travel",
            "grounded": False,
            "route": "global_fallback",
            "web_grounded": False,
        }
        with patch.object(knowledge_base, "answer_with_knowledge", return_value=None),              patch.object(knowledge_base, "answer_with_global_travel", return_value=expected):
            result = knowledge_base.answer_question("What should I pack for Europe?")
        self.assertEqual(result, expected)

    def test_10_rag_exception_falls_back(self):
        from app.services import knowledge_base
        expected = {
            "answer": "Fallback travel answer.",
            "sources": ["Google Search"],
            "source_type": "web_travel",
            "grounded": True,
            "route": "web_search",
            "web_grounded": True,
        }
        with patch.object(knowledge_base, "answer_with_knowledge",
                          side_effect=RuntimeError("RAG unavailable")),              patch.object(knowledge_base, "answer_with_global_travel",
                          return_value=expected):
            result = knowledge_base.answer_question("Where should I travel?")
        self.assertEqual(result, expected)

    def test_11_authenticated_http_chat_e2e(self):
        from fastapi.testclient import TestClient
        from app.routers.chat import get_current_user

        expected = {
            "answer": "Try Mysuru Palace.",
            "sources": ["Project knowledge"],
            "source_type": "private_rag",
            "grounded": True,
            "route": "private_rag",
            "web_grounded": False,
        }

        async def fake_user():
            return {"id": 1, "sub": "1"}

        self.app.dependency_overrides[get_current_user] = fake_user
        try:
            with patch("app.routers.chat.answer_question", return_value=expected):
                response = TestClient(self.app).post(
                    "/api/chat",
                    json={"question": "What should I visit in Mysuru?"},
                    headers={"Authorization": "Bearer test-token"},
                )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            for key, value in expected.items():
                self.assertEqual(body.get(key), value)
        finally:
            self.app.dependency_overrides.pop(get_current_user, None)

    def test_12_invalid_payload_e2e(self):
        from fastapi.testclient import TestClient
        from app.routers.chat import get_current_user

        async def fake_user():
            return {"id": 1, "sub": "1"}

        self.app.dependency_overrides[get_current_user] = fake_user
        try:
            response = TestClient(self.app).post(
                "/api/chat",
                json={"question": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            self.assertEqual(response.status_code, 422)
        finally:
            self.app.dependency_overrides.pop(get_current_user, None)

    def test_13_unauthenticated_http_chat_is_protected(self):
        from fastapi.testclient import TestClient
        response = TestClient(self.app).post(
            "/api/chat", json={"question": "What should I visit in Goa?"}
        )
        self.assertIn(response.status_code, {401, 403})

    def test_14_chat_request_model_contract(self):
        from app.schemas import ChatRequest
        self.assertEqual(
            ChatRequest(question="Best places to visit in Goa").question,
            "Best places to visit in Goa",
        )
        with self.assertRaises(Exception):
            ChatRequest(question="")

    def test_15_frontend_element_ids_remain_consistent(self):
        ids = set(re.findall(r'id="([^"]+)"', self.index))
        for element_id in ("chatForm", "question", "chatAnswer"):
            self.assertIn(element_id, ids)
            self.assertIn(f'byId("{element_id}")', self.js)


def main():
    print("=" * 72)
    print("STEP 12 - PHASE 4")
    print("AI/RAG TRAVEL ASSISTANT END-TO-END VALIDATION")
    print("=" * 72)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Step12Phase4E2E)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print("=" * 72)
    print(f"RESULT: {passed}/{result.testsRun} tests passed")
    print("=" * 72)
    if result.wasSuccessful():
        print("STEP 12 PHASE 4 END-TO-END VALIDATION PASSED")
        print("AI/RAG Travel Assistant is ready to freeze.")
        return 0
    print("STEP 12 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Do not modify project code yet. Review the failing checks first.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
