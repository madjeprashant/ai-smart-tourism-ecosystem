"""LangChain, FAISS and Gemini helpers for the VoyageAI tourism assistant.

Routing:
1. Approved/uploaded VoyageAI knowledge is tried first.
2. Clearly relevant retrieved context is used for a grounded answer.
3. If retrieval is missing or the grounded model says it cannot answer,
   return None so chat.py can continue to the worldwide travel fallback.
4. Worldwide fallback uses Google Search grounding first, then Gemini's
   general travel knowledge if web grounding is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)

# Load the project's .env whenever this service is imported.
# This keeps FastAPI, tests and direct Python execution consistent.
load_dotenv(PROJECT_ROOT / ".env")

KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "tourism_knowledge"
FAISS_DIR = PROJECT_ROOT / "data" / "faiss_index"

COMMUNITY_FAISS_DIR = PROJECT_ROOT / "data" / "community_faiss_index"
COMMUNITY_STATE_FILE = PROJECT_ROOT / "data" / "community_faiss_state.json"


# Retrieval settings.
RETRIEVAL_K_PER_SOURCE = 6
MAX_CONTEXT_DOCUMENTS = 5
MIN_LEXICAL_RELEVANCE = 0.12

# Keep the grounded/private route on the project's existing model, but use a
# separate, higher-availability model for worldwide fallback questions.
# This prevents the global route from being blocked when the 3.5 Flash quota
# has been exhausted by repeated development/testing calls.
PRIVATE_MODEL = os.getenv("VOYAGEAI_PRIVATE_MODEL", "gemini-3.5-flash")
WEB_MODEL = os.getenv("VOYAGEAI_WEB_MODEL", "gemini-2.5-flash")

# Worldwide general-knowledge fallback deliberately uses a separate, lightweight
# model.  This keeps worldwide answers available even when the private 3.5 Flash
# quota is exhausted.  Older projects sometimes have VOYAGEAI_GLOBAL_MODEL set
# to gemini-2.5-flash or gemini-3.5-flash, so ignore those legacy values here.
_legacy_global = os.getenv("VOYAGEAI_GLOBAL_MODEL", "").strip()
if _legacy_global in {"gemini-2.5-flash", "gemini-3.5-flash"} or not _legacy_global:
    GLOBAL_MODEL = "gemini-3.1-flash-lite"
else:
    GLOBAL_MODEL = _legacy_global


STOP_WORDS = {
    "a", "an", "and", "are", "about", "before", "can", "could", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "please", "should", "the", "to", "what", "when", "where",
    "which", "who", "why", "with", "would", "you", "your", "visit",
    "visiting", "travel", "traveller", "traveler", "best", "things",
    "place", "places", "day", "days",
}


def ai_is_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def ai_dependencies_available() -> bool:
    try:
        _imports()
        return True
    except RuntimeError:
        return False


def _imports():
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_core.documents import Document
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            GoogleGenerativeAIEmbeddings,
        )
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as error:
        raise RuntimeError(
            "AI packages are not installed. Run: pip install -r requirements.txt"
        ) from error

    return (
        FAISS,
        Document,
        ChatGoogleGenerativeAI,
        GoogleGenerativeAIEmbeddings,
        RecursiveCharacterTextSplitter,
    )


def _embeddings():
    _, _, _, GoogleGenerativeAIEmbeddings, _ = _imports()
    return GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")


def extract_text(filename: str, content: bytes) -> str:
    """Extract text from accepted tourism knowledge-base uploads."""
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".md", ".csv"}:
        return content.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            from io import BytesIO
            from pypdf import PdfReader

            return "\n".join(
                page.extract_text() or ""
                for page in PdfReader(BytesIO(content)).pages
            )
        except ImportError as error:
            raise ValueError(
                "PDF support needs pypdf. Run: pip install -r requirements.txt"
            ) from error

    if suffix == ".docx":
        try:
            from io import BytesIO
            from docx import Document as WordDocument

            return "\n".join(
                paragraph.text
                for paragraph in WordDocument(BytesIO(content)).paragraphs
            )
        except ImportError as error:
            raise ValueError(
                "DOCX support needs python-docx. Run: pip install -r requirements.txt"
            ) from error

    raise ValueError("Use a .txt, .md, .csv, .pdf or .docx file.")


def add_document(filename: str, text: str) -> int:
    """Chunk one uploaded document and merge it into the FAISS index."""
    if not ai_is_configured():
        raise RuntimeError(
            "Set GEMINI_API_KEY in .env before creating the AI knowledge base."
        )

    FAISS, Document, _, _, RecursiveCharacterTextSplitter = _imports()

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
    ).split_text(text)

    documents = [
        Document(
            page_content=chunk,
            metadata={
                "source": filename,
                "source_type": "tourism_document",
            },
        )
        for chunk in chunks
    ]

    if not documents:
        raise ValueError("The uploaded file does not contain readable text.")

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    FAISS_DIR.parent.mkdir(parents=True, exist_ok=True)

    (KNOWLEDGE_DIR / filename).write_text(text, encoding="utf-8")

    if FAISS_DIR.exists():
        store = FAISS.load_local(
            str(FAISS_DIR),
            _embeddings(),
            allow_dangerous_deserialization=True,
        )
        store.add_documents(documents)
    else:
        store = FAISS.from_documents(documents, _embeddings())

    store.save_local(str(FAISS_DIR))
    return len(documents)


def _community_documents(stories: list):
    """Convert approved Story rows into traceable LangChain Documents."""
    _, Document, _, _, RecursiveCharacterTextSplitter = _imports()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
    )

    documents = []

    for story in stories:
        text = (
            f"Destination: {story.destination}\n"
            f"Title: {story.title}\n"
            f"Traveller: {story.author}\n"
            f"Experience: {story.content}"
        )

        for chunk in splitter.split_text(text):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": f"Community story — {story.title}",
                        "source_type": "community_story",
                        "story_id": story.id,
                        "destination": story.destination,
                        "author": story.author,
                    },
                )
            )

    return documents


def sync_community_stories(db) -> int:
    """Keep the community FAISS index synchronized with approved stories."""
    if not ai_is_configured():
        return 0

    from ..models import Story

    stories = list(
        db.scalars(
            select(Story)
            .where(Story.approved.is_(True))
            .order_by(Story.id.asc())
        ).all()
    )

    current_ids = [story.id for story in stories]

    previous_ids = None

    if COMMUNITY_STATE_FILE.exists():
        try:
            previous_ids = json.loads(
                COMMUNITY_STATE_FILE.read_text(encoding="utf-8")
            ).get("story_ids")
        except (OSError, ValueError, TypeError):
            previous_ids = None

    if COMMUNITY_FAISS_DIR.exists() and previous_ids == current_ids:
        return len(stories)

    FAISS, _, _, _, _ = _imports()

    if stories:
        documents = _community_documents(stories)

        if documents:
            COMMUNITY_FAISS_DIR.parent.mkdir(parents=True, exist_ok=True)

            store = FAISS.from_documents(documents, _embeddings())
            store.save_local(str(COMMUNITY_FAISS_DIR))
    else:
        if COMMUNITY_FAISS_DIR.exists():
            shutil.rmtree(COMMUNITY_FAISS_DIR)

    COMMUNITY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMUNITY_STATE_FILE.write_text(
        json.dumps({"story_ids": current_ids}),
        encoding="utf-8",
    )

    return len(stories)


def _tokens(text: str) -> set[str]:
    """Return meaningful lowercase tokens for a lightweight relevance check."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())

    return {
        word
        for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def _relevance_features(question: str, document) -> tuple[float, bool]:
    """Calculate lexical overlap and explicit destination matching."""
    query_terms = _tokens(question)

    if not query_terms:
        return 0.0, False

    text = document.page_content or ""
    metadata = document.metadata or {}

    searchable = " ".join(
        [
            text,
            str(metadata.get("destination", "")),
            str(metadata.get("source", "")),
            str(metadata.get("author", "")),
        ]
    )

    doc_terms = _tokens(searchable)

    overlap = len(query_terms & doc_terms) / max(len(query_terms), 1)

    question_lower = question.lower()
    destination = str(
        metadata.get("destination", "")
    ).strip().lower()

    destination_match = bool(
        destination
        and len(destination) >= 4
        and destination in question_lower
    )

    return overlap, destination_match


def _select_relevant_documents(question: str, retrieved: list[tuple]) -> list:
    """Re-rank FAISS candidates and discard clearly unrelated context."""
    if not retrieved:
        return []

    # FAISS similarity score/distance is used only for ranking candidates.
    ranked = sorted(retrieved, key=lambda item: item[1])

    max_rank = max(len(ranked) - 1, 1)
    candidates = []

    for rank, (doc, distance, source_group) in enumerate(ranked):
        lexical_score, destination_match = _relevance_features(
            question,
            doc,
        )

        semantic_rank_score = 1.0 - (rank / max_rank)

        final_score = (
            0.55 * semantic_rank_score
            + 0.30 * lexical_score
            + (0.15 if destination_match else 0.0)
        )

        # Critical guard:
        # A semantically similar but unrelated document must NOT become
        # grounding context for Gemini.
        relevant = (
            destination_match
            or lexical_score >= MIN_LEXICAL_RELEVANCE
        )

        if relevant:
            candidates.append(
                (
                    final_score,
                    doc,
                    distance,
                    source_group,
                    lexical_score,
                    destination_match,
                )
            )

    candidates.sort(key=lambda item: item[0], reverse=True)

    selected = []
    per_group = {}
    seen_sources = set()

    for item in candidates:
        _, doc, _, source_group, _, _ = item

        source = doc.metadata.get(
            "source",
            "uploaded guide",
        )

        if source in seen_sources:
            continue

        if per_group.get(source_group, 0) >= 3:
            continue

        selected.append(item)
        seen_sources.add(source)
        per_group[source_group] = (
            per_group.get(source_group, 0) + 1
        )

        if len(selected) >= MAX_CONTEXT_DOCUMENTS:
            break

    return selected


def _content_to_text(content) -> str:
    """Normalize Gemini response content into plain text."""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
                if value:
                    parts.append(str(value))
            elif isinstance(item, str):
                parts.append(item)

        return "\n".join(parts).strip()

    return str(content).strip()


def _looks_like_unsupported_answer(answer: str) -> bool:
    """Detect Gemini saying the retrieved context is insufficient."""
    normalized = " ".join((answer or "").lower().split())

    if not normalized:
        return True

    exact_markers = {
        "__no_grounded_answer__",
        "i cannot answer from the provided context",
        "i can't answer from the provided context",
        "the provided context does not contain",
        "the available knowledge does not contain enough information",
        "the provided knowledge does not contain enough information",
        "i don't have enough information in the provided context",
        "i do not have enough information in the provided context",
        "not enough information in the provided context",
    }

    if any(marker in normalized for marker in exact_markers):
        return True

    return False


def _is_fatal_ai_configuration_error(error: Exception) -> bool:
    """Return True for errors that must not be hidden by fallback handling."""
    message = str(error).lower()
    markers = (
        "api_key_invalid", "api key not valid", "invalid api key",
        "unauthenticated", "permission_denied", "permission denied",
        "authentication", "credentials", "billing not enabled",
        "quota project", "model not found", "unsupported model",
        "gemini_api_key", "missing gemini", "ai packages are not installed",
    )
    return any(marker in message for marker in markers)


def answer_with_knowledge(question: str, db=None) -> dict | None:
    """Answer from relevant private/approved knowledge only.

    IMPORTANT:
    Returning None when the knowledge base cannot answer is intentional.
    chat.py uses None to continue to the worldwide travel fallback.
    """
    if not ai_is_configured():
        return None

    FAISS, _, ChatGoogleGenerativeAI, _, _ = _imports()

    retrieved = []

    # Retrieval is best-effort: a corrupt/missing index or transient vector-store
    # failure should not prevent the general travel fallback. Authentication,
    # invalid-key, missing-package and configuration errors must still surface.
    try:
        # 1. Uploaded tourism documents.
        if FAISS_DIR.exists():
            store = FAISS.load_local(
                str(FAISS_DIR),
                _embeddings(),
                allow_dangerous_deserialization=True,
            )
            retrieved.extend(
                (doc, score, "tourism_document")
                for doc, score in store.similarity_search_with_score(
                    question, k=RETRIEVAL_K_PER_SOURCE,
                )
            )

        # 2. Approved community stories.
        if db is not None:
            sync_community_stories(db)
            if COMMUNITY_FAISS_DIR.exists():
                community_store = FAISS.load_local(
                    str(COMMUNITY_FAISS_DIR),
                    _embeddings(),
                    allow_dangerous_deserialization=True,
                )
                retrieved.extend(
                    (doc, score, "community_story")
                    for doc, score in community_store.similarity_search_with_score(
                        question, k=RETRIEVAL_K_PER_SOURCE,
                    )
                )
    except Exception as error:
        if _is_fatal_ai_configuration_error(error):
            raise
        logger.warning(
            "Tourism knowledge retrieval failed; trying global travel fallback: %s",
            error,
            exc_info=True,
        )
        return None

    # 3. Relevance gate.
    selected = _select_relevant_documents(
        question,
        retrieved,
    )

    # THIS IS THE IMPORTANT FIX.
    # Do NOT return an "unsupported" answer here.
    # Returning None lets chat.py call answer_with_global_travel().
    if not selected:
        return None

    documents = [item[1] for item in selected]

    context = "\n\n".join(
        (
            f"Source: {doc.metadata.get('source', 'uploaded guide')}\n"
            f"Source type: "
            f"{doc.metadata.get('source_type', 'tourism_document')}\n"
            f"{doc.page_content}"
        )
        for doc in documents
    )

    model = ChatGoogleGenerativeAI(
        model=PRIVATE_MODEL,
        temperature=0.2,
    )

    prompt = f"""You are VoyageAI, a grounded tourism assistant.

Answer the traveller's question ONLY from the supplied knowledge context.

The context can contain:
- curated tourism documents
- approved community stories written by travellers

Grounding rules:
1. Do not add facts, places, prices, timings, recommendations or claims
   that are not supported by the context.
2. Treat community stories as personal traveller experiences, not official
   or guaranteed facts.
3. When the context contains both source types, you may combine them, but
   keep the distinction clear.
4. If the context does not actually answer the question, output exactly:
   __NO_GROUNDED_ANSWER__
5. Prefer the most directly relevant destination/topic evidence.
6. Do not use unrelated retrieved documents just because they are present.

Question:
{question}

Knowledge context:
{context}
"""

    response = model.invoke(prompt)
    answer_text = _content_to_text(response.content)

    # 4. Second safety gate.
    # If Gemini itself confirms that the retrieved context is insufficient,
    # return None so worldwide travel can answer the question.
    if _looks_like_unsupported_answer(answer_text):
        return None

    sources = sorted(
        {
            doc.metadata.get(
                "source",
                "uploaded guide",
            )
            for doc in documents
        }
    )

    source_types = sorted(
        {
            doc.metadata.get(
                "source_type",
                "tourism_document",
            )
            for doc in documents
        }
    )

    if source_types == ["community_story"]:
        source_type = "community_story"
    elif source_types == ["tourism_document"]:
        source_type = "knowledge_base"
    else:
        source_type = "community_and_knowledge"

    return {
        "answer": answer_text,
        "sources": sources,
        "source_type": source_type,
        "grounded": True,
        "retrieved_count": len(documents),
        "route": "private_knowledge",
        "web_grounded": False,
    }


def _extract_grounding_sources(response) -> list[str]:
    """Extract human-readable web sources from Gemini grounding metadata."""
    sources = []

    try:
        candidate = response.candidates[0]
        metadata = getattr(
            candidate,
            "grounding_metadata",
            None,
        )

        chunks = getattr(
            metadata,
            "grounding_chunks",
            None,
        ) or []

        for chunk in chunks:
            web = getattr(chunk, "web", None)

            if web is None:
                continue

            title = getattr(web, "title", None)
            uri = getattr(web, "uri", None)

            if title and uri:
                sources.append(f"{title} — {uri}")
            elif title:
                sources.append(str(title))
            elif uri:
                sources.append(str(uri))

    except Exception:
        pass

    return list(dict.fromkeys(sources))[:6]


def _answer_with_google_search(question: str) -> dict | None:
    """Use Gemini managed Google Search grounding for worldwide travel.

    The web-grounded route uses a separate web model rather than the
    private RAG model so private-model quota exhaustion does not disable
    worldwide travel answers.
    """
    if not ai_is_configured():
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY")
    )

    prompt = f"""You are VoyageAI, a worldwide travel assistant.

The private VoyageAI AI Knowledge Base and approved Community Stories did
not contain enough relevant information for this question.

Use Google Search to find reliable, current public travel information and
answer the traveller's question.

Rules:
1. Answer travel-related questions directly and practically for destinations
   anywhere in the world.
2. Prefer official tourism authorities, government sources, transport
   operators, major attractions, and reputable travel sources when
   appropriate.
3. Clearly distinguish facts from suggestions.
4. Do not invent bookings, availability, prices, opening hours, visa rules,
   weather, safety alerts, or other time-sensitive details.
5. If a current detail is not verified by search results, say so.
6. Keep the answer concise and useful.
7. Do not claim that web information came from VoyageAI's private knowledge
   base or community stories.
8. If the question is not travel-related, politely explain that VoyageAI
   focuses on travel assistance.

Question:
{question}
"""

    response = client.models.generate_content(
        model=WEB_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ],
            temperature=0.2,
        ),
    )

    answer_text = getattr(
        response,
        "text",
        None,
    ) or ""

    answer_text = answer_text.strip()

    if not answer_text:
        return None

    web_sources = _extract_grounding_sources(response)

    return {
        "answer": answer_text,
        "sources": web_sources or ["Google Search"],
        "source_type": "web_travel",
        "grounded": True,
        "route": "web_search",
        "web_grounded": True,
    }


