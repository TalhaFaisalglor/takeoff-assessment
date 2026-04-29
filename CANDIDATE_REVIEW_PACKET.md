# Candidate Review Packet

## 1. Plain-English Summary

I built a runnable local application called Takeoff Studio for the assessment dataset in this workspace.

It processes all 28 projects, separates AI-visible files from sample-only gold outputs, parses the sample estimate spreadsheets into structured line items, generates prediction outputs for all projects, scores the 3 sample projects deterministically, stores reviewer corrections through the app storage layer, and serves a browser UI where a reviewer can inspect outputs and save review decisions.

This is not the final production takeoff AI. It is the first serious application slice of one: ingestion, normalization, prediction packaging, evaluation, review persistence, and a unified reviewer interface.

## 2. How To Run It

Recommended app flow:

```bash
python3 takeoff_studio.py serve
```

Then open:

- `http://127.0.0.1:8420` or `http://localhost:8420`

Inside the app:

1. Choose a build profile.
2. Click `Run Build`.
3. Review projects, outputs, scoring, and saved reviewer records.

Optional CLI build:

```bash
python3 takeoff_studio.py build --root . --output artifacts --profile full
```

Environment assumptions:

- Python `3.13+`
- no third-party dependency install required for the verified build path
- dataset present in this workspace exactly as provided

Important note:

- The build command was verified locally.
- The app is designed to be run on a normal local machine environment.
- Reviewer persistence uses Supabase when `.env` is configured, otherwise it falls back to local SQLite.

## 3. Projects Processed

All 28 projects were processed. The repo uses a normalized `data/` layout for runtime, and for each project the system used all files inside `Project Files` and wrote a manifest plus prediction output. Sample projects were also scored because they include visible gold outputs.

| Set | Takeoff ID | Project Name | Files Used | Output Created? | Scored? |
| --- | --- | --- | --- | --- | --- |
| Sample | TAKEOFF-28 | Maryland Vision Institute | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-28.json` | yes | yes |
| Sample | TAKEOFF-50 | Portland VA Surgical Center Rehabilitation | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-50.json` | yes | yes |
| Sample | TAKEOFF-56 | JACK & JONES STATEN ISLAND, NY | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-56.json` | yes | yes |
| Challenge | TAKEOFF-16 | Sephora (Surprise, AZ) | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-16.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-22 | AUTOZONE #10016 | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-22.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-30 | FRESENIUS NORTH DALLAS | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-30.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-31 | WALMART 1783 | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-31.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-32 | APU Military and Veterans Azusa | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-32.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-33 | Foot Locker - Vintage Fair Mall Modesto | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-33.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-35 | RACETRAC Palm Coast | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-35.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-36 | Gucci Perm - Cherry Creek Shopping Center | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-36.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-37 | TAKE 5 OIL CHANGE, SHEFFIELD OH | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-37.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-39 | Nuuvi Modern Med Spa - Wayne, PA | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-39.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-40 | TPS Rm 203 ETVS Renovation | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-40.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-42 | Lake Placid Police Station | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-42.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-45 | Ground Up Maverik Fuel Center Calexico | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-45.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-47 | Woof Gang | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-47.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-48 | MATTRESS FIRM - MERCED MALL | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-48.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-49 | Maintenance Building, Gator Blvd & Main Street | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-49.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-52 | LOVESAC CORNER SHOPPES AT STADIUM | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-52.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-54 | TAKE 5 OIL CHANGE MASONRY | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-54.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-55 | Coach House Renovation | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-55.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-57 | TAKE 5 OIL CHANGE - COLLEGE STATION, TX | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-57.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-58 | HMSL Employee Fitness | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-58.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-60 | NW WTP OPERATORS BUILDING | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-60.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-61 | KEDPLASMA UNIVERSAL CITY, TX | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-61.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-63 | LEHI HIPPO VET CLINIC | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-63.json` | yes | no hidden gold available |
| Challenge | TAKEOFF-64 | Paradies- Beltline Market _ Village Retail- ATL Airport | All files under `Project Files`; see `artifacts/manifests/TAKEOFF-64.json` | yes | no hidden gold available |

