# AI Smart Tourism Ecosystem — VoyageAI

An MCA final-year full-stack tourism platform that combines AI-assisted trip planning, saved itineraries, expense tracking, community travel stories, food and weather exploration, a RAG-based travel assistant, authentication, administration, and live travel-data integrations.

## Core modules

- **AI Travel Planner** — destination, duration, interests and budget based itinerary generation.
- **Saved Itineraries** — authenticated users can save and manage generated trips.
- **Expense Tracker** — trip budget and expense management.
- **Community Stories** — travel stories with moderation support and retrieval for the assistant.
- **Food Explorer** — restaurant/food discovery.
- **Weather** — destination weather information.
- **RAG Travel Assistant** — LangChain + FAISS based travel knowledge retrieval with Gemini integration.
- **Authentication** — JWT-based login, password hashing and protected routes.
- **Administration** — administrator dashboard, user/role management and story moderation.
- **Travel Explorer** — maps, restaurants and hotels using a controlled Geoapify → OpenStreetMap fallback flow.
- **REST API** — FastAPI endpoints with automatic Swagger/OpenAPI documentation.

## Travel-data provider policy

The Travel Explorer uses a deliberately simple fallback chain:

```text
Geoapify
   ↓ failure / unavailable / unusable result
OpenStreetMap (OSM / Overpass)
   ↓ failure / empty result
No data
```

There is no emergency cache and no third provider for the Travel Explorer. If OSM cannot provide usable data, the API returns an explicit no-data response rather than fabricated or stale fallback content.

## Project structure

```text
ai-smart-tourism-ecosystem/
├── app/
│   ├── routers/          # FastAPI route modules
│   ├── services/         # provider, RAG and business services
│   ├── static/           # frontend HTML/CSS/JS
│   ├── auth.py
│   ├── config.py
│   ├── crud.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   └── security.py
├── data/
│   ├── community_faiss_index/
│   ├── faiss_index/
│   └── tourism_knowledge/
├── scripts/
│   └── bootstrap_admin.py
├── tests/                # focused final regression/feature tests
├── .env.example
├── .gitignore
├── requirements.txt
└── start_tourism_app.bat
```

## Run locally on Windows

1. Extract the ZIP and open Command Prompt in the `ai-smart-tourism-ecosystem` folder.
2. Create and activate the project's `venv` environment:

```bat
python -m venv venv
venv\\Scripts\\activate
```

3. Create your local environment file from the safe template:

```bat
copy .env.example .env
```

4. Install the dependencies:

```bat
python -m pip install -r requirements.txt
```

5. Start the application:

```bat
python -m uvicorn app.main:app --reload
```

Alternatively, double-click `start_tourism_app.bat` after creating the `venv` environment.

Open:

- `http://127.0.0.1:8000/static/index.html`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/admin`

The ZIP intentionally excludes `.env` so API keys and local secrets are not distributed. Add your own credentials to `.env` only when needed.

## Environment configuration

Copy `.env.example` to `.env` and configure the local database and required API credentials.

At minimum, configure the application environment and JWT settings:

```text
APP_ENV=development
JWT_SECRET_KEY=<random-secret-at-least-32-characters>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
CORS_ORIGINS=*
```

For production, use a strong secret and replace the wildcard CORS value with the exact frontend origin(s).

## Database

The application uses SQLAlchemy and can run with SQLite for local development or MySQL when `DATABASE_URL` is configured accordingly in `.env`.

## Administrator bootstrap

New registrations are created as travelers. To create the first administrator:

```bat
python scripts\bootstrap_admin.py --email your-admin-email@example.com
```

The bootstrap script only creates an administrator when the database has no existing administrator.

## Testing

The `tests/` directory contains the focused final validation suite rather than the historical phase-by-phase development validators.

Run the standard pytest-compatible tests with:

```bat
pytest -q
```

Some legacy architecture validators from the development process were intentionally removed from the final submission because they executed checks during module import and were not suitable as a clean regression suite. The final test set is documented in `tests/README.md`.

## Security

Do not commit `.env`, API keys, database credentials, JWT secrets, or local database files. Keep `.env.example` as the shareable configuration template.

## Planner quality and budget transparency

The itinerary preview now includes a `quality_report` object alongside the itinerary. It reports how many requested days were returned, which days have no activities, and the sum of estimated activity costs. The budget scope is explicitly `activity_estimates_only`; the planner does not claim to verify the complete trip cost because live transport, accommodation, meal and admission prices are not comprehensively available. Warnings are included when a requested day is missing, a day has no activities, or the estimated activity costs alone exceed the submitted budget.

Generic fallback activities remain disabled by default (`PLANNER_ALLOW_GENERIC_FALLBACK=false`) so the planner does not present vague placeholder activities as verified venues.


## Practical day-wise itinerary scheduling (V12)

The planner now returns a `schedule` array for every day, in addition to the
existing `activities` and `guide_sections` fields. The frontend renders the
chronological schedule with breakfast, sightseeing, lunch, one main rest break,
afternoon visits, and dinner. Restaurant/cafe recommendations are placed as
later food experiences where possible rather than being treated as the first
morning sightseeing stop.

The engine selects up to five named places per day when the provider returns
enough suitable places. It ranks places using selected-interest compatibility,
category/place validation, distance, geographic grouping, and duplicate
avoidance. The schedule is deterministic and constraint-based; it is not
presented as a trained machine-learning prediction model.

### Why this version does not add ML yet

The project currently has no labelled dataset of traveller preferences,
ratings, actual visit durations, trip outcomes, or actual spending sufficient
to train and evaluate a useful model. A machine-learning model added without
such data would be unvalidated and could make recommendations less reliable.
The current approach is explainable and testable. If usage feedback is later
collected with consent, a ranking model could be evaluated against this
baseline.

Schedule times, meal costs, activity costs and visit durations are estimates.
The app does not claim to verify live opening hours, transport availability,
ticket prices, or activity bookings. Confirm those details before travel.

## Mixed-interest itinerary planning (V13)

The planner treats selected interests as trip-wide preferences rather than assigning a single interest to each day. It attempts to include at least one suitable place from every requested interest on each day when enough distinct place data is available. Remaining activity slots are distributed across interests, with geographic clustering and duplicate avoidance. If the provider cannot find enough places for a requested interest, the planner does not fabricate real venues; the resulting itinerary may contain fewer categories and should be reviewed.

The day schedule includes breakfast, sightseeing, lunch, one main rest break, afternoon visits and dinner. Times and activity costs are estimates and do not guarantee current opening hours, admission prices or availability.
