from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ChatRequest
from ..security import get_current_user
from ..services.knowledge_base import answer_question


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
    Main API entry point for the VoyageAI hybrid travel assistant.

    The actual routing remains centralized inside:
        knowledge_base.answer_question()

    Routing order:

    1. Reject invalid/empty questions.
    2. Check private project knowledge and approved Community Stories.
    3. If private knowledge is insufficient, use worldwide travel routing.
    4. Worldwide routing may use Google Search grounding.
    5. If web grounding is unavailable, use Gemini general travel knowledge.
    6. Preserve truthful source and route metadata for the frontend.

    Authentication is required through get_current_user().
    """

    # ---------------------------------------------------------
    # 1. Validate the incoming question
    # ---------------------------------------------------------
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Please enter a travel question.",
        )

    # ---------------------------------------------------------
    # 2. Protect against unnecessarily huge requests
    # ---------------------------------------------------------
    if len(question) > 2000:
        raise HTTPException(
            status_code=422,
            detail="Please keep your travel question under 2000 characters.",
        )

    # ---------------------------------------------------------
    # 3. Use the centralized hybrid router
    # ---------------------------------------------------------
    try:
        result = answer_question(
            question,
            db=db,
        )

        # answer_question() is responsible for deciding:
        #
        # private knowledge
        #        ↓
        # worldwide fallback
        #
        # Therefore the API route must NOT perform a second
        # independent routing decision.

        if result is not None:
            return result

    # ---------------------------------------------------------
    # 4. Handle known backend/runtime failures
    # ---------------------------------------------------------
    except RuntimeError as error:
        error_text = str(error)

        if "RESOURCE_EXHAUSTED" in error_text or "429" in error_text:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The Gemini API quota is temporarily exhausted. "
                    "Please wait for the quota to reset and try again."
                ),
            ) from error

        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except Exception as error:
        error_text = str(error)

        # Invalid Gemini API key
        if (
            "API_KEY_INVALID" in error_text
            or "API key not valid" in error_text
        ):
            raise HTTPException(
                status_code=502,
                detail=(
                    "The Gemini API key configured in .env is invalid. "
                    "Create a new key in Google AI Studio, update "
                    "GEMINI_API_KEY, and restart the application."
                ),
            ) from error

        # Gemini quota/rate limit
        if (
            "RESOURCE_EXHAUSTED" in error_text
            or "429" in error_text
        ):
            raise HTTPException(
                status_code=503,
                detail=(
                    "The Gemini API quota is temporarily exhausted. "
                    "Please wait for the quota to reset and try again."
                ),
            ) from error

        # Other unexpected AI/backend error
        raise HTTPException(
            status_code=502,
            detail=(
                "The travel assistant could not generate an answer "
                "right now. Please try again."
            ),
        ) from error

    # ---------------------------------------------------------
    # 5. Safe final response
    # ---------------------------------------------------------
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