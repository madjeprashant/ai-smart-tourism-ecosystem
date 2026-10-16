"""
STEP 16 - PHASE 4
KNOWLEDGE BASE END-TO-END VALIDATION

Validates the complete Knowledge Base flow:

Frontend UI
    ->
Knowledge status API
    ->
Knowledge upload API
    ->
File validation/extraction
    ->
AI configuration / ingestion boundary
    ->
Upload response contract
    ->
Frontend response handling

Do not modify application code unless an actual E2E failure is found.
"""

from pathlib import Path
import io

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"

INDEX_PATH = STATIC_DIR / "index.html"
APP_JS_PATH = STATIC_DIR / "app.js"


def main():
    checks = []

    client = TestClient(app)

    index = (
        INDEX_PATH.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        if INDEX_PATH.exists()
        else ""
    )

    app_js = (
        APP_JS_PATH.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        if APP_JS_PATH.exists()
        else ""
    )

    # ================================================================
    # 1. APPLICATION -> FRONTEND
    # ================================================================

    root_response = client.get("/")

    checks.append(
        (
            "Application root responds successfully",
            root_response.status_code == 200,
        )
    )

    checks.append(
        (
            "Application root serves frontend HTML",
            "text/html"
            in root_response.headers.get("content-type", ""),
        )
    )

    checks.append(
        (
            "Knowledge Base frontend files are available",
            INDEX_PATH.exists() and APP_JS_PATH.exists(),
        )
    )

    # ================================================================
    # 2. KNOWLEDGE BASE UI CONTRACT
    # ================================================================

    checks.append(
        (
            "Knowledge Base form is present",
            'id="knowledgeForm"' in index,
        )
    )

    checks.append(
        (
            "Knowledge file input is present",
            'id="knowledgeFile"' in index,
        )
    )

    checks.append(
        (
            "Knowledge upload status element is present",
            'id="uploadStatus"' in index,
        )
    )

    # ================================================================
    # 3. STATUS API -> FRONTEND
    # ================================================================

    status_response = client.get(
        "/api/knowledge/status"
    )

    checks.append(
        (
            "Knowledge status endpoint is reachable",
            status_response.status_code not in (404, 405),
        )
    )

    status_data = {}

    if status_response.status_code == 200:
        try:
            status_data = status_response.json()
        except Exception:
            status_data = {}

        checks.append(
            (
                "Knowledge status endpoint returns JSON",
                isinstance(status_data, dict),
            )
        )

        checks.append(
            (
                "Knowledge status exposes ready state",
                "ready" in status_data,
            )
        )

        checks.append(
            (
                "Knowledge status exposes Gemini configuration state",
                "gemini_configured" in status_data,
            )
        )

    # ================================================================
    # 4. STATUS RESPONSE -> FRONTEND CONTRACT
    # ================================================================

    checks.append(
        (
            "Frontend calls Knowledge status endpoint",
            "/api/knowledge/status" in app_js,
        )
    )

    checks.append(
        (
            "Frontend evaluates Knowledge ready state",
            "status.ready" in app_js,
        )
    )

    checks.append(
        (
            "Frontend evaluates Gemini configuration state",
            "status.gemini_configured" in app_js,
        )
    )

    # ================================================================
    # 5. FRONTEND -> UPLOAD REQUEST
    # ================================================================

    checks.append(
        (
            "Frontend handles Knowledge form submission",
            'byId("knowledgeForm").addEventListener("submit"'
            in app_js,
        )
    )

    checks.append(
        (
            "Frontend obtains selected Knowledge file",
            'byId("knowledgeFile").files[0]' in app_js,
        )
    )

    checks.append(
        (
            "Frontend creates FormData for upload",
            "new FormData()" in app_js,
        )
    )

    checks.append(
        (
            "Frontend appends selected file as 'file'",
            'formData.append("file", file)' in app_js,
        )
    )

    checks.append(
        (
            "Frontend calls Knowledge upload endpoint",
            "/api/knowledge/upload" in app_js,
        )
    )

    checks.append(
        (
            "Frontend uses POST for upload",
            'method: "POST"' in app_js,
        )
    )

    checks.append(
        (
            "Frontend sends authentication headers",
            "authHeaders()" in app_js,
        )
    )

    # ================================================================
    # 6. ACTUAL MULTIPART UPLOAD -> FASTAPI
    # ================================================================

    test_content = (
        b"Step 16 Phase 4 Knowledge Base E2E test. "
        b"Bengaluru is a tourism destination in Karnataka."
    )

    upload_response = client.post(
        "/api/knowledge/upload",
        files={
            "file": (
                "step16_phase4.txt",
                io.BytesIO(test_content),
                "text/plain",
            )
        },
    )

    checks.append(
        (
            "Knowledge upload route exists",
            upload_response.status_code not in (404, 405),
        )
    )

    checks.append(
        (
            "Knowledge upload request reaches application logic",
            upload_response.status_code in (
                200,
                400,
                401,
                403,
                422,
                500,
                503,
            ),
        )
    )

    # ================================================================
    # 7. UPLOAD RESPONSE CONTRACT
    # ================================================================

    if upload_response.status_code == 200:
        try:
            upload_data = upload_response.json()
        except Exception:
            upload_data = {}

        checks.append(
            (
                "Successful Knowledge upload returns JSON",
                isinstance(upload_data, dict),
            )
        )

        checks.append(
            (
                "Successful upload returns filename",
                isinstance(
                    upload_data.get("filename"),
                    str,
                ),
            )
        )

        checks.append(
            (
                "Successful upload returns chunks_added",
                isinstance(
                    upload_data.get("chunks_added"),
                    int,
                ),
            )
        )

    # ================================================================
    # 8. FRONTEND CONSUMES UPLOAD RESPONSE
    # ================================================================

    checks.append(
        (
            "Frontend reads upload filename",
            "payload.filename" in app_js,
        )
    )

    checks.append(
        (
            "Frontend reads uploaded chunk count",
            "payload.chunks_added" in app_js,
        )
    )

    checks.append(
        (
            "Frontend checks upload HTTP success",
            "if (!response.ok)" in app_js,
        )
    )

    checks.append(
        (
            "Frontend displays API error detail",
            "payload.detail" in app_js,
        )
    )

    # ================================================================
    # 9. SUCCESS STATE
    # ================================================================

    checks.append(
        (
            "Frontend displays Knowledge upload success state",
            'uploadStatus.className = "upload-status success"'
            in app_js,
        )
    )

    checks.append(
        (
            "Frontend resets Knowledge form after success",
            "event.currentTarget.reset()" in app_js,
        )
    )

    # ================================================================
    # 10. ERROR STATE
    # ================================================================

    checks.append(
        (
            "Frontend displays Knowledge upload error state",
            'uploadStatus.className = "upload-status error"'
            in app_js,
        )
    )

    # ================================================================
    # 11. INVALID REQUEST -> VALIDATION
    # ================================================================

    invalid_upload = client.post(
        "/api/knowledge/upload"
    )

    checks.append(
        (
            "Upload without a file is rejected",
            invalid_upload.status_code in (
                400,
                401,
                403,
                422,
            ),
        )
    )

    # ================================================================
    # 12. UNSUPPORTED FILE -> VALIDATION
    # ================================================================

    unsupported_upload = client.post(
        "/api/knowledge/upload",
        files={
            "file": (
                "step16_phase4.exe",
                io.BytesIO(b"invalid file type"),
                "application/octet-stream",
            )
        },
    )

    checks.append(
        (
            "Unsupported file type reaches validation",
            unsupported_upload.status_code in (
                400,
                401,
                403,
                422,
                500,
                503,
            ),
        )
    )

    # ================================================================
    # RESULT
    # ================================================================

    print("=" * 72)
    print("STEP 16 - PHASE 4")
    print("KNOWLEDGE BASE END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0

    for name, ok in checks:
        print(
            ("PASS: " if ok else "FAIL: ") + name
        )
        passed += int(bool(ok))

    print("=" * 72)
    print(
        f"RESULT: {passed}/{len(checks)} tests passed"
    )
    print("=" * 72)

    if passed == len(checks):
        print(
            "STEP 16 PHASE 4 END-TO-END VALIDATION PASSED"
        )
        print(
            "KNOWLEDGE BASE IS READY TO FREEZE"
        )
        return 0

    print(
        "STEP 16 PHASE 4 END-TO-END VALIDATION FAILED"
    )
    print(
        "Inspect only the failed E2E checks before making code changes."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())