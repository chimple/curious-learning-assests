#!/usr/bin/env python3
"""Build the RESPECT lesson workbook from a Chimple course-ID configuration.

The configuration keeps course assignments aligned with Chimple's
language/grade/subject hierarchy instead of hard-coding a fixed sheet list.

Course IDs are grouped by language, grade, and subject in
``chimple_course_config.json``. Three source modes are supported:

1) Dashboard API mode (recommended for fresh data)
   The script requests course-detail rows by course ID. Configure the endpoint
   using --api-url or CHIMPLE_DASHBOARD_API_URL.

2) Dashboard XLSX mode
   The script filters an existing Chimple dashboard export by the configured
   course IDs. If no ``All Courses`` sheet exists, matching group sheets are used.

3) Direct Supabase mode
   The script reads the public course, chapter, chapter_lesson, and lesson
   tables by course ID. Supply the URL and key as arguments or environment
   variables; credentials are never stored in this script.

The output workbook has one sheet per language, grade, and subject combination,
with these columns:
  lesson_id, title, lesson_name, grade, curriculum, chapter_id, chapter_name,
  chapter_image, lesson_image, cocos_lesson_code, lido_lesson_id,
  cocosChapterCode, Asset Link
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUTPUT_NAME = "Respect Course Latest All Course Details From dashboard.xlsx"
DEFAULT_COURSE_CONFIG = Path(__file__).with_name("chimple_course_config.json")
CLI_EXAMPLES = """
PowerShell API mode:
  $env:CHIMPLE_DASHBOARD_API_URL = "https://your-dashboard.example/course-details"
  $env:CHIMPLE_DASHBOARD_API_TOKEN = "<token>"  # optional
  python .\build_respect_course_workbook.py

PowerShell Supabase mode:
  $env:SUPABASE_URL = "https://your-project.supabase.co"
  $env:SUPABASE_ANON_KEY = "<key>"
  python .\build_respect_course_workbook.py

