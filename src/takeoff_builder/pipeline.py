from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .discovery import discover_projects
from .gold_parser import parse_gold_workbook
from .models import ProjectRecord, TakeoffItem, TakeoffOutput
from .scoring import score_predictions


TRADE_PATTERNS: dict[str, list[tuple[str, str, str]]] = {
    "painting": [
        (r"\bpaint\b|\bprimer\b|\bcoats?\b", "Wall paint system", "SF"),
        (r"\bceiling\b.*\bpaint\b|\bflat\b", "Ceiling paint system", "SF"),
        (r"\bcolumn\b.*\bpaint\b", "Column paint finish", "SF"),
    ],
    "hvac": [
        (r"\bduct\b", "Sheet metal ductwork", "FT"),
        (r"\bflexible duct\b|\bflex duct\b", "Flexible duct runs", "FT"),
        (r"\brtu-\d+\b|\brtu\b", "Packaged rooftop units", "EA"),
        (r"\bvav-\d+\b|\bvav\b", "VAV terminal units", "EA"),
        (r"\bdiffuser\b|\bregister\b|\bgrille\b", "Diffusers, registers, and grilles", "EA"),
    ],
    "electrical": [
        (r"\blight\b|\btroffer\b|\bdownlight\b|\bexit sign\b", "Lighting fixtures", "EA"),
        (r"\bsensor\b", "Controls and sensors", "EA"),
        (r"\bswitch\b", "Switch devices", "EA"),
        (r"\breceptacle\b|\boutlet\b", "Power and low-voltage devices", "EA"),
        (r"\bpanel\b|\btransformer\b|\bbreaker\b", "Distribution equipment", "EA"),
        (r"\bwiring\b|\bconduit\b", "Branch wiring and conduit", "SF"),
    ],
    "flooring": [
        (r"\btile\b|\bporcelain\b|\bquarry\b", "Tile flooring", "SF"),
        (r"\btransition\b", "Floor transitions", "FT"),
        (r"\bwall tile\b", "Wall tile", "SF"),
    ],
    "carpentry/gabinets": [
        (r"\bwood\b|\bmillwork\b|\bcladding\b", "Millwork and wood trim", "FT"),
        (r"\bcabinet\b|\bcounter\b|\bbackwrap\b", "Cabinets and counters", "FT"),
        (r"\bdoor\b|\bhardware\b", "Doors and hardware", "EA"),
    ],
    "masonry": [
        (r"\bcmu\b|\bbrick\b|\bmasonry\b", "Masonry wall system", "SF"),
        (r"\blintel\b|\brebar\b", "Masonry reinforcing and lintels", "EA"),
    ],
    "plumbing": [
        (r"\blavatory\b|\bsink\b|\bwater closet\b|\btoilet\b", "Plumbing fixtures", "EA"),
        (r"\bdrain\b|\bpipe\b|\bplumbing\b", "Plumbing piping and drains", "FT"),
    ],
    "roofing": [
        (r"\broof\b|\bshingle\b|\bflashing\b", "Roofing system", "SF"),
    ],
    "landscaping": [
        (r"\btree\b|\bshrub\b|\bsod\b", "Landscape planting", "EA"),
        (r"\birrigation\b", "Irrigation scope", "LS"),
    ],
    "drywall/framing": [
        (r"\bdrywall\b|\bgypsum\b|\bgwb\b|\btoughrock\b", "Gypsum board wall system", "SF"),
        (r"\bframing\b|\bstud\b", "Metal stud framing", "SF"),
        (r"\bsoffit\b", "Soffit framing and drywall", "FT"),
    ],
}

TRADE_ALIASES = {
    "ceramic": "flooring",
    "tile": "flooring",
    "flooring": "flooring",
    "carpentry": "carpentry/gabinets",
    "gabinets": "carpentry/gabinets",
    "finish carpentry": "carpentry/gabinets",
    "hvac": "hvac",
    "electrical": "electrical",
    "painting": "painting",
    "plumbing": "plumbing",
    "masonry": "masonry",
    "roofing": "roofing",
    "landscaping": "landscaping",
    "drywall": "drywall/framing",
    "framing": "drywall/framing",
    "drywall and framing": "drywall/framing",
}

