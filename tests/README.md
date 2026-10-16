# Final Validation Suite

This directory contains the focused tests retained for the final MCA project submission.

| Test | Coverage |
|---|---|
| `test_admin.py` | Administrator dashboard, roles and moderation |
| `test_authentication.py` | Authentication and protected user flows |
| `test_rag_assistant.py` | RAG assistant integration and end-to-end contracts |
| `test_ai_travel_planner.py` | AI travel planner behavior and final UI contract |
| `test_chat_api.py` | Chat API contract |
| `test_community_stories.py` | Community stories end-to-end behavior |
| `test_expense_tracker.py` | Expense tracker end-to-end behavior |
| `test_food_explorer.py` | Food explorer final behavior/UI/E2E coverage |
| `test_hybrid_travel.py` | Hybrid travel behavior |
| `test_knowledge_base.py` | Knowledge-base final validation |
| `test_rest_api.py` | REST API/OpenAPI validation |
| `test_saved_itineraries.py` | Saved itinerary API/architecture validation |
| `test_saved_itineraries_ui.py` | Saved itinerary frontend contract |
| `test_production_config.py` | Runtime/JWT/CORS production configuration |
| `test_provider_fallback.py` | Geoapify → OSM planner fallback |
| `test_travel_explorer_provider.py` | Geoapify → OSM → no-data provider behavior |
| `test_travel_explorer_ui.py` | Travel Explorer frontend/API contract |
| `test_trip_planner.py` | Trip Planner end-to-end validation |
| `test_weather.py` | Weather integration validation |

## Test philosophy

Historical development tests were created phase-by-phase while building the application. They are not all part of the final regression suite. The final submission keeps representative tests for each major feature and the current provider/security architecture.

For the final report, testing can be summarized by module, behavior type (API/UI/E2E), and observed result rather than listing every historical development script.