The Supabase key can also be supplied through SUPABASE_SERVICE_ROLE_KEY.
When exactly one backend is configured in the environment, it is selected automatically.
If both are configured, pass --api or --supabase to choose one.
"""
COLUMNS = [
    "lesson_id",
    "title",
    "lesson_name",
    "grade",
    "curriculum",
    "chapter_id",
    "chapter_name",
    "chapter_image",
    "lesson_image",
    "cocos_lesson_code",
    "lido_lesson_id",
    "cocosChapterCode",
    "Asset Link",
]

ASSET_BASE = "https://raw.githubusercontent.com/chimple/chimple-zips/main"

ALIASES = {
    "lesson_id": ["lesson_id", "lessonId", "lesson_doc_id", "doc_id"],
    "title": ["title", "lesson_name", "lessonName", "name"],
    "lesson_name": ["lesson_name", "lessonName", "title", "name"],
    "grade": ["grade", "grade_name", "course_grade_name"],
    "curriculum": ["curriculum", "curriculum_name"],
    "chapter_id": ["chapter_id", "chapterId", "chapter_doc_id"],
    "chapter_name": ["chapter_name", "chapterName", "chapter_title"],
    "chapter_image": ["chapter_image", "chapterImage", "Chapter-Icon-Link"],
    "lesson_image": ["lesson_image", "lessonImage", "Lesson-Icon-Link"],
    "cocos_lesson_code": [
        "cocos_lesson_code",
        "cocosLessonCode",
        "cocos_lesson_id",
        "cocosLessonId",
        "id",
    ],
    "lido_lesson_id": ["lido_lesson_id", "lidoLessonId"],
    "cocosChapterCode": [
        "cocosChapterCode",
        "cocos_chapter_code",
        "cocos_chapter_id",
        "cocosChapterId",
    ],
    "Asset Link": ["Asset Link", "asset_link", "assetLink", "zip_url", "zipUrl"],
    "course_id": ["course_id", "courseId"],
}


def clean_key(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_course_groups(path: Path) -> List[Dict[str, Any]]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read course configuration {path}: {exc}") from exc

    if not isinstance(config, dict) or config.get("application") != "Chimple Kids Learning":
        raise ValueError("Course configuration application must be 'Chimple Kids Learning'.")
    languages = config.get("languages")
    if not isinstance(languages, list) or not languages:
        raise ValueError("Course configuration must contain a non-empty languages array.")

    groups: List[Dict[str, Any]] = []
    seen_sheets: set[str] = set()
    for language_entry in languages:
        if not isinstance(language_entry, dict):
            raise ValueError("Each language entry must be an object.")
        language = clean_text(language_entry.get("language"))
        grades = language_entry.get("grades")
        if not language or not isinstance(grades, list):
            raise ValueError("Each language needs a name and a grades array.")

        for grade_entry in grades:
            if not isinstance(grade_entry, dict):
                raise ValueError(f"Grades for {language} must be objects.")
            grade = clean_text(grade_entry.get("grade"))
            subjects = grade_entry.get("subjects")
            if not grade or not isinstance(subjects, list):
                raise ValueError(f"Each {language} grade needs a number and subjects array.")

            for subject_entry in subjects:
                if not isinstance(subject_entry, dict):
                    raise ValueError(f"Subjects for {language} Grade {grade} must be objects.")
                subject = clean_text(subject_entry.get("subject"))
                raw_course_ids = subject_entry.get("courses")
                if not subject or not isinstance(raw_course_ids, list):
                    raise ValueError(
                        f"Each {language} Grade {grade} subject needs a name and courses array."
                    )
                course_ids = [clean_text(course_id) for course_id in raw_course_ids]
                if any(not course_id for course_id in course_ids):
                    raise ValueError(
                        f"Course IDs cannot be empty in {language} Grade {grade} {subject}."
                    )

                sheet = f"{language} Grade {grade} {subject}"
                if len(sheet) > 31:
                    raise ValueError(f"Excel sheet name exceeds 31 characters: {sheet!r}.")
                if sheet in seen_sheets:
                    raise ValueError(f"Duplicate language/grade/subject group: {sheet!r}.")
                seen_sheets.add(sheet)
                groups.append(
                    {
                        "language": language,
                        "grade": grade,
                        "subject": subject,
                        "course_ids": list(dict.fromkeys(course_ids)),
                        "sheet": sheet,
                    }
                )

    if not groups:
        raise ValueError("Course configuration must include at least one grade and subject.")
    return groups


def pick(row: Mapping[str, Any], canonical: str) -> Any:
    for key in ALIASES.get(canonical, [canonical]):
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def derive_chapter_code(cocos_code: str) -> str:
    """en0400 -> en04, maths1604 -> maths16, puzzle0001 -> puzzle00."""
    code = cocos_code.strip()
    m = re.match(r"^(.*?)(\d{4})$", code)
    if not m:
        return ""
    return f"{m.group(1)}{m.group(2)[:2]}"


def make_asset_link(cocos_code: str) -> str:
    return f"{ASSET_BASE}/{cocos_code}.zip"


def normalize_lesson(row: Mapping[str, Any], generate_asset: bool = True) -> Optional[Dict[str, str]]:
    lesson_id = clean_text(pick(row, "lesson_id"))
    if not lesson_id:
        # Chapter/group heading: explicitly excluded by requirement.
        return None

    cocos_code = clean_text(pick(row, "cocos_lesson_code"))
    lido_lesson_id = clean_text(pick(row, "lido_lesson_id"))
    if not cocos_code and not lido_lesson_id:
        return None

    name = clean_text(pick(row, "lesson_name")) or clean_text(pick(row, "title"))
    if not name:
        return None

    asset = clean_text(pick(row, "Asset Link"))
    # Cocos bundles are downloadable ZIPs. A Lido-only lesson has no Cocos ZIP
    # and must remain publishable so Cuba can use its Lido compatibility path.
    if cocos_code and not asset and generate_asset:
        asset = make_asset_link(cocos_code)
    if cocos_code and not asset:
        return None

    chapter_code = clean_text(pick(row, "cocosChapterCode"))
    if cocos_code and not chapter_code:
        chapter_code = derive_chapter_code(cocos_code)

    return {
        "lesson_id": lesson_id,
        "title": name,
        "lesson_name": name,
        "grade": clean_text(pick(row, "grade")),
        "curriculum": clean_text(pick(row, "curriculum")),
        "chapter_id": clean_text(pick(row, "chapter_id")),
        "chapter_name": clean_text(pick(row, "chapter_name")),
        "chapter_image": clean_text(pick(row, "chapter_image")),
        "lesson_image": clean_text(pick(row, "lesson_image")),
        "cocos_lesson_code": cocos_code,
        "lido_lesson_id": lido_lesson_id,
        "cocosChapterCode": chapter_code,
        "Asset Link": asset,
    }


def verify_asset(url: str, timeout: float = 12.0) -> bool:
    """Return True only when the public ZIP URL responds successfully."""
    try:
        # Some hosts do not support HEAD reliably, so fall back to a tiny GET.
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code < 400:
            return True
        r = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"Range": "bytes=0-0"},
            stream=True,
        )
        return r.status_code in (200, 206)
    except requests.RequestException:
        return False


def dedupe_lessons(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        lid = row["lesson_id"]
        if lid in seen:
            continue
        seen.add(lid)
        result.append(row)
    return result


def extract_json_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "data", "results", "items", "course_details"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        # Some APIs return {"data": {"rows": [...]}}
        data = payload.get("data")
        if isinstance(data, dict):
            return extract_json_rows(data)
    raise ValueError("API response does not contain a recognizable row list.")


def fetch_api_rows(
    api_url: str,
    course_id: str,
    token: Optional[str],
    timeout: float,
) -> List[Dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        api_url,
        params={"course_id": course_id},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return extract_json_rows(response.json())


def build_from_api(
    args: argparse.Namespace,
    course_groups: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, str]]]:
    api_url = args.api_url or os.getenv("CHIMPLE_DASHBOARD_API_URL", "")
    if not api_url:
        raise ValueError(
            "API mode needs --api-url or CHIMPLE_DASHBOARD_API_URL. "
            "Point it at the Chimple dashboard/course-details endpoint that accepts "
            "a course_id query parameter."
        )
    token = args.api_token or os.getenv("CHIMPLE_DASHBOARD_API_TOKEN")

    cache: Dict[str, List[Dict[str, Any]]] = {}
    out: Dict[str, List[Dict[str, str]]] = {}
    for group in course_groups:
        raw_rows: List[Dict[str, Any]] = []
        for course_id in group["course_ids"]:
            if course_id not in cache:
                cache[course_id] = fetch_api_rows(
                    api_url=api_url,
                    course_id=course_id,
                    token=token,
                    timeout=args.timeout,
                )
            raw_rows.extend(cache[course_id])
        normalized: List[Dict[str, str]] = []
        for raw in raw_rows:
            row = normalize_lesson(raw, generate_asset=True)
            if row:
                normalized.append(row)
        out[group["sheet"]] = dedupe_lessons(normalized)
    return out


def chunks(items: Sequence[str], size: int = 400) -> Iterable[Sequence[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def supabase_rows(
    base_url: str,
    table: str,
    params: Mapping[str, str],
    key: str,
    timeout: float,
) -> List[Dict[str, Any]]:
    """Fetch every page from a Supabase REST table without exposing the key."""
    endpoint = f"{base_url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "Accept": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Range-Unit": "items",
    }
    rows: List[Dict[str, Any]] = []
    start, page_size = 0, 1000
    while True:
        page_headers = {**headers, "Range": f"{start}-{start + page_size - 1}"}
        response = requests.get(endpoint, params=params, headers=page_headers, timeout=timeout)
        response.raise_for_status()
        page = extract_json_rows(response.json())
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def fetch_supabase_course_rows(
    base_url: str,
    key: str,
    course_id: str,
    timeout: float,
) -> List[Dict[str, Any]]:
    courses = supabase_rows(
        base_url,
        "course",
        {
            "select": (
                "id,grade_id,curriculum_id,"
                "grade:grade!public_course_grade_id_fkey(name),"
                "curriculum:curriculum!public_course_curriculum_id_fkey(name)"
            ),
            "id": f"eq.{course_id}",
            "is_deleted": "eq.false",
        },
        key,
        timeout,
    )
    course_by_id = {clean_text(course.get("id")): course for course in courses}
    if not course_by_id:
        return []

    chapters: List[Dict[str, Any]] = []
    for course_ids in chunks(list(course_by_id)):
        chapters.extend(
            supabase_rows(
                base_url,
                "chapter",
                {
                    "select": "id,course_id,name,image,sort_index",
                    "course_id": f"in.({','.join(course_ids)})",
                    "is_deleted": "eq.false",
                    "order": "sort_index.asc",
                },
                key,
                timeout,
            )
        )
    chapters.sort(
        key=lambda chapter: (
            chapter.get("sort_index") is None,
            chapter.get("sort_index") if chapter.get("sort_index") is not None else 0,
            clean_text(chapter.get("id")),
        )
    )
    chapter_by_id = {clean_text(chapter.get("id")): chapter for chapter in chapters}
    if not chapter_by_id:
        return []
    chapter_order = {chapter_id: index for index, chapter_id in enumerate(chapter_by_id)}

    # Query the join table, rather than lesson directly, because lesson membership
    # and ordering are defined by chapter_lesson in Cuba as well.
    course_rows: List[Dict[str, Any]] = []
    for chapter_ids in chunks(list(chapter_by_id)):
        links = supabase_rows(
            base_url,
            "chapter_lesson",
            {
                "select": (
                    "chapter_id,lesson_id,sort_index,"
                    "lesson:lesson_id(id,name,image,cocos_lesson_id,lido_lesson_id,"
                    "cocos_chapter_code,is_deleted)"
                ),
                "chapter_id": f"in.({','.join(chapter_ids)})",
                "is_deleted": "eq.false",
                "order": "sort_index.asc",
            },
            key,
            timeout,
        )
        for link in links:
            lesson = link.get("lesson")
            chapter = chapter_by_id.get(clean_text(link.get("chapter_id")))
            if not isinstance(lesson, dict) or not chapter or lesson.get("is_deleted"):
                continue
            course = course_by_id.get(clean_text(chapter.get("course_id")))
            if not course:
                continue
            course_rows.append(
                {
                    "course_id": course.get("id"),
                    "grade": (
                        course.get("grade", {}).get("name")
                        if isinstance(course.get("grade"), dict)
                        else None
                    ),
                    "curriculum": (
                        course.get("curriculum", {}).get("name")
                        if isinstance(course.get("curriculum"), dict)
                        else None
                    ),
                    "chapter_id": chapter.get("id"),
                    "chapter_name": chapter.get("name"),
                    "chapter_image": chapter.get("image"),
                    "lesson_id": lesson.get("id") or link.get("lesson_id"),
                    "lesson_name": lesson.get("name"),
                    "lesson_image": lesson.get("image"),
                    "cocos_lesson_code": lesson.get("cocos_lesson_id"),
                    "lido_lesson_id": lesson.get("lido_lesson_id"),
                    "cocosChapterCode": lesson.get("cocos_chapter_code"),
                    "chapter_index": chapter.get("sort_index"),
                    "chapter_order": chapter_order[clean_text(link.get("chapter_id"))],
                    "lesson_index": link.get("sort_index"),
                }
            )
    # Sort after the join because each table query orders only its own index.
    course_rows.sort(
        key=lambda row: (
            row["chapter_order"],
            row["lesson_index"] is None,
            row["lesson_index"] if row["lesson_index"] is not None else 0,
        )
    )
    return course_rows


def build_from_supabase(
    args: argparse.Namespace,
    course_groups: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, str]]]:
    base_url = args.supabase_url or os.getenv("SUPABASE_URL", "")
    key = args.supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not base_url or not key:
        raise ValueError(
            "Supabase mode needs --supabase-url / SUPABASE_URL and "
            "--supabase-key / SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY."
        )

    cache: Dict[str, List[Dict[str, Any]]] = {}
    out: Dict[str, List[Dict[str, str]]] = {}
    for group in course_groups:
        normalized: List[Dict[str, str]] = []
        for course_id in group["course_ids"]:
            if course_id not in cache:
                cache[course_id] = fetch_supabase_course_rows(
                    base_url=base_url,
                    key=key,
                    course_id=course_id,
                    timeout=args.timeout,
                )
            for raw in cache[course_id]:
                row = normalize_lesson(raw, generate_asset=True)
                if row:
                    normalized.append(row)
        out[group["sheet"]] = dedupe_lessons(normalized)
    return out


def worksheet_dict_rows(ws) -> List[Dict[str, Any]]:
    headers = [clean_key(c.value) for c in ws[1]]
    rows: List[Dict[str, Any]] = []
    for values in ws.iter_rows(min_row=2, values_only=True):
        d: Dict[str, Any] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            d[header] = values[idx] if idx < len(values) else None
        rows.append(d)
    return rows


def build_from_xlsx(
    path: Path,
    course_groups: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[str, List[str]]]:
    wb = load_workbook(path, data_only=True, read_only=True)
    output: Dict[str, List[Dict[str, str]]] = {}
    selected_courses: Dict[str, List[str]] = {}
    has_all_courses = "All Courses" in wb.sheetnames
    all_rows = worksheet_dict_rows(wb["All Courses"]) if has_all_courses else []
    missing_sheets = [
        group["sheet"]
        for group in course_groups
        if group["course_ids"] and not has_all_courses and group["sheet"] not in wb.sheetnames
    ]
    if missing_sheets:
        wb.close()
        raise ValueError(
            "Source workbook needs an All Courses sheet or matching configured sheets: "
            + ", ".join(missing_sheets)
        )
    if has_all_courses:
        requested_ids = {
            course_id for group in course_groups for course_id in group["course_ids"]
        }
        available_ids = {clean_text(pick(row, "course_id")) for row in all_rows}
        missing_ids = sorted(requested_ids - available_ids)
        if missing_ids:
            wb.close()
            raise ValueError(
                "Course IDs not found in the All Courses sheet: " + ", ".join(missing_ids)
            )

    for group in course_groups:
        sheet = group["sheet"]
        current_rows = worksheet_dict_rows(wb[sheet]) if sheet in wb.sheetnames else []
        if has_all_courses:
            course_ids = set(group["course_ids"])
            source_rows = [
                row for row in all_rows if clean_text(pick(row, "course_id")) in course_ids
            ]
        else:
            source_rows = current_rows
        selected_courses[sheet] = list(group["course_ids"])

        # Enrich dashboard-wide rows from the curated sheet when the broad
        # export is missing a human-readable title or an already-known asset URL.
        current_by_id = {
            clean_text(pick(r, "lesson_id")): r
            for r in current_rows
            if clean_text(pick(r, "lesson_id"))
        }
        current_by_code = {
            clean_text(pick(r, "cocos_lesson_code")): r
            for r in current_rows
            if clean_text(pick(r, "cocos_lesson_code"))
        }

        normalized = []
        for raw in source_rows:
            enriched = dict(raw)
            fallback = (
                current_by_id.get(clean_text(pick(raw, "lesson_id")))
                or current_by_code.get(clean_text(pick(raw, "cocos_lesson_code")))
            )
            if fallback:
                for canonical in (
                    "title",
                    "lesson_name",
                    "grade",
                    "curriculum",
                    "chapter_id",
                    "chapter_name",
                    "chapter_image",
                    "lesson_image",
                    "cocos_lesson_code",
                    "lido_lesson_id",
                    "cocosChapterCode",
                    "Asset Link",
                ):
                    if not clean_text(pick(enriched, canonical)):
                        value = pick(fallback, canonical)
                        if value not in (None, ""):
                            enriched[canonical] = value
            row = normalize_lesson(enriched, generate_asset=True)
            if row:
                normalized.append(row)
        output[sheet] = dedupe_lessons(normalized)

    wb.close()
    return output, selected_courses


def write_workbook(
    data: Mapping[str, Sequence[Mapping[str, str]]],
    output: Path,
    course_groups: Sequence[Mapping[str, Any]],
) -> None:
    wb = Workbook()
    wb.remove(wb.active)

    for group in course_groups:
        sheet = group["sheet"]
        ws = wb.create_sheet(sheet)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"
        ws.sheet_view.showGridLines = False

        for col_idx, header in enumerate(COLUMNS, start=1):
            cell = ws.cell(1, col_idx, header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row_idx, item in enumerate(data.get(sheet, []), start=2):
            for col_idx, header in enumerate(COLUMNS, start=1):
                cell = ws.cell(row_idx, col_idx, item.get(header, ""))
                cell.alignment = Alignment(vertical="top", wrap_text=False)
                if header == "Asset Link" and cell.value:
                    cell.hyperlink = str(cell.value)
                    cell.style = "Hyperlink"

        widths = {
            "A": 24,
            "B": 34,
            "C": 34,
            "D": 18,
            "E": 30,
            "F": 24,
            "G": 34,
            "H": 24,
            "I": 24,
            "J": 24,
            "K": 78,
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        ws.row_dimensions[1].height = 24
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(1, ws.max_row)}"

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)


def validate_output(data: Mapping[str, Sequence[Mapping[str, str]]], verify_assets: bool) -> None:
    errors: List[str] = []
    for sheet, rows in data.items():
        ids = set()
        for i, row in enumerate(rows, start=2):
            for col in ("lesson_id", "title", "lesson_name"):
                if not clean_text(row.get(col)):
                    errors.append(f"{sheet}!{i}: empty {col}")
            cocos_code = clean_text(row.get("cocos_lesson_code"))
            lido_lesson_id = clean_text(row.get("lido_lesson_id"))
            if not cocos_code and not lido_lesson_id:
                errors.append(f"{sheet}!{i}: missing Cocos and Lido lesson IDs")
            if cocos_code:
                # Chapter code is optional catalogue metadata. The bundle URL is
                # the required Cocos playback dependency.
                if not clean_text(row.get("Asset Link")):
                    errors.append(f"{sheet}!{i}: empty Asset Link for Cocos lesson")
            lid = row.get("lesson_id", "")
            if lid in ids:
                errors.append(f"{sheet}!{i}: duplicate lesson_id {lid}")
            ids.add(lid)
            if verify_assets and row.get("Asset Link") and not verify_asset(row["Asset Link"]):
                errors.append(f"{sheet}!{i}: asset unavailable: {row['Asset Link']}")
    if errors:
        preview = "\n".join(errors[:30])
        more = "" if len(errors) <= 30 else f"\n... and {len(errors)-30} more"
        raise ValueError(f"Output validation failed:\n{preview}{more}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=CLI_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--source-xlsx",
        type=Path,
        help="Dashboard XLSX export with an All Courses sheet or configured group sheets.",
    )
    source.add_argument(
        "--api",
        action="store_true",
        help="Fetch fresh rows using the course IDs in the configuration.",
    )
    source.add_argument(
        "--supabase",
        action="store_true",
        help="Fetch fresh course, chapter, and lesson data directly from Supabase REST.",
    )

    parser.add_argument(
        "--course-config",
        type=Path,
        default=DEFAULT_COURSE_CONFIG,
        help="JSON mapping languages, grades, subjects, and course IDs.",
    )
    parser.add_argument("--api-url", help="Course-details API URL; or set CHIMPLE_DASHBOARD_API_URL.")
    parser.add_argument("--api-token", help="Bearer token; or set CHIMPLE_DASHBOARD_API_TOKEN.")
    parser.add_argument("--supabase-url", help="Supabase project URL; or set SUPABASE_URL.")
    parser.add_argument(
        "--supabase-key",
        help="Supabase service-role/anon key; or set SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--verify-assets",
        action="store_true",
        help="Check every public ZIP URL and fail if any asset cannot be reached.",
    )
    parser.add_argument("--output", type=Path, default=Path(OUTPUT_NAME))
    args = parser.parse_args()
    course_groups = load_course_groups(args.course_config)
    if not any(group["course_ids"] for group in course_groups):
        raise ValueError("Add at least one course ID under a subject in the course configuration.")

    api_url = args.api_url or os.getenv("CHIMPLE_DASHBOARD_API_URL", "")
    supabase_url = args.supabase_url or os.getenv("SUPABASE_URL", "")
    supabase_key = (
        args.supabase_key
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY", "")
    )
    if not args.source_xlsx and not args.api and not args.supabase:
        use_api = bool(api_url)
        use_supabase = bool(supabase_url and supabase_key)
        if use_api == use_supabase:
            if use_api:
                raise ValueError(
                    "Both API and Supabase environments are configured; pass --api or --supabase."
                )
            raise ValueError(
                "Set CHIMPLE_DASHBOARD_API_URL or SUPABASE_URL and a Supabase key, "
                "or provide --source-xlsx."
            )
        args.api = use_api
        args.supabase = use_supabase

    if args.source_xlsx:
        data, selected = build_from_xlsx(args.source_xlsx, course_groups)
        if selected:
            print("Configured course IDs:")
            for sheet, course_ids in selected.items():
                print(f"  {sheet}: {', '.join(course_ids) if course_ids else '(none)'}")
    elif args.supabase:
        data = build_from_supabase(args, course_groups)
    else:
        data = build_from_api(args, course_groups)

    validate_output(data, verify_assets=args.verify_assets)
    write_workbook(data, args.output, course_groups)

    print(f"Wrote: {args.output}")
    print("Course and lesson counts:")
    for group in course_groups:
        sheet = group["sheet"]
        print(
            f"  {sheet}: {len(group['course_ids'])} courses, "
            f"{len(data.get(sheet, []))} lessons"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