DEFAULT_TRADE_ITEMS: dict[str, list[tuple[str, str]]] = {
    "painting": [("Wall paint system", "SF"), ("Ceiling paint system", "SF")],
    "hvac": [("Sheet metal ductwork", "FT"), ("Mechanical equipment allowance", "EA")],
    "electrical": [("Lighting and branch power allowance", "SF"), ("Distribution equipment", "EA")],
    "flooring": [("Tile flooring", "SF"), ("Floor transitions", "FT"), ("Wall tile", "SF")],
    "carpentry/gabinets": [("Millwork and wood trim", "FT"), ("Doors and hardware", "EA")],
    "plumbing": [("Plumbing fixtures", "EA"), ("Plumbing piping and drains", "FT")],
    "masonry": [("Masonry wall system", "SF")],
    "roofing": [("Roofing system", "SF")],
    "landscaping": [("Landscape planting", "EA"), ("Irrigation scope", "LS")],
    "drywall/framing": [("Gypsum board wall system", "SF"), ("Metal stud framing", "SF")],
}

BUILD_PROFILES: dict[str, dict[str, object]] = {
    "full": {
        "label": "Full dataset",
        "description": "Process all 3 sample projects and all 25 challenge projects.",
        "challenge_takeoff_ids": None,
    },
    "minimum": {
        "label": "Minimum acceptable submission",
        "description": "Process all 3 sample projects and 5 challenge projects end-to-end.",
        "challenge_takeoff_ids": ["TAKEOFF-30", "TAKEOFF-36", "TAKEOFF-39", "TAKEOFF-47", "TAKEOFF-55"],
    },
    "samples": {
        "label": "Samples only",
        "description": "Process only the 3 sample projects with visible gold outputs.",
        "challenge_takeoff_ids": [],
    },
}