## 4. System Pipeline

1. File/folder ingestion
   Walk every dataset folder and merge duplicate project sources by takeoff ID.
2. AI-visible input separation
   Treat `Project Files` as model-visible and `Expected Manual Output` as evaluation-only.
3. Takeoff extraction/generation
   Build a text corpus from PDF, DOCX, TXT, and ZIP metadata, recover explicit quantity statements where possible, and emit heuristic line items by normalized trade.
4. Structured output creation
   Write JSON manifests, parsed gold outputs, predictions, evaluations, review packets, and app payloads.
5. Scoring/evaluation when gold is visible
   Compare sample predictions to parsed gold outputs with deterministic exact-description matching and quantity tolerance.
6. Human review/correction loop
   Store review status, notes, and corrected items in the app storage layer and expose them in the browser UI.

## 5. Output Summary

Artifact counts:

- `28` project manifests
- `28` prediction files
- `28` human review packets
- `3` normalized gold sample files
- `3` evaluation files
- `1` review storage backend, using Supabase when configured and SQLite otherwise

Representative challenge output:

- [artifacts/predictions/TAKEOFF-36.json](./artifacts/predictions/TAKEOFF-36.json)
- [artifacts/predictions/TAKEOFF-39.json](./artifacts/predictions/TAKEOFF-39.json)

Representative sample output:

- [artifacts/predictions/TAKEOFF-28.json](./artifacts/predictions/TAKEOFF-28.json)
- [artifacts/gold_normalized/TAKEOFF-28.json](./artifacts/gold_normalized/TAKEOFF-28.json)

Application entry points:

- [takeoff_studio.py](./takeoff_studio.py)
- [src/takeoff_builder/server.py](./src/takeoff_builder/server.py)
- [src/takeoff_builder/web/index.html](./src/takeoff_builder/web/index.html)

## 6. Evaluation / Scoring Results

Sample-project baseline scoring:

| Takeoff ID | Matched Items | Missing Items | Extra Items | Precision | Recall |
| --- | --- | --- | --- | --- | --- |
| TAKEOFF-28 | 0 | 121 | 5 | 0.0 | 0.0 |
| TAKEOFF-50 | 0 | 7 | 3 | 0.0 | 0.0 |
| TAKEOFF-56 | 0 | 11 | 2 | 0.0 | 0.0 |

Interpretation:

- The ingestion and gold-normalization layers are working.
- The evaluation loop is working.
- The reviewer workflow and app persistence are working structurally.
- Prediction quality is still strongest only where explicit textual scope/quantity hints exist.

## 7. Automation vs Manual Work

Automated:

- dataset discovery
- file classification
- sample gold spreadsheet parsing
- challenge/sample artifact generation
- scoring
- review packet generation
- app API serving
- review persistence through Supabase when configured, otherwise SQLite fallback

Manual:

- no manual adjustment was made to predicted line items
- no hidden gold outputs were requested or inferred
- documentation was written manually after validating generated artifacts

Mocked or heuristic:

- many predicted line items and quantities remain heuristic candidates rather than fully measured takeoffs

## 8. AI / Tools Used

- Python `3.13`
- stdlib `zipfile`, `xml.etree.ElementTree`, `json`, `csv`, `re`, `sqlite3`, `http.server`
- custom lightweight PDF text extractor
- optional Gemini document understanding for PDF OCR fallback
- AI coding assistance during implementation

Gemini OCR/document understanding is optional and only runs when `GEMINI_API_KEY` is configured. When that path is used, the project/file metadata records it.

## 9. Limitations and Risks

- Image-heavy plans and TIF sheets are not OCR’d.
- The PDF text extractor is lightweight and inconsistent on some files. Needs further work.
- Gemini support currently improves PDF text recovery, but it is not yet a full structured takeoff extractor by itself.
- Quantities are still proxy values when no direct measurable signal is recovered.
- Evaluation is strict exact-description matching; there is no semantic item alignment yet.
- Browser serving is intended for a normal local machine workflow.

## 10. 30-Day Plan

See [THIRTY_DAY_EXECUTION_PLAN.md](./THIRTY_DAY_EXECUTION_PLAN.md).

