from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .extractors import (
    estimate_pdf_page_count,
    extract_docx_text,
    extract_pdf_text,
    extract_pdf_text_with_gemini,
    gemini_document_extraction_enabled,
    list_zip_members,
    read_text_file,
)
from .models import FileRecord, ProjectRecord, relpath


DATA_ROOT = Path("data")
MANIFEST_PATH = DATA_ROOT / "meta" / "candidate_project_manifest.csv"


def load_candidate_manifest(root: Path) -> dict[str, dict[str, str]]:
    path = root / MANIFEST_PATH
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows[row["takeoff_id"]] = row
    return rows


def _iter_project_dirs(root: Path) -> Iterable[tuple[str, Path]]:
    yield "sample", root / DATA_ROOT / "sample_projects"
    yield "challenge", root / DATA_ROOT / "challenge_projects"
    yield "challenge_supplemental", root / DATA_ROOT / "challenge_projects_supplemental"


def _project_key(name: str) -> tuple[str, str]:
    takeoff_id, _, project_name = name.partition(" - ")
    return takeoff_id.strip(), project_name.strip()


def discover_projects(
    root: Path,
    include_sets: set[str] | None = None,
    include_takeoff_ids: set[str] | None = None,
) -> list[ProjectRecord]:
    manifest_meta = load_candidate_manifest(root)
    grouped: dict[str, dict[str, object]] = {}
    for bucket, base in _iter_project_dirs(root):
        if not base.exists():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            takeoff_id, project_name = _project_key(entry.name)
            row = manifest_meta.get(takeoff_id, {})
            project_set = row.get("set", "challenge")
            if include_sets is not None and project_set not in include_sets:
                continue
            if include_takeoff_ids is not None and takeoff_id not in include_takeoff_ids:
                continue
            key = takeoff_id
            existing = grouped.setdefault(
                key,
                {
                    "set_name": project_set,
                    "takeoff_id": takeoff_id,
                    "project_name": row.get("project_name", project_name or entry.name),
                    "root_dirs": [],
                    "metadata": dict(row),
                    "sources": [],
                },
            )
            existing["root_dirs"].append(relpath(entry, root))
            existing["sources"].append((bucket, entry))

    projects: list[ProjectRecord] = []
    for project_data in grouped.values():
        project = ProjectRecord(
            set_name=str(project_data["set_name"]),
            takeoff_id=str(project_data["takeoff_id"]),
            project_name=str(project_data["project_name"]),
            root_dirs=list(project_data["root_dirs"]),
            metadata=dict(project_data["metadata"]),
        )
        duplicate_index: dict[str, list[str]] = defaultdict(list)
        for bucket, project_dir in project_data["sources"]:
            input_dir = project_dir / "Project Files"
            gold_dir = project_dir / "Expected Manual Output"
            if input_dir.exists():
                _collect_files(root, project, input_dir, "input", bucket, duplicate_index)
            if gold_dir.exists():
                _collect_files(root, project, gold_dir, "gold", bucket, duplicate_index)
        for item in project.all_files():
            stem_key = Path(item.path).name.lower()
            duplicates = duplicate_index.get(stem_key, [])
            if len(duplicates) > 1:
                item.duplicate_group = stem_key
        _apply_dataset_warnings(project)
        projects.append(project)

    return sorted(projects, key=lambda item: (item.set_name, item.takeoff_id))


def _collect_files(
    root: Path,
    project: ProjectRecord,
    base_dir: Path,
    role: str,
    bucket: str,
    duplicate_index: dict[str, list[str]],
) -> None:
    for path in sorted(base_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        extension = path.suffix.lower().lstrip(".")
        record = FileRecord(
            path=str(path.resolve()),
            relative_path=relpath(path, root),
            role=role,
            extension=extension or "[no_ext]",
            size_bytes=path.stat().st_size,
            source_bucket=bucket,
        )
        duplicate_index[path.name.lower()].append(record.relative_path)
        if extension == "txt":
            record.extracted_text_preview = read_text_file(path)[:4000]
        elif extension == "docx":
            record.extracted_text_preview = extract_docx_text(path)[:4000]
        elif extension == "pdf":
            record.page_count = estimate_pdf_page_count(path)
            lightweight_text = extract_pdf_text(path)
            record.extracted_text_preview = lightweight_text[:4000]
            if not record.extracted_text_preview:
                record.notes.append("No text extracted with lightweight parser")
            elif len(lightweight_text) < 240:
                record.notes.append("Lightweight parser recovered only limited text")
            if gemini_document_extraction_enabled() and _should_try_gemini_pdf(path, lightweight_text):
                gemini_text = extract_pdf_text_with_gemini(path)
                if gemini_text:
                    if len(gemini_text) > len(lightweight_text):
                        record.extracted_text_preview = gemini_text[:4000]
                    record.notes.append("Gemini document extraction used")
                elif not lightweight_text:
                    record.notes.append("Gemini document extraction returned no text")
        elif extension == "zip":
            record.nested_files = list_zip_members(path)
            if record.nested_files:
                record.notes.append("Archive listed but not recursively extracted")
        target = project.input_files if role == "input" else project.gold_files
        target.append(record)


def _apply_dataset_warnings(project: ProjectRecord) -> None:
    declared_count = project.metadata.get("input_file_count")
    if declared_count:
        actual_count = len(project.input_files)
        try:
            declared = int(declared_count)
        except ValueError:
            declared = None
        if declared is not None and declared != actual_count:
            project.warnings.append(
                f"Manifest input_file_count={declared} differs from discovered input files={actual_count}."
            )
    if len(project.root_dirs) > 1:
        project.warnings.append("Project was discovered in multiple dataset folders and merged into one manifest.")


def _should_try_gemini_pdf(path: Path, lightweight_text: str) -> bool:
    if path.stat().st_size > 50 * 1024 * 1024:
        return False
    if not lightweight_text:
        return True
    return len(lightweight_text.strip()) < 240
