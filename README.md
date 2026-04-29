# Takeoff Studio

Takeoff Studio is the local application for the assessment in [10 — Assessment 1.md](./10%20%E2%80%94%20Assessment%201.md).

It is designed as one coherent app:

- dataset ingestion and normalization
- prediction artifact generation
- sample-project scoring
- persistent reviewer corrections
- a browser UI served by the backend
- a build button in the UI so the data-processing flow can be triggered from the app

## Dataset Layout

The repo expects the assessment dataset under `data/`, not as raw top-level folders.

Current runtime layout:

```text
data/
  meta/candidate_project_manifest.csv
  sample_projects/
  challenge_projects/
  challenge_projects_supplemental/
  output_template/
  submission_instructions/
```

The original assessment notes and raw folder names are not required for the app runtime.

## Recommended Flow

Optional Supabase setup for reviewer persistence:

1. Copy `.env.example` to `.env`
2. Fill in:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_REVIEWS_TABLE`

If `.env` is present, the backend will store reviewer records in Supabase using a server-side key. The browser still talks only to the local app server. If not, it falls back to local SQLite in `artifacts/reviews.db`.

Optional Gemini document extraction:

- set `GEMINI_API_KEY` to enable the PDF OCR/vision fallback
- optional: set `GEMINI_MODEL` to override the default `gemini-2.5-flash`

When enabled, PDFs with weak or missing native text extraction are sent through Gemini document understanding and the file notes record that Gemini extraction was used.

Start the app:

```bash
python3 takeoff_studio.py serve
```

Then open:

- `http://127.0.0.1:8420`
- or
- `localhost:8420`


Inside the UI:

1. Choose a build profile.
2. Click `Run Build`.
3. Review generated projects, scoring, artifacts, and reviewer records.

## Build Profiles

The UI and backend support these profiles:

- `full`: all 3 sample + all 25 challenge projects
- `minimum`: all 3 sample + 5 challenge projects
- `samples`: only the 3 sample projects

CLI build is still available:

```bash
python3 takeoff_studio.py build --root . --output artifacts --profile full
```

Or with `make`:

```bash
make build
make app
```

## What The App Contains

Backend:

- project discovery from the normalized `data/` dataset root
- clean separation between `Project Files` and `Expected Manual Output`
- gold spreadsheet normalization for the 3 sample projects
- challenge/sample prediction generation
- optional Gemini-backed PDF OCR fallback for weak-text PDFs
- deterministic evaluation for visible-gold sample projects
- Supabase-backed reviewer records when configured, otherwise SQLite fallback

Frontend:

- project browser
- build controls
- scoring/evaluation summary
- predicted line-item review view
- artifact links
- in-app review form for corrections and notes
- embedded access to the README, architecture note, review packet, and 30-day plan

## Primary App Files

- [takeoff_studio.py](./takeoff_studio.py)
- [src/takeoff_builder/app.py](./src/takeoff_builder/app.py)
- [src/takeoff_builder/server.py](./src/takeoff_builder/server.py)
- [src/takeoff_builder/service.py](./src/takeoff_builder/service.py)
- [src/takeoff_builder/storage.py](./src/takeoff_builder/storage.py)
- [src/takeoff_builder/pipeline.py](./src/takeoff_builder/pipeline.py)
- [src/takeoff_builder/web/index.html](./src/takeoff_builder/web/index.html)
- [src/takeoff_builder/web/app.js](./src/takeoff_builder/web/app.js)
- [src/takeoff_builder/web/styles.css](./src/takeoff_builder/web/styles.css)

## Build Output

The build writes:

- `artifacts/manifests/*.json`
- `artifacts/gold_normalized/*.json`
- `artifacts/predictions/*.json`
- `artifacts/evaluations/*.json`
- `artifacts/review_packets/*.json`
- `artifacts/dashboard_data.json`
- `artifacts/run_summary.json`
- `artifacts/reviews.db` when running without Supabase

## Verified

Verified locally:

- `python3 takeoff_studio.py build --root . --output artifacts`
- `python3 takeoff_studio.py build --root . --output artifacts_min --profile minimum`
- app modules compile
- service layer loads summaries and project detail
- SQLite review persistence works
- Supabase table and REST-backed review persistence were wired into the storage layer
- Supabase can now be used in backend-only mode with `SUPABASE_SERVICE_ROLE_KEY`

## Current Limits

- No OCR for scanned plans, TIFs, or image-heavy markups
- No image OCR for non-PDF plan formats yet
- Prediction quality is improved for projects with strong text descriptions, but still baseline for many drawing-only projects
- Sample scoring still exposes major extraction gaps
- The best Supabase mode for this app is backend-only access with a service-role key in `.env`
- A production multi-user version should still add real user auth and narrower row-level policies

## Submission Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [CANDIDATE_REVIEW_PACKET.md](./CANDIDATE_REVIEW_PACKET.md)
- [THIRTY_DAY_EXECUTION_PLAN.md](./THIRTY_DAY_EXECUTION_PLAN.md)