def answer_with_global_travel(question: str) -> dict | None:
    """Worldwide fallback: Google Search first, Gemini knowledge second.

    Worldwide answers use GLOBAL_MODEL, independently from the private
    knowledge-generation model.
    """
    if not ai_is_configured():
        return None

    # First choice: current public web information.
    try:
        web_result = _answer_with_google_search(question)

        if web_result:
            return web_result

    except Exception as error:
        if _is_fatal_ai_configuration_error(error):
            raise
        # Search grounding is optional; transient/search-tool failures may
        # fall through to Gemini general knowledge. Log them for diagnosis.
        logger.warning("Google Search grounding failed; trying Gemini fallback: %s", error, exc_info=True)

    # Second choice: Gemini's general travel knowledge.
    _, _, ChatGoogleGenerativeAI, _, _ = _imports()

    model = ChatGoogleGenerativeAI(
        model=GLOBAL_MODEL,
        temperature=0.25,
    )

    prompt = f"""You are VoyageAI, a worldwide travel assistant.

The project's private AI Knowledge Base and approved Community Stories did
not contain enough relevant information for this question, and live web
grounding is currently unavailable.

Answer using your general travel knowledge so the traveller can still get
useful help for destinations anywhere in the world.

Rules:
1. Answer travel-related questions directly and practically.
2. Do not pretend that information came from VoyageAI's uploaded documents
   or community stories.
3. Do not invent bookings, live availability, exact current prices, opening
   hours, visa rules, weather, safety alerts, or other time-sensitive facts.
4. Treat variable details as approximate and tell the traveller to verify
   current details with official sources when relevant.
5. If the question is not travel-related, politely say that VoyageAI is
   focused on travel assistance.

Question:
{question}
"""

    response = model.invoke(prompt)
    answer_text = _content_to_text(response.content)

    if not answer_text:
        return None

    return {
        "answer": answer_text,
        "sources": ["Gemini general travel knowledge"],
        "source_type": "global_travel",
        "grounded": False,
        "route": "global_fallback",
        "web_grounded": False,
    }


