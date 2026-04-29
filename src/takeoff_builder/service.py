from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pipeline import BUILD_PROFILES
from .storage import get_review_record, get_storage_backend, init_review_db


class TakeoffAppService:
    def __init__(self, root: Path, output: Path):
        self.root = root.resolve()
        self.output = output.resolve()
        self.review_db_path = self.output / "reviews.db"
        init_review_db(self.review_db_path)
        self.review_backend = get_storage_backend(self.review_db_path)

    def load_dashboard_payload(self) -> dict[str, Any]:
        path = self.output / "dashboard_data.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text())

    def list_projects(self) -> list[dict[str, Any]]:
        try:
            payload = self.load_dashboard_payload()
        except FileNotFoundError:
            return []
        return payload["projects"]

    def get_summary(self) -> dict[str, Any]:
        try:
            payload = self.load_dashboard_payload()
            summary = dict(payload["summary"])
            summary["build_state"] = "ready"
        except FileNotFoundError:
            summary = {
                "profile": None,
                "profile_label": None,
                "project_count": 0,
                "sample_project_count": 0,
                "challenge_project_count": 0,
                "processed_projects": [],
                "build_state": "not_built",
            }
        summary["available_profiles"] = BUILD_PROFILES
        summary["review_db_path"] = str(self.review_db_path)
        summary["review_backend"] = self.review_backend
        summary["root_path"] = str(self.root)
        summary["output_path"] = str(self.output)
        return summary

    def get_project(self, takeoff_id: str) -> dict[str, Any]:
        payload = self.load_dashboard_payload()
        project = next((item for item in payload["projects"] if item["takeoff_id"] == takeoff_id), None)
        if not project:
            raise KeyError(takeoff_id)
        project = dict(project)
        project["review_record"] = get_review_record(self.review_db_path, takeoff_id)
        project["review_backend"] = self.review_backend
        project["documents"] = {
            "readme": self._read_doc("README.md"),
            "architecture": self._read_doc("ARCHITECTURE.md"),
            "review_packet": self._read_doc("CANDIDATE_REVIEW_PACKET.md"),
            "plan_30_day": self._read_doc("THIRTY_DAY_EXECUTION_PLAN.md"),
        }
        return project

    def _read_doc(self, name: str) -> str:
        path = self.root / name
        return path.read_text(encoding="utf-8")
