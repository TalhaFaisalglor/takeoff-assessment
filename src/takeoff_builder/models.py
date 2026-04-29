from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class FileRecord:
    path: str
    relative_path: str
    role: str
    extension: str
    size_bytes: int
    source_bucket: str
    duplicate_group: str | None = None
    notes: list[str] = field(default_factory=list)
    extracted_text_preview: str = ""
    page_count: int | None = None
    nested_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Keep manifests portable by exposing repository-relative paths only.
        payload["path"] = self.relative_path
        return payload


@dataclass
class ProjectRecord:
    set_name: str
    takeoff_id: str
    project_name: str
    root_dirs: list[str]
    input_files: list[FileRecord] = field(default_factory=list)
    gold_files: list[FileRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def all_files(self) -> list[FileRecord]:
        return [*self.input_files, *self.gold_files]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "set_name": self.set_name,
            "takeoff_id": self.takeoff_id,
            "project_name": self.project_name,
            "root_dirs": self.root_dirs,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "input_files": [item.to_dict() for item in self.input_files],
            "gold_files": [item.to_dict() for item in self.gold_files],
        }


@dataclass
class TakeoffItem:
    item_number: str | None
    description: str
    quantity: float | int | None
    unit: str | None
    confidence: float
    source_reference: str
    drawing_reference: str | None = None
    section_reference: str | None = None
    division: str | None = None
    category: str | None = None
    raw_quantity: float | int | None = None
    wastage: float | int | None = None
    quantity_with_wastage: float | int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TakeoffOutput:
    project_id: str
    project_name: str
    set_name: str
    trade_scope: str
    input_files_used: list[str]
    ai_run: dict[str, Any]
    line_items: list[TakeoffItem]
    evaluation_when_gold_available: dict[str, Any]
    human_review_stub: dict[str, Any]
    project_manifest_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "set_name": self.set_name,
            "trade_scope": self.trade_scope,
            "input_files_used": self.input_files_used,
            "ai_run": self.ai_run,
            "line_items": [item.to_dict() for item in self.line_items],
            "evaluation_when_gold_available": self.evaluation_when_gold_available,
            "human_review_stub": self.human_review_stub,
            "project_manifest_path": self.project_manifest_path,
        }


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
