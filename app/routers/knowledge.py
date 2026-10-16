from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.knowledge_base import add_document, ai_dependencies_available, ai_is_configured, extract_text


router = APIRouter(prefix="/api/knowledge", tags=["AI Knowledge Base"])
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}
MAX_FILE_SIZE = 8 * 1024 * 1024


@router.get("/status")
def knowledge_status():
    key_configured = ai_is_configured()
    packages_available = ai_dependencies_available()
    return {
        "gemini_configured": key_configured,
        "ai_packages_available": packages_available,
        "ready": key_configured and packages_available,
        "accepted_files": sorted(ALLOWED_EXTENSIONS),
    }


@router.post("/upload")
async def upload_knowledge(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload a TXT, MD, CSV, PDF or DOCX tourism document.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Files must be 8 MB or smaller.")
    try:
        chunks = add_document(filename, extract_text(filename, content))
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"message": "Tourism knowledge added successfully.", "filename": filename, "chunks_added": chunks}
