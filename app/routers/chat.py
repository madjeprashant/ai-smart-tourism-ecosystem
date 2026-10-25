from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ChatRequest
from ..security import get_current_user
from ..services.knowledge_base import (
    answer_with_knowledge,
    answer_with_global_travel,
)


router = APIRouter(
    prefix="/api",
    tags=["Travel Chat"],
)


@router.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Travel Assistant routing:

    1. Try the private/approved VoyageAI knowledge first:
       - uploaded tourism documents
       - approved Community Stories

    2. If no relevant knowledge is found, use the worldwide travel
       fallback:
       - Google Search grounding first
       - Gemini general travel knowledge if web grounding is unavailable

    The response returned by the knowledge service contains the source
    classification used by the frontend.
    """
    try:
        # Priority 1: grounded VoyageAI knowledge.
        # Passing db allows approved Community Stories to be synchronized
        # and searched together with uploaded tourism documents.
        result = answer_with_knowledge(
            request.question,
            db=db,
        )

        # Priority 2: worldwide travel fallback.
        # This is reached only when the private knowledge base does not
        # contain sufficiently relevant information.
        if result is None:
            result = answer_with_global_travel(
                request.question,
            )

        if result:
            return result

    except RuntimeError as error:
        # Missing packages and explicit configuration errors are not retrieval
        # misses; surface them so they can be fixed instead of masking them.
        raise HTTPException(status_code=503, detail=str(error)) from error

    except Exception as error:
        error_text = str(error).lower()
        invalid_key = any(marker in error_text for marker in (
            "api_key_invalid", "api key not valid", "invalid api key",
            "unauthenticated", "permission_denied", "permission denied",
            "authentication", "credentials", "billing not enabled",
            "quota project", "model not found", "unsupported model",
        ))
        if invalid_key:
            detail = (
                "Gemini authentication or configuration failed. Check GEMINI_API_KEY, "
                "the selected model, and Google AI Studio project settings."
            )
            raise HTTPException(status_code=502, detail=detail) from error

        # The knowledge service is responsible for converting recoverable
        # retrieval failures into None and attempting the global fallback.
        # Any remaining exception is a genuine service failure; don't hide it.
        raise HTTPException(
            status_code=502,
            detail="The Travel Assistant could not complete the request. Check the server logs and configuration.",
        ) from error

    return {
        "answer": (
            "I could not generate a travel answer right now. "
            "Please try again."
        ),
        "sources": [],
        "source_type": "none",
        "grounded": False,
        "route": "none",
        "web_grounded": False,
    }