def run_pipeline(root: Path, output_root: Path, profile: str = "full") -> dict[str, object]:
    include_sets, include_takeoff_ids = _discovery_filters(profile)
    projects = discover_projects(root, include_sets=include_sets, include_takeoff_ids=include_takeoff_ids)
    output_root.mkdir(parents=True, exist_ok=True)
    manifests_dir = output_root / "manifests"
    gold_dir = output_root / "gold_normalized"
    predictions_dir = output_root / "predictions"
    evaluations_dir = output_root / "evaluations"
    review_dir = output_root / "review_packets"
    for directory in (manifests_dir, gold_dir, predictions_dir, evaluations_dir, review_dir):
        directory.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "profile": profile,
        "profile_label": BUILD_PROFILES.get(profile, BUILD_PROFILES["full"])["label"],
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_count": len(projects),
        "sample_project_count": sum(1 for item in projects if item.set_name == "sample"),
        "challenge_project_count": sum(1 for item in projects if item.set_name == "challenge"),
        "processed_projects": [],
        "available_profiles": BUILD_PROFILES,
    }
    dashboard_projects: list[dict[str, object]] = []

    for project in projects:
        manifest_path = manifests_dir / f"{project.takeoff_id}.json"
        manifest_path.write_text(json.dumps(project.to_manifest(), indent=2))

        gold_output = _load_gold_output(project)
        if gold_output:
            gold_path = gold_dir / f"{project.takeoff_id}.json"
            serializable_gold = {key: value for key, value in gold_output.items() if key != "line_items_objects"}
            gold_path.write_text(json.dumps(serializable_gold, indent=2))

        predicted_items, ai_run = _predict_takeoff(project)
        evaluation = (
            score_predictions(predicted_items, gold_output["line_items_objects"]) if gold_output else _empty_evaluation()
        )
        prediction = TakeoffOutput(
            project_id=project.takeoff_id,
            project_name=project.project_name,
            set_name=project.set_name,
            trade_scope=str(ai_run.get("detected_trade_scope") or _project_trade_scope(project, gold_output)),
            input_files_used=[item.relative_path for item in project.input_files],
            ai_run=ai_run,
            line_items=predicted_items,
            evaluation_when_gold_available=evaluation,
            human_review_stub=_human_review_stub(project, predicted_items),
            project_manifest_path=manifest_path.relative_to(output_root).as_posix(),
        )
        prediction_path = predictions_dir / f"{project.takeoff_id}.json"
        prediction_path.write_text(json.dumps(prediction.to_dict(), indent=2))
        review_path = review_dir / f"{project.takeoff_id}_review.json"
        review_path.write_text(json.dumps(prediction.human_review_stub, indent=2))
        if gold_output:
            evaluation_path = evaluations_dir / f"{project.takeoff_id}.json"
            evaluation_path.write_text(json.dumps(evaluation, indent=2))

        dashboard_projects.append(
            {
                "takeoff_id": project.takeoff_id,
                "project_name": project.project_name,
                "set_name": project.set_name,
                "trade_scope": prediction.trade_scope,
                "input_file_count": len(project.input_files),
                "gold_file_count": len(project.gold_files),
                "predicted_item_count": len(predicted_items),
                "scored": bool(gold_output),
                "warnings": project.warnings,
                "artifact_paths": {
                    "manifest": manifest_path.relative_to(output_root).as_posix(),
                    "prediction": prediction_path.relative_to(output_root).as_posix(),
                    "review_packet": review_path.relative_to(output_root).as_posix(),
                    "gold": (gold_dir / f"{project.takeoff_id}.json").relative_to(output_root).as_posix()
                    if gold_output
                    else None,
                    "evaluation": (evaluations_dir / f"{project.takeoff_id}.json").relative_to(output_root).as_posix()
                    if gold_output
                    else None,
                },
                "prediction_preview": [item.to_dict() for item in predicted_items[:8]],
                "evaluation_summary": evaluation,
                "input_files_preview": [item.relative_path for item in project.input_files[:8]],
            }
        )

        summary["processed_projects"].append(
            {
                "takeoff_id": project.takeoff_id,
                "project_name": project.project_name,
                "set_name": project.set_name,
                "input_file_count": len(project.input_files),
                "gold_file_count": len(project.gold_files),
                "predicted_item_count": len(predicted_items),
                "scored": bool(gold_output),
            }
        )

    (output_root / "run_summary.json").write_text(json.dumps(summary, indent=2))
    dashboard_payload = {
        "summary": summary,
        "projects": dashboard_projects,
    }
    (output_root / "dashboard_data.json").write_text(json.dumps(dashboard_payload, indent=2))
    return summary

def _discovery_filters(profile: str) -> tuple[set[str] | None, set[str] | None]:
    config = BUILD_PROFILES.get(profile, BUILD_PROFILES["full"])
    challenge_ids = config["challenge_takeoff_ids"]
    if challenge_ids is None:
        return None, None
    sample_projects = {"TAKEOFF-28", "TAKEOFF-50", "TAKEOFF-56"}
    selected_ids = set(challenge_ids) | sample_projects
    include_sets = {"sample"} if not challenge_ids else {"sample", "challenge"}
    return include_sets, selected_ids


def _load_gold_output(project: ProjectRecord) -> dict[str, object] | None:
    workbook_files = [item for item in project.gold_files if item.extension == "xlsx"]
    if not workbook_files:
        return None
    workbook = parse_gold_workbook(Path(workbook_files[0].path))
    line_items = [item.to_dict() for item in workbook.line_items]
    return {
        "project_id": project.takeoff_id,
        "project_name": project.project_name,
        "trade_scope": workbook.scope,
        "project_area": workbook.project_area,
        "input_files_used": [item.relative_path for item in project.input_files],
        "line_items": line_items,
        "line_items_objects": workbook.line_items,
    }


