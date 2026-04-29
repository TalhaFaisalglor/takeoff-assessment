from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .models import TakeoffItem


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class GoldWorkbook:
    project_id: str
    scope: str
    project_area: str
    line_items: list[TakeoffItem]


def _column_letters(cell_ref: str) -> str:
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _load_sheet_rows(path: Path) -> list[dict[str, str]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheet = workbook.find("a:sheets", NS)[0]
        rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_map[rid]
        sheet_path = "xl/" + target if not target.startswith("xl/") else target
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared:
                text = "".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                shared_strings.append(text)
        root = ET.fromstring(archive.read(sheet_path))
    rows: list[dict[str, str]] = []
    for row in root.find("a:sheetData", NS):
        values: dict[str, str] = {}
        for cell in row:
            ref = cell.attrib.get("r", "")
            col = _column_letters(ref)
            value_node = cell.find("a:v", NS)
            if value_node is None:
                continue
            value = value_node.text or ""
            if cell.attrib.get("t") == "s":
                value = shared_strings[int(value)]
            values[col] = value.strip()
        rows.append(values)
    return rows


def parse_gold_workbook(path: Path) -> GoldWorkbook:
    rows = _load_sheet_rows(path)
    project_id = ""
    scope = ""
    project_area = ""
    header_map: dict[str, str] = {}
    line_items: list[TakeoffItem] = []
    current_division = ""
    current_category = ""

    for row in rows:
        if row.get("A") == "PROJECT ID:":
            project_id = row.get("C") or row.get("D") or project_id
            continue
        if row.get("A") == "SCOPE:":
            scope = row.get("C") or row.get("D") or scope
            continue
        if row.get("A") == "PROJECT AREA:":
            project_area = row.get("C") or row.get("D") or project_area
            continue
        if row.get("A") == "ITEM #":
            for key, value in row.items():
                header_map[value.upper()] = key
            continue

        description_col = header_map.get("DESCRIPTION")
        if not description_col:
            continue
        description = row.get(description_col, "").strip()
        if not description:
            continue

        item_number = row.get(header_map.get("ITEM #", "A"), "").strip()
        drawing_ref = row.get(header_map.get("DRAWING #", "B"), "").strip() or None
        section_ref = row.get(header_map.get("SECTION #", "C"), "").strip() or None

        if description.startswith("DIVISION "):
            current_division = description
            current_category = ""
            continue
        if not item_number:
            current_category = description
            continue
        if "SUBTOTAL" in description.upper() or "TOTAL BASE BID" in description.upper():
            continue

        qty_col = header_map.get("QUANTITY")
        unit_col = header_map.get("UNIT")
        wastage_col = header_map.get("WASTAGE")
        qty_waste_col = header_map.get("QUANTITY WITH WASTAGE")
        raw_qty = _to_number(row.get(qty_col, "")) if qty_col else None
        qty_with_wastage = _to_number(row.get(qty_waste_col, "")) if qty_waste_col else raw_qty
        item = TakeoffItem(
            item_number=item_number,
            description=description,
            quantity=qty_with_wastage,
            unit=row.get(unit_col, "").strip() or None if unit_col else None,
            confidence=1.0,
            source_reference=_combine_refs(drawing_ref, section_ref, current_division, current_category),
            drawing_reference=drawing_ref,
            section_reference=section_ref,
            division=current_division or None,
            category=current_category or None,
            raw_quantity=raw_qty,
            wastage=_to_number(row.get(wastage_col, "")) if wastage_col else None,
            quantity_with_wastage=qty_with_wastage,
        )
        line_items.append(item)

    return GoldWorkbook(project_id=project_id, scope=scope, project_area=project_area, line_items=line_items)


def _combine_refs(drawing: str | None, section: str | None, division: str, category: str) -> str:
    parts = [part for part in (drawing, section, division, category) if part]
    return " | ".join(parts)


def _to_number(value: str) -> float | int | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else round(number, 3)