def _looks_like_non_travel_question(question: str) -> bool:
    """Conservative scope guard for clearly non-travel questions.

    We intentionally keep this conservative: many travel questions are phrased
    as ordinary factual questions (for example, "What is the capital of
    Australia?"), so the assistant must not require words such as "travel" or
    "trip" before allowing the worldwide travel route.
    """
    normalized = " ".join((question or "").lower().split())
    if not normalized:
        return False

    clearly_non_travel_patterns = (
        r"\bwrite\s+(?:a\s+)?(?:python|javascript|java|c\+\+|sql)\s+code\b",
        r"\b(?:python|javascript|java|c\+\+|sql)\s+(?:program|code|script)\b",
        r"\bhow\s+do\s+i\s+(?:code|program|debug|compile)\b",
        r"\b(?:solve|calculate|simplify)\s+(?:this\s+)?(?:equation|integral|derivative|math)\b",
        r"\bwhat\s+is\s+(?:recursion|polymorphism|inheritance|encapsulation)\b",
        r"\b(?:debug|fix)\s+(?:this\s+)?(?:code|program|error)\b",
        r"\b(?:homework|assignment)\s+(?:question|problem)\b",
        r"\b(?:lyrics|song\s+lyrics)\b",
        r"\bwrite\s+(?:me\s+)?a\s+(?:poem|song|story)\b",
    )

    return any(re.search(pattern, normalized) for pattern in clearly_non_travel_patterns)