def _predict_takeoff(project: ProjectRecord) -> tuple[list[TakeoffItem], dict[str, object]]:
    text_blocks = []
    input_files_used: list[str] = []
    assumptions: list[str] = []
    warnings = list(project.warnings)
    for item in project.input_files:
        input_files_used.append(item.relative_path)
        if item.extracted_text_preview:
            text_blocks.append(item.extracted_text_preview)
        else:
            text_blocks.append(Path(item.relative_path).name)
        if item.extension == "zip" and item.nested_files:
            text_blocks.extend(item.nested_files)
    corpus = "\n".join(text_blocks)
    corpus_lower = corpus.lower()

    trade_scope = _infer_trade_scope(project, corpus)
    project_area = _extract_project_area(corpus)
    if project_area:
        assumptions.append(f"Detected project area from source material: {project_area} SF.")
    else:
        warnings.append("No project area was detected in AI-visible files.")

    line_items: list[TakeoffItem] = []
    seen_descriptions: set[str] = set()
    explicit_items = _extract_explicit_line_items(project, corpus, trade_scope)
    for item in explicit_items:
        seen_descriptions.add(item.description.lower())
        line_items.append(item)
    if explicit_items:
        assumptions.append("Used explicit quantity statements recovered from project description text where available.")
    if not explicit_items:
        for trade in _expand_trades(trade_scope):
            for pattern, description, unit in TRADE_PATTERNS.get(trade, []):
                evidence_count = len(re.findall(pattern, corpus_lower, flags=re.I))
                if evidence_count == 0:
                    continue
                quantity = _estimate_quantity(unit, evidence_count, project_area)
                notes = [f"Evidence matches in corpus: {evidence_count}"]
                if unit == "SF" and project_area:
                    notes.append("Quantity uses detected project area as a first-pass proxy.")
                if description.lower() in seen_descriptions:
                    continue
                seen_descriptions.add(description.lower())
                line_items.append(
                    TakeoffItem(
                        item_number=None,
                        description=description,
                        quantity=quantity,
                        unit=unit,
                        confidence=min(0.35 + evidence_count * 0.08, 0.92),
                        source_reference=_best_source_reference(project, pattern),
                        division=None,
                        category=trade.title(),
                        notes=notes,
                    )
                )

    fallback_used = False
    for trade in _expand_trades(trade_scope):
        if trade == "unknown":
            continue
        category_matches = [
            item for item in line_items if item.category and item.category.lower() == trade.lower()
        ]
        if category_matches:
            continue
        for fallback in _fallback_items(trade, project, project_area):
            line_items.append(fallback)
            fallback_used = True
    if not line_items:
        assumptions.append("No structured quantity signals were extracted; fallback items are based on file names and declared scope.")
        for fallback in _fallback_items("unknown", project, project_area):
            line_items.append(fallback)
            fallback_used = True
    if fallback_used:
        assumptions.append("Some line items are trade-template fallbacks because the lightweight parser could not recover enough measurable text.")

    ai_run = {
        "run_id": f"{project.takeoff_id.lower()}-baseline-v1",
        "detected_trade_scope": trade_scope,
        "tools_or_models_used": _tools_used_for_project(project),
        "assumptions": assumptions,
        "warnings": warnings,
        "input_summary": {
            "text_corpus_length": len(corpus),
            "files_seen": len(input_files_used),
        },
    }
    return line_items, ai_run


def _tools_used_for_project(project: ProjectRecord) -> list[str]:
    tools = [
        "Python 3.13 stdlib CLI",
        "Custom XML parsers for XLSX/DOCX",
        "Lightweight PDF text extractor",
    ]
    if any("Gemini document extraction used" in note for item in project.input_files for note in item.notes):
        tools.append("Gemini document understanding OCR layer")
    return tools


def _extract_project_area(corpus: str) -> int | None:
    match = re.search(r"project area[:\s]+([0-9,]{3,8})", corpus, flags=re.I)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"total area(?:\s+is)?\s+([0-9,]{3,8})\s*sf", corpus, flags=re.I)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"footprint area(?:\s+is| of)?\s+([0-9,]{3,8})\s*sf", corpus, flags=re.I)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"\b([0-9,]{3,8})\s*sf\b", corpus, flags=re.I)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _infer_trade_scope(project: ProjectRecord, corpus: str) -> str:
    declared = str(project.metadata.get("client_services") or "").strip()
    if declared:
        return declared
    lowered = corpus.lower()
    scope_match = re.search(r"our scope is ([a-z /&-]+?)(?:\.|\n)", lowered)
    if scope_match:
        return scope_match.group(1).strip().title()
    if "paint" in lowered:
        return "Painting"
    if "roof" in lowered:
        return "Roofing"
    if "plumbing" in lowered:
        return "Plumbing"
    if "masonry" in lowered or "brick" in lowered:
        return "Masonry"
    if "landscape" in lowered or "irrigation" in lowered:
        return "Landscaping"
    if "drywall" in lowered or "framing" in lowered:
        return "Drywall and Framing"
    if "soffit" in lowered or "new wall" in lowered:
        return "Drywall and Framing"
    return "Unknown"


