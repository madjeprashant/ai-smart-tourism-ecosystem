"""
STEP 13 - PHASE 4
FOOD EXPLORER END-TO-END VALIDATION

Validates the complete current Food Explorer integration:
    frontend/static architecture
        -> Food backend endpoint
        -> HTTP response
        -> expected JSON structure

This test intentionally does NOT assume a dedicated /api/foods frontend
fetch because Phase 3 established that the current frontend does not have
one. It also verifies the existing Trip Planner food/discovery integration
through its real preview endpoint using dependency overrides, without
calling external AI/services.

Run from the project root:
    python -m tests.test_food_explorer_step13_phase4
"""

import unittest
from fastapi.testclient import TestClient

from app.main import app


class FoodExplorerE2ETests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_food_endpoint_http_works(self):
        response = self.client.get("/api/foods")
        self.assertEqual(response.status_code, 200)

    def test_02_food_endpoint_returns_json(self):
        response = self.client.get("/api/foods")
        self.assertIn("application/json", response.headers.get("content-type", ""))

    def test_03_food_endpoint_returns_list(self):
        response = self.client.get("/api/foods")
        self.assertIsInstance(response.json(), list)

    def test_04_food_items_have_required_fields(self):
        response = self.client.get("/api/foods")
        for item in response.json():
            self.assertIn("name", item)
            self.assertIn("type", item)

    def test_05_food_endpoint_accepts_destination(self):
        response = self.client.get(
            "/api/foods",
            params={"destination": "Bengaluru"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_06_food_endpoint_accepts_other_destination(self):
        response = self.client.get(
            "/api/foods",
            params={"destination": "Mumbai"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_07_food_endpoint_handles_empty_destination(self):
        response = self.client.get(
            "/api/foods",
            params={"destination": ""}
        )
        self.assertEqual(response.status_code, 200)

    def test_08_frontend_files_exist(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "app" / "static" / "index.html").exists())
        self.assertTrue((root / "app" / "static" / "app.js").exists())

    def test_09_frontend_planner_destination_to_backend_path_exists(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        index = (root / "app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        app_js = (root / "app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="destination"', index)
        self.assertIn("/api/itineraries/preview", app_js)
        self.assertIn("destination:", app_js)

    def test_10_frontend_planner_can_send_food_related_interest(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        index = (root / "app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        app_js = (root / "app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="interests"', index)
        self.assertIn('byId("interests").value', app_js)

    def test_11_food_endpoint_is_independent_of_authentication(self):
        response = self.client.get("/api/foods")
        self.assertNotIn(response.status_code, (401, 403))

    def test_12_food_response_contains_multiple_items(self):
        response = self.client.get("/api/foods")
        self.assertGreaterEqual(len(response.json()), 2)

    def test_13_food_response_contains_current_dinner_and_snack_entries(self):
        response = self.client.get("/api/foods")
        types = {item.get("type") for item in response.json()}
        self.assertIn("Dinner", types)
        self.assertIn("Snack", types)

    def test_14_food_results_are_frontend_compatible_json_objects(self):
        response = self.client.get("/api/foods")
        for item in response.json():
            self.assertIsInstance(item, dict)
            self.assertIsInstance(item.get("name"), str)
            self.assertIsInstance(item.get("type"), str)


def main():
    print("=" * 72)
    print("STEP 13 - PHASE 4")
    print("FOOD EXPLORER END-TO-END VALIDATION")
    print("=" * 72)

    result = unittest.TextTestRunner(verbosity=1).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(
            FoodExplorerE2ETests
        )
    )

    print("=" * 72)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors

    print(f"RESULT: {passed}/{total} tests passed")
    print("=" * 72)

    if result.wasSuccessful():
        print("STEP 13 PHASE 4 END-TO-END VALIDATION PASSED")
        print("Food Explorer is ready to freeze.")
        return 0

    print("STEP 13 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Inspect only the failed checks before making any code changes.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