def answer_question(question: str, db=None) -> dict | None:
    """Main Step-4 hybrid travel-assistant router.

    Routing order:
      1. Clearly non-travel questions are kept inside VoyageAI's travel scope.
      2. Approved/uploaded project knowledge and approved community stories.
      3. Google Search-grounded worldwide travel information.
      4. Gemini general travel knowledge as the final worldwide fallback.

    The function always returns the source metadata expected by the UI.
    """
    question = (question or "").strip()
    if not question:
        return None

    # Do not block ordinary destination/factual questions. This guard only
    # catches questions that are unambiguously outside a travel assistant's
    # scope.
    if _looks_like_non_travel_question(question):
        return {
            "answer": (
                "I'm VoyageAI, a travel-focused assistant. I can help with "
                "destinations, itineraries, attractions, transport, budgets, "
                "food, hotels, activities, travel planning, and other "
                "travel-related questions worldwide."
            ),
            "sources": [],
            "source_type": "none",
            "grounded": False,
            "route": "scope_guard",
            "web_grounded": False,
        }

    owned_db = False
    session = db

    # The API route normally supplies a database session. Opening one here
    # also makes this function safe and easy to exercise directly from tests.
    if session is None:
        try:
            from ..database import SessionLocal
            session = SessionLocal()
            owned_db = True
        except Exception:
            session = None

    try:
        # First choice: private VoyageAI knowledge + approved community
        # experiences. answer_with_knowledge() returns None when the retrieved
        # context is missing or insufficient, which is exactly what we want.
        private_result = answer_with_knowledge(question, db=session)
        if private_result:
            return private_result

        # Second/third choice: worldwide travel information. This function
        # tries Google Search grounding first and Gemini general knowledge
        # second, while labelling the source correctly.
        return answer_with_global_travel(question)
    except Exception:
        # Never expose a backend exception to the UI. If the private route
        # fails unexpectedly, make one final worldwide attempt.
        try:
            return answer_with_global_travel(question)
        except Exception:
            return None
    finally:
        if owned_db and session is not None:
            try:
                session.close()
            except Exception:
                pass


# Backwards-compatible name for existing imports.
def answer_with_gemini(question: str) -> dict | None:
    return answer_with_global_travel(question)