def _project_trade_scope(project: ProjectRecord, gold_output: dict[str, object] | None) -> str:
    declared = str(project.metadata.get("client_services") or "").strip()
    if declared:
        return declared
    if gold_output:
        return str(gold_output.get("trade_scope") or "Unknown")
    return "Unknown"


def _expand_trades(scope: str) -> list[str]:
    parts = [part.strip().lower() for part in re.split(r"[;,/]", scope) if part.strip()]
    normalized = [TRADE_ALIASES.get(part, part) for part in parts]
    return list(dict.fromkeys(normalized)) or ["unknown"]


def _extract_explicit_line_items(project: ProjectRecord, corpus: str, trade_scope: str) -> list[TakeoffItem]:
    items: list[TakeoffItem] = []
    source_reference = _project_description_reference(project) or (
        project.input_files[0].relative_path if project.input_files else "No source file available"
    )
    seen: set[tuple[str, str, float | int]] = set()
    project_area = _extract_project_area(corpus)
    for raw_line in corpus.splitlines():
        line = " ".join(raw_line.split())
        if not line or len(line) < 6:
            continue
        if trade_scope.lower().startswith("painting") and project_area:
            enumerated = re.match(r"^\d+\.\s*(Ceiling|Interior Walls|Doors|Exterior Walls)\b", line, flags=re.I)
            if enumerated:
                label_map = {
                    "ceiling": ("Ceiling paint", "SF", project_area),
                    "interior walls": ("Interior wall paint", "SF", project_area),
                    "doors": ("Door paint", "EA", 1),
                    "exterior walls": ("Exterior wall paint", "SF", project_area),
                }
                label, unit, quantity = label_map[enumerated.group(1).lower()]
                key = (label.lower(), unit, quantity)
                if key not in seen:
                    seen.add(key)
                    items.append(
                        TakeoffItem(
                            item_number=None,
                            description=label,
                            quantity=quantity,
                            unit=unit,
                            confidence=0.55,
                            source_reference=source_reference,
                            category=trade_scope.lower(),
                            notes=["Recovered from enumerated scope list in project description text; quantity is a proxy where no explicit quantity was provided."],
                        )
                    )
                continue
        specific_matchers = [
            (r"walls?\s+area\s+is\s+around\s+([0-9,]+(?:\.\d+)?)\s*(SF|FT|LF)\b", "Wall area"),
            (r"roofing\s+having\s+the\s+area\s+of\s+([0-9,]+(?:\.\d+)?)\s*(SF|FT|LF)\b", "Roofing system"),
        ]
        matched_specific = False
        for pattern, label in specific_matchers:
            specific = re.search(pattern, line, flags=re.I)
            if not specific:
                continue
            quantity = _parse_number(specific.group(1))
            unit = specific.group(2).upper().replace("LF", "FT")
            key = (label.lower(), unit, quantity)
            if quantity is None or key in seen:
                matched_specific = True
                continue
            seen.add(key)
            items.append(
                TakeoffItem(
                    item_number=None,
                    description=label,
                    quantity=quantity,
                    unit=unit,
                    confidence=0.82,
                    source_reference=source_reference,
                    category=trade_scope.lower(),
                    notes=["Recovered from explicit quantity statement in project description text."],
                )
            )
            matched_specific = True
        if matched_specific:
            continue
        eq_match = re.match(
            r"^(?:\d+\.\s*)?(.+?)\s*=\s*([0-9,]+(?:\.\d+)?)\s*(SF|FT|LF|EA|LS)\b",
            line,
            flags=re.I,
        )
        area_match = re.match(
            r"^(?:the\s+)?(.+?)\s+(?:area is around|area is|area of|is around)\s*([0-9,]+(?:\.\d+)?)\s*(SF|FT|LF)\b",
            line,
            flags=re.I,
        )
        match = eq_match or area_match
        if not match:
            continue
        description = _normalize_explicit_description(match.group(1), trade_scope)
        description_lower = description.lower()
        if "project" in description_lower or "footprint" in description_lower:
            continue
        quantity = _parse_number(match.group(2))
        unit = match.group(3).upper().replace("LF", "FT")
        key = (description.lower(), unit, quantity)
        if quantity is None or key in seen:
            continue
        seen.add(key)
        items.append(
            TakeoffItem(
                item_number=None,
                description=description,
                quantity=quantity,
                unit=unit,
                confidence=0.82,
                source_reference=source_reference,
                category=trade_scope.lower(),
                notes=["Recovered from explicit quantity statement in project description text."],
            )
        )
    return items


