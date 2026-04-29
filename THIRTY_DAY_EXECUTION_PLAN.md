# 30-Day Execution Plan

## Days 1-5

- Lock the dataset contract: project, file, gold, prediction, correction, and score schemas.
- Stand up a small persistence layer with SQLite first, Postgres if multi-user review is needed immediately.
- Add document fingerprinting so duplicate plan sets and repeated archives do not create noisy runs.
- Instrument the current pipeline with run IDs, stage timings, and extraction coverage metrics.

## Days 6-10

- Add OCR for scanned PDFs, TIFs, and JPG plan sheets.
- Add document preprocessing: page splitting, deskewing, sheet title detection, and page-type classification.
- Separate files into likely buckets such as drawings, specs, addenda, markups, and admin docs.

## Days 11-15

- Add vision/document extraction workers for schedules, legends, finish tags, mechanical schedules, and electrical fixture schedules.
- Replace coarse trade-template fallback logic with extraction prompts per trade.
- Persist intermediate evidence so every predicted line item can point back to a page, sheet, and snippet.

## Days 16-20

- Build a better evaluator with:
  - exact matching
  - alias dictionaries
  - fuzzy semantic matching
  - quantity-delta reporting
  - precision/recall by trade and by project

- Start tracking benchmark runs against the three sample projects and any newly labeled corrections.

## Days 21-25

- Build the reviewer correction workflow:
  - queue projects for review
  - edit quantities and descriptions
  - approve/reject items
  - capture missing items
  - write corrections back into training/evaluation tables

- Export reviewer-ready CSV or spreadsheet views for estimators who do not want a custom UI yet.

## Days 26-30

- Add learning-loop features:
  - correction-aware prompt retrieval
  - trade-specific extraction strategies
  - confidence calibration
  - regression benchmark dashboard

- Finish with a production recommendation memo covering:
  - which trades are ready first
  - where OCR/vision still fails
  - what human-review staffing is required
  - what accuracy gates must be met before automating downstream estimate creation

## What Success Looks Like After 30 Days

- Every project is ingested into a normalized manifest automatically.
- OCR/vision extraction works on the majority of plan/spec packages.
- Reviewers can correct outputs quickly and those corrections persist cleanly.
- Evaluation scores can be tracked over time by trade and by project.
- The team has a defensible path from prototype ingestion to a real learning takeoff system.
