# Architecture Note

## Goal

Build the first local application slice of an AI construction takeoff system that can:

- ingest messy project folders
- separate AI-visible inputs from gold/reference outputs
- normalize human takeoff outputs into a structured schema
- generate challenge-project prediction outputs
- score sample-project predictions deterministically
- persist human review/correction state
- present the whole workflow through one browser application

## System Shape

The app is split into four layers:

1. Data pipeline
   Discovers projects, extracts text where possible, normalizes sample gold outputs, generates predictions, scores sample projects, and writes artifacts.

2. Backend application server
   Serves the frontend, exposes project/review/build APIs, and exposes artifacts through stable routes.

3. Review persistence
   Stores reviewer status, notes, and corrected items in Supabase when configured, otherwise SQLite.

4. Frontend application
   Gives reviewers one workspace for project browsing, output inspection, evaluation review, artifact access, and review submission.

## Dataset Separation

The application treats the dataset as two logical planes:

- AI-visible inputs: every file inside a project's `Project Files` folder
- evaluation-only gold: every file inside a sample project's `Expected Manual Output` folder

This rule is enforced in [src/takeoff_builder/discovery.py](./src/takeoff_builder/discovery.py). Gold files are parsed only in the normalization/evaluation path and are never used in the challenge prediction path.

## Folder Handling

The ingestion step checks the normalized dataset root:

- `data/sample_projects`
- `data/challenge_projects`
- `data/challenge_projects_supplemental`

Important dataset conditions handled explicitly:

- duplicate challenge sources for `TAKEOFF-32`, `TAKEOFF-45`, and `TAKEOFF-60`
- nested legacy folders and duplicated assets inside `TAKEOFF-56`
- zipped duplicate drawing package in `TAKEOFF-45`
- mismatches between manifest `input_file_count` and actual discovered file totals

## Data Model

Core pipeline models:

- `ProjectRecord`: normalized project boundary, metadata, warnings, input files, gold files
- `FileRecord`: path, extension, role, source bucket, size, preview text, page count, archive members
- `TakeoffItem`: normalized line item with description, quantity, unit, confidence, and source reference
- `TakeoffOutput`: per-project output with run metadata, line items, evaluation block, and review stub

Application models:

- `dashboard_data.json`: consolidated project summary payload for the app
- `reviews.db`: local fallback review store when Supabase is not configured
- API resources: summary, project details, artifact links, and review records

## Pipeline

1. Discovery
   Read the candidate manifest CSV from `data/meta/candidate_project_manifest.csv`, walk every dataset folder, merge duplicate project sources by takeoff ID, and classify files as `input` or `gold`.

2. Extraction
   Extract lightweight text where possible:
   - `txt`: direct read
   - `docx`: ZIP/XML parse
   - `xlsx`: ZIP/XML parse
   - `pdf`: custom stream decompression and text-object extraction, with optional Gemini OCR fallback when native text is weak
   - `zip`: nested member listing

3. Gold normalization
   Parse the three sample estimate spreadsheets into structured line items with division/category context, quantity, unit, wastage, and references.

4. Prediction
   Build a per-project corpus from AI-visible files only, infer trade scope, extract explicit quantity statements where available, and fall back to rule-based trade templates where extraction is weak.

5. Evaluation
   Run deterministic sample-only scoring using normalized exact-description matching plus quantity tolerance.

6. Review initialization
   Emit review-packet JSON and initialize review persistence.

7. Application payload
   Write `dashboard_data.json` so the app can present projects and outputs coherently.

## Backend API

Implemented in [src/takeoff_builder/server.py](./src/takeoff_builder/server.py).

Primary routes:

- `GET /api/health`
- `GET /api/summary`
- `GET /api/projects`
- `GET /api/projects/{takeoff_id}`
- `GET /api/reviews/{takeoff_id}`
- `POST /api/reviews/{takeoff_id}`
- `POST /api/rebuild`

The server also serves:

- the frontend application
- artifact files under `/artifacts/...`

## Frontend Application

Implemented in:

- [src/takeoff_builder/web/index.html](./src/takeoff_builder/web/index.html)
- [src/takeoff_builder/web/app.js](./src/takeoff_builder/web/app.js)
- [src/takeoff_builder/web/styles.css](./src/takeoff_builder/web/styles.css)

The UI includes:

- project browser and filtering
- overview metrics
- predicted line-item table
- sample evaluation summary
- input-file preview
- artifact links
- editable reviewer record with save action
- embedded access to README, architecture note, review packet, and 30-day plan

## Deterministic Code vs AI Reasoning

Deterministic:

- dataset discovery
- duplicate-folder merging
- file classification
- `.xlsx` gold parsing
- scoring logic
- review persistence
- API serialization
- artifact writing

Model-like reasoning, but implemented locally as rules in this prototype:

- trade normalization
- explicit quantity extraction from project-description narrative
- evidence-to-line-item heuristics
- proxy quantity generation
- fallback line-item templates when extraction is weak

In a stronger version of the system, these heuristic steps would be replaced or augmented by OCR + vision + LLM extraction workers, but the surrounding dataset controls, evaluation layer, and review persistence would remain deterministic.

## Current Weaknesses

- No OCR for image-heavy plans, TIF sheets, or scanned markups
- No schedule/table extraction engine
- No sheet-scale measurement engine
- No semantic matcher for partial item equivalence
- Prediction quality is still strongest only where usable text descriptions exist
- Sample-project evaluation scores remain poor because the extraction layer cannot yet recover drawing-level quantities reliably

## What I Would Improve Next

- add OCR and document-image preprocessing
- use a vision/document model to extract schedules, legends, and tagged quantities
- expand trade-specific extraction strategies
- improve line-item matching for evaluation
- add run history and analytics beyond the current local-first prototype
- expose correction deltas and audit history in the UI
