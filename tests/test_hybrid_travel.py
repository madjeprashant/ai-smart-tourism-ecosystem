"""
Phase 1 - Step 4
Hybrid Travel Assistant tests.

These tests validate the ROUTING architecture without burning Gemini API quota.
Live Gemini/web calls are deliberately mocked.

Architecture under test:
1. Clearly non-travel questions -> scope guard, no AI call.
2. Private/approved knowledge -> returned first.
3. If private knowledge is unavailable -> worldwide travel fallback.
4. Source metadata must remain truthful.
5. Private retrieval must not invent knowledge for an unrelated destination.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services import knowledge_base as kb


def _assert_source_shape(result: dict, expected_type: str, expected_route: str):
    assert isinstance(result, dict), f"Expected dict result, got {type(result).__name__}"
    assert isinstance(result.get("answer"), str) and result["answer"].strip()
    assert result.get("source_type") == expected_type, result
    assert result.get("route") == expected_route, result
    assert "grounded" in result
    assert "web_grounded" in result
    assert isinstance(result.get("sources", []), list)


def _private_answer(text: str, source_type: str = "community_story") -> dict:
    return {
        "answer": text,
        "sources": ["Community story — Chasing Sunsets and Coastal Cafes"],
        "source_type": source_type,
        "grounded": True,
        "route": "private_knowledge",
        "web_grounded": False,
        "retrieved_count": 1,
    }


def _global_answer(text: str = "Worldwide travel answer.") -> dict:
    return {
        "answer": text,
        "sources": ["Gemini general travel knowledge"],
        "source_type": "global_travel",
        "grounded": False,
        "route": "global_fallback",
        "web_grounded": False,
    }


def test_north_goa_private_knowledge():
    """Private/community knowledge must win over worldwide fallback."""
    private = _private_answer(
        "The approved traveller story recommends exploring North Goa early "
        "in the morning and keeping offline maps available."
    )

    with patch.object(kb, "answer_with_knowledge", return_value=private) as private_mock, \
         patch.object(
             kb,
             "answer_with_global_travel",
             side_effect=AssertionError(
                 "Global fallback must not run when private knowledge answers."
             ),
         ):
        result = kb.answer_question(
            "What does the traveller recommend for exploring North Goa?"
        )

    private_mock.assert_called_once()
    _assert_source_shape(result, "community_story", "private_knowledge")
    assert "North Goa" in result["answer"]


def test_australia_global_travel():
    """A destination absent from private knowledge must use worldwide travel."""
    with patch.object(kb, "answer_with_knowledge", return_value=None), \
         patch.object(
             kb,
             "answer_with_global_travel",
             return_value=_global_answer("The capital of Australia is Canberra."),
         ) as global_mock:
        result = kb.answer_question("What is the capital of Australia?")

    global_mock.assert_called_once_with("What is the capital of Australia?")
    _assert_source_shape(result, "global_travel", "global_fallback")
    assert "Canberra" in result["answer"]


def test_tokyo_global_travel():
    """Tokyo should use the worldwide route when private data is absent."""
    with patch.object(kb, "answer_with_knowledge", return_value=None), \
         patch.object(
             kb,
             "answer_with_global_travel",
             return_value=_global_answer("Tokyo is a worldwide travel destination."),
         ):
        result = kb.answer_question("What are the best places to visit in Tokyo?")

    _assert_source_shape(result, "global_travel", "global_fallback")
    assert "Tokyo" in result["answer"]


def test_paris_global_travel():
    """Paris should use the worldwide route when private data is absent."""
    with patch.object(kb, "answer_with_knowledge", return_value=None), \
         patch.object(
             kb,
             "answer_with_global_travel",
             return_value=_global_answer("Here is a three-day Paris itinerary."),
         ):
        result = kb.answer_question(
            "What are the best things to do in Paris for 3 days?"
        )

    _assert_source_shape(result, "global_travel", "global_fallback")
    assert "Paris" in result["answer"]


def test_non_travel_question():
    """
    Clearly non-travel questions must be stopped by the scope guard.
    This must not call Gemini or the worldwide fallback.
    """
    with patch.object(
        kb,
        "answer_with_knowledge",
        side_effect=AssertionError(
            "Private retrieval must not run for a clearly non-travel question."
        ),
    ), patch.object(
        kb,
        "answer_with_global_travel",
        side_effect=AssertionError(
            "Global travel fallback must not run for a clearly non-travel question."
        ),
    ):
        result = kb.answer_question("Write Python code to sort a list.")

    _assert_source_shape(result, "none", "scope_guard")
    assert result["grounded"] is False
    assert result["web_grounded"] is False
    assert "travel" in result["answer"].lower()


def test_source_classification():
    """
    Source metadata is part of the product contract.

    The router must preserve the source returned by the selected route rather
    than relabelling Gemini output as private VoyageAI knowledge.
    """
    private = _private_answer("Approved community experience for North Goa.")

    with patch.object(kb, "answer_with_knowledge", return_value=private):
        result = kb.answer_question(
            "What did the traveller recommend for North Goa?"
        )

    _assert_source_shape(result, "community_story", "private_knowledge")
    assert result["grounded"] is True
    assert result["web_grounded"] is False

    with patch.object(kb, "answer_with_knowledge", return_value=None), \
         patch.object(
             kb,
             "answer_with_global_travel",
             return_value=_global_answer("The capital of Australia is Canberra."),
         ):
        result = kb.answer_question("What is the capital of Australia?")

    _assert_source_shape(result, "global_travel", "global_fallback")
    assert result["grounded"] is False
    assert result["web_grounded"] is False
    assert result["sources"] == ["Gemini general travel knowledge"]


def test_private_retrieval_is_destination_specific():
    """
    A private retrieval candidate mentioning a different destination must not
    be treated as an answer for Tokyo.

    This is a lightweight unit test of the relevance gate and makes no Gemini
    request.
    """

    class DummyDocument:
        def __init__(self, page_content: str, metadata: dict):
            self.page_content = page_content
            self.metadata = metadata

    north_goa_doc = DummyDocument(
        page_content=(
            "Destination: North Goa\n"
            "Traveller: Prashant\n"
            "Experience: Rent a scooter early in the morning."
        ),
        metadata={
            "source": "Community story — Chasing Sunsets and Coastal Cafes",
            "source_type": "community_story",
            "destination": "North Goa",
            "author": "Prashant",
        },
    )

    selected = kb._select_relevant_documents(
        "What are the best places to visit in Tokyo?",
        [(north_goa_doc, 0.05, "community_story")],
    )

    assert selected == [], (
        "Private retrieval incorrectly selected North Goa knowledge for Tokyo."
    )


def run_all():
    tests = [
        ("North Goa private/community knowledge", test_north_goa_private_knowledge),
        ("Worldwide Australia", test_australia_global_travel),
        ("Worldwide Tokyo", test_tokyo_global_travel),
        ("Worldwide Paris", test_paris_global_travel),
        ("Non-travel scope", test_non_travel_question),
        ("Source classification", test_source_classification),
        ("Private retrieval isolation", test_private_retrieval_is_destination_specific),
    ]

    print("=" * 65)
    print("PHASE 1 - STEP 4")
    print("HYBRID TRAVEL ASSISTANT TESTS")
    print("=" * 65)

    passed = 0

    for label, test in tests:
        print(f"\n--- {label} ---")
        try:
            test()
            print("PASS")
            passed += 1
        except Exception as error:
            print("FAIL")
            print(f"ERROR: {error}")

    print("\n" + "=" * 65)
    print(f"RESULT: {passed}/{len(tests)} tests passed")
    print("=" * 65)

    if passed != len(tests):
        raise SystemExit(1)

    print("STEP 4 ROUTING TESTS PASSED")
    print("No Gemini quota was consumed by this test suite.")


if __name__ == "__main__":
    run_all()