def _normalize_explicit_description(text: str, trade_scope: str) -> str:
    cleaned = text.replace("(", " ").replace(")", " ")
    cleaned = re.sub(r"\barea\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bapprox\.?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[:,-]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    lower = cleaned.lower()
    if trade_scope.lower().startswith("painting"):
        mapping = {
            "paint on walls": "Wall paint",
            "wall paint": "Wall paint",
            "paint on wall base": "Wall base paint",
            "paint on wall trims": "Wall trim paint",
            "door paint": "Door paint",
            "paint on doors": "Door paint",
            "door frame paint": "Door frame paint",
            "paint on door frames": "Door frame paint",
            "ceiling paint": "Ceiling paint",
        }
        return mapping.get(lower, cleaned.title())
    return cleaned.title()


def _parse_number(value: str) -> float | int | None:
    value = value.replace(",", "").strip()
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _project_description_reference(project: ProjectRecord) -> str | None:
    for item in project.input_files:
        if item.relative_path.endswith("Project Description.txt"):
            return item.relative_path
    return None


def _estimate_quantity(unit: str, evidence_count: int, project_area: int | None) -> int | float:
    if unit == "SF":
        if project_area:
            return int(project_area)
        return max(evidence_count * 100, 100)
    if unit == "FT":
        return max(evidence_count * 8, 8)
    if unit == "EA":
        return max(evidence_count, 1)
    return 1


def _best_source_reference(project: ProjectRecord, pattern: str) -> str:
    regex = re.compile(pattern, flags=re.I)
    for item in project.input_files:
        if item.extracted_text_preview and regex.search(item.extracted_text_preview):
            return item.relative_path
    return project.input_files[0].relative_path if project.input_files else "No source file available"


def _fallback_items(scope: str, project: ProjectRecord, project_area: int | None) -> Iterable[TakeoffItem]:
    category = scope or "General"
    references = ", ".join(Path(item.relative_path).name for item in project.input_files[:3])
    defaults = DEFAULT_TRADE_ITEMS.get(scope)
    if not defaults:
        defaults = [(f"{project.project_name} scope review allowance", "LS")]
    for description, unit in defaults:
        yield TakeoffItem(
            item_number=None,
            description=description,
            quantity=_estimate_quantity(unit, 1, project_area),
            unit=unit,
            confidence=0.2,
            source_reference=references or "No input files found",
            category=category,
            notes=["Fallback line item because no reliable structured extraction was found."],
        )


def _human_review_stub(project: ProjectRecord, items: list[TakeoffItem]) -> dict[str, object]:
    return {
        "status": "needs_review",
        "reviewer_actions": [
            "Confirm scope and trade split against drawings/specs",
            "Replace proxy quantities with measured quantities",
            "Mark missing items and delete false positives",
        ],
        "proposed_corrections_file": f"review_packets/{project.takeoff_id}_review.json",
        "line_items_to_review": [
            {
                "description": item.description,
                "predicted_quantity": item.quantity,
                "unit": item.unit,
                "confidence": item.confidence,
            }
            for item in items
        ],
    }


def _empty_evaluation() -> dict[str, object]:
    return {
        "matched_items": 0,
        "missing_items": [],
        "extra_items": [],
        "quantity_differences": [],
        "precision": 0.0,
        "recall": 0.0,
        "overall_notes": "No gold output available for challenge projects.",
    }
