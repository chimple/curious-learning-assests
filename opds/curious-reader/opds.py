#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_iso8601() -> str:
    # Match the examples which include timezone and fractional seconds
    return datetime.now(timezone.utc).isoformat()


def parse_query_param(url: str, key: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        vals = qs.get(key)
        if vals:
            return vals[0]
        return None
    except Exception:
        return None


def classify_web_app(entry: Dict[str, Any]) -> str:
    url: str = entry.get("appUrl", "")
    if "ftm" in url.lower():
        return "ftm"
    if "story" in url.lower():
        return "story"
    if "assessment" in url.lower():
        return "assessment"
    return "other"


def build_opds_feed(base_out_url: str, web_apps: List[Dict[str, Any]], out_path: Path) -> None:
    navigation: List[Dict[str, Any]] = []

    # Build unique languages from FTM entries primarily
    seen_lang_codes: Dict[str, Dict[str, Any]] = {}
    for app in web_apps:
        if classify_web_app(app) != "ftm":
            continue
        lang_code = app.get("langCode")
        if not lang_code:
            continue
        if lang_code not in seen_lang_codes:
            seen_lang_codes[lang_code] = app

    for lang_code, app in seen_lang_codes.items():
        title: str = app.get("title", f"Curious Reader {lang_code}")
        icon_href: str = app.get("appIconUrl", "")
        navigation.append(
            {
                "href": f"{base_out_url}/grades/{lang_code}.json",
                "title": title.replace("Feed The Monster", "Curious Reader").strip(),
                "type": "application/opds+json",
                "alternate": [
                    {
                        "href": f"{base_out_url}/{icon_href}",
                        "rel": "icon",
                        "type": "image/png",
                        "title": title.replace("Feed The Monster", "Curious Reader").strip(),
                    }
                ],
            }
        )

    opds = {
        "metadata": {"title": "Curious Reader"},
        "links": [
            {
                "rel": "self",
                "href": f"{base_out_url}/opds.json",
                "type": "application/opds+json",
            }
        ],
        "navigation": navigation,
    }
    write_json(out_path, opds)


def detect_right_to_left(ftm_root: Path, slug: str) -> bool:
    config_path = ftm_root / slug / f"ftm_{slug}.json"
    if not config_path.exists():
        return False
    try:
        cfg = read_json(config_path)
        return bool(cfg.get("RightToLeft", False))
    except Exception:
        return False


def detect_ftm_lesson_count(ftm_root: Path, slug: str) -> Optional[int]:
    """Return number of lessons for this FTM language by counting Levels in config.

    If config is missing or malformed, returns None.
    """
    config_path = ftm_root / slug / f"ftm_{slug}.json"
    if not config_path.exists():
        return None
    try:
        cfg = read_json(config_path)
        levels = cfg.get("Levels")
        if isinstance(levels, list) and len(levels) > 0:
            # Prefer the maximum LevelNumber + 1, falling back to length
            max_level_num: Optional[int] = None
            for level in levels:
                if isinstance(level, dict):
                    meta = level.get("LevelMeta")
                    if isinstance(meta, dict):
                        num = meta.get("LevelNumber")
                        if isinstance(num, int):
                            max_level_num = num if max_level_num is None else max(max_level_num, num)
            if max_level_num is not None:
                # LevelNumber appears 0-based in configs; count is max + 1
                return max_level_num + 1
            return len(levels)
        return None
    except Exception:
        return None


def list_audio_urls_for_ftm(base_out_url: str, ftm_root: Path, slug: str) -> List[str]:
    audios_dir = ftm_root / slug / "audios"
    urls: List[str] = []
    if not audios_dir.exists():
        return urls
    for file in sorted(audios_dir.iterdir()):
        if not file.is_file():
            continue
        if file.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg"}:
            continue
        urls.append(f"{base_out_url}/assets/cr_lang/{slug}/audios/{file.name}")
    return urls


def list_audio_urls_for_assessment(base_out_url: str, assess_root: Path, dataset: str) -> List[str]:
    ds_dir = assess_root / dataset
    urls: List[str] = []
    if not ds_dir.exists():
        return urls
    for file in sorted(ds_dir.iterdir()):
        if not file.is_file():
            continue
        if file.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg"}:
            continue
        urls.append(f"{base_out_url}/assets/data/audio/{dataset}/{file.name}")
    return urls


def build_ftm_lesson_manifest(
    *,
    base_out_url: str,
    ftm_slug: str,
    lang_code: str,
    lesson_id: int,
    icon_rel_path: str,
    right_to_left: bool,
    audio_urls: List[str],
) -> Dict[str, Any]:
    modified = now_iso8601()
    icon_abs_url = f"{base_out_url}/{icon_rel_path}"
    open_access_by_slug = f"https://curiousreader-respect-ftm.web.app/?lang={ftm_slug}&lesson_id={lesson_id}"
    open_access_by_code = f"https://curiousreader-respect-ftm.web.app/?lang={lang_code}&lesson_id={lesson_id}"

    resources: List[Dict[str, Any]] = [
        {
            "type": "image/png",
            "href": icon_abs_url,
            "properties": {"width": 128, "height": 128},
        }
    ]
    for url in audio_urls:
        resources.append({"href": url, "type": "audio/mpeg" if url.lower().endswith(".mp3") else "audio/wav"})

    return {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org",
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": str(lesson_id),
            "author": "Curious Reader",
            "identifier": open_access_by_slug,
            "language": lang_code,
            "modified": modified,
            "published": modified,
            "description": f"Interactive learning lesson: {lesson_id}",
            "subject": ["Education", "Learning"],
            "readingProgression": "rtl" if right_to_left else "ltr",
        },
        "links": [
            {
                "rel": "self",
                "href": f"{base_out_url}/lessons/cr_lang/ftm_{lang_code}_{lesson_id}.json",
                "type": "application/webpub+json",
            },
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": open_access_by_slug,
                "type": "text/html",
            },
        ],
        "images": [
            {"href": icon_abs_url, "type": "image/png", "height": 128, "width": 128}
        ],
        "readingOrder": [
            {
                "type": "text/html",
                "href": open_access_by_code,
                "title": str(lesson_id),
            }
        ],
        "resources": resources,
    }


def build_assessment_manifest(
    *,
    base_out_url: str,
    dataset: str,
    title: str,
    lang_code: str,
    icon_rel_path: str,
    audio_urls: List[str],
) -> Dict[str, Any]:
    modified = now_iso8601()
    icon_abs_url = f"{base_out_url}/{icon_rel_path}"
    open_access = f"https://curiousreader-respect-assessment.web.app/?lesson_id={dataset}"

    resources: List[Dict[str, Any]] = [
        {
            "type": "image/png",
            "href": icon_abs_url,
            "properties": {"width": 128, "height": 128},
        }
    ]
    for url in audio_urls:
        resources.append({"href": url, "type": "audio/mpeg" if url.lower().endswith(".mp3") else "audio/wav"})

    return {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org",
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": title,
            "author": "Curious Reader",
            "identifier": open_access,
            "language": lang_code,
            "modified": modified,
            "published": modified,
            "description": f"Interactive learning lesson: {title}",
            "subject": ["Education", "Learning"],
            "readingProgression": "ltr",
        },
        "links": [
            {
                "rel": "self",
                "href": f"{base_out_url}/lessons/data/{dataset}.json",
                "type": "application/webpub+json",
            },
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": open_access,
                "type": "text/html",
            },
        ],
        "images": [
            {"href": icon_abs_url, "type": "image/png", "height": 128, "width": 128}
        ],
        "readingOrder": [
            {"type": "text/html", "href": open_access, "title": title}
        ],
        "resources": resources,
    }


def build_story_manifest(
    *,
    base_out_url: str,
    book_name: str,
    title: str,
    lang_code: str,
    icon_rel_path: str,
) -> Dict[str, Any]:
    modified = now_iso8601()
    icon_abs_url = f"{base_out_url}/{icon_rel_path}"
    open_access = f"https://curiousreader-respect-story.web.app/?lesson_id={book_name}"

    return {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org",
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": title,
            "author": "Curious Reader",
            "identifier": open_access,
            "language": lang_code,
            "modified": modified,
            "published": modified,
            "description": f"Interactive learning lesson: {title}",
            "subject": ["Education", "Learning"],
            "readingProgression": "ltr",
        },
        "links": [
            {
                "rel": "self",
                "href": f"{base_out_url}/lessons/book/{book_name}.json",
                "type": "application/webpub+json",
            },
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": open_access,
                "type": "text/html",
            },
        ],
        "images": [
            {"href": icon_abs_url, "type": "image/png", "height": 128, "width": 128}
        ],
        "readingOrder": [
            {"type": "text/html", "href": open_access, "title": title}
        ],
        "resources": [
            {
                "type": "image/png",
                "href": icon_abs_url,
                "properties": {"width": 128, "height": 128},
            }
        ],
    }


def generate(
    base_dir: Path,
    base_out_url: str,
    ftm_lessons_count: int,
) -> None:
    # Determine the public directory. Prefer the provided base_dir if it already
    # points to a public folder (contains web-apps or manifest), otherwise look
    # for a nested public folder.
    public_candidates: List[Path] = [
        base_dir,
        base_dir / "public",
        base_dir.parent / "public",
    ]
    public_dir: Path = base_dir
    for candidate in public_candidates:
        if (candidate / "web-apps").exists() or (candidate / "manifest.json").exists():
            public_dir = candidate
            break

    # Resolve inputs and outputs relative to public folder
    web_apps_root = public_dir / "web-apps"
    ftm_root = web_apps_root / "ftm"
    assessment_root = web_apps_root / "assessment"

    # languages.json may live alongside public (project root) or inside public
    lang_candidates: List[Path] = [
        public_dir / "languages.json",
        public_dir.parent / "languages.json",
        base_dir / "languages.json",
    ]
    languages_path: Optional[Path] = next((p for p in lang_candidates if p.exists()), None)
    if languages_path is None:
        raise FileNotFoundError(
            f"Missing languages.json. Checked: {', '.join(str(p) for p in lang_candidates)}"
        )

    languages_data = read_json(languages_path)
    web_apps: List[Dict[str, Any]] = languages_data.get("web_apps", [])

    # 1) OPDS top-level feed
    build_opds_feed(base_out_url, web_apps, public_dir / "opds.json")

    # 2) FTM lessons + grades per language
    ftm_apps_by_code: Dict[str, Dict[str, Any]] = {}
    for app in web_apps:
        if classify_web_app(app) != "ftm":
            continue
        code = app.get("langCode")
        if not code:
            continue
        ftm_apps_by_code[code] = app

    for lang_code, app in ftm_apps_by_code.items():
        icon_rel = app.get("appIconUrl", "")
        slug = parse_query_param(app.get("appUrl", ""), "cr_lang") or app.get("languageInEnglishName", lang_code).lower()
        right_to_left = detect_right_to_left(ftm_root, slug)
        audio_urls = list_audio_urls_for_ftm(base_out_url, ftm_root, slug)

        # Determine lessons count from FTM config Levels; fallback to provided default
        detected_count = detect_ftm_lesson_count(ftm_root, slug)
        lessons_count = detected_count if detected_count is not None else ftm_lessons_count

        # Build lessons
        for lesson_id in range(1, lessons_count + 1):
            lesson_manifest = build_ftm_lesson_manifest(
                base_out_url=base_out_url,
                ftm_slug=slug,
                lang_code=lang_code,
                lesson_id=lesson_id,
                icon_rel_path=icon_rel,
                right_to_left=right_to_left,
                audio_urls=audio_urls,
            )
            lesson_out_path = public_dir / f"lessons/cr_lang/ftm_{lang_code}_{lesson_id}.json"
            write_json(lesson_out_path, lesson_manifest)

        # Build grades feed for this language
        publications: List[Dict[str, Any]] = []
        for lesson_id in range(1, lessons_count + 1):
            publications.append(
                {
                    "metadata": {
                        "title": str(lesson_id),
                        "author": "Curious Reader",
                        "identifier": f"https://curiousreader-respect-ftm.web.app/?lang={slug}&lesson_id={lesson_id}",
                        "language": lang_code,
                        "modified": now_iso8601(),
                    },
                    "links": [
                        {
                            "rel": "self",
                            "href": f"{base_out_url}/lessons/cr_lang/ftm_{lang_code}_{lesson_id}.json",
                            "type": "application/webpub+json",
                        },
                        {
                            "rel": "http://opds-spec.org/acquisition/open-access",
                            "href": f"https://curiousreader-respect-ftm.web.app/?lang={slug}&lesson_id={lesson_id}",
                            "type": "text/html",
                        },
                    ],
                    "images": [
                        {
                            "href": f"{base_out_url}/{icon_rel}",
                            "type": "image/png",
                            "height": 128,
                            "width": 128,
                        }
                    ],
                }
            )

        # Append assessment publications for this language
        for assess_app in web_apps:
            if classify_web_app(assess_app) != "assessment":
                continue
            if assess_app.get("langCode") != lang_code:
                continue
            app_url = assess_app.get("appUrl", "")
            dataset = parse_query_param(app_url, "data")
            if not dataset:
                continue
            assess_icon_rel = assess_app.get("appIconUrl", "appIcons/assessment_icon_prod.png")
            assess_title = assess_app.get("title", f"Assessment {dataset}")
            publications.append(
                {
                    "metadata": {
                        "title": assess_title,
                        "author": "Curious Reader",
                        "identifier": f"https://curiousreader-respect-assessment.web.app/?lesson_id={dataset}",
                        "language": lang_code,
                        "modified": now_iso8601(),
                    },
                    "links": [
                        {
                            "rel": "self",
                            "href": f"{base_out_url}/lessons/data/{dataset}.json",
                            "type": "application/webpub+json",
                        },
                        {
                            "rel": "http://opds-spec.org/acquisition/open-access",
                            "href": f"https://curiousreader-respect-assessment.web.app/?lesson_id={dataset}",
                            "type": "text/html",
                        },
                    ],
                    "images": [
                        {
                            "href": f"{base_out_url}/{assess_icon_rel}",
                            "type": "image/png",
                            "height": 128,
                            "width": 128,
                        }
                    ],
                }
            )

        # Append storybook publications for this language
        for story_app in web_apps:
            if classify_web_app(story_app) != "story":
                continue
            if story_app.get("langCode") != lang_code:
                continue
            story_url = story_app.get("appUrl", "")
            book_name = parse_query_param(story_url, "book")
            if not book_name:
                continue
            story_icon_rel = story_app.get("appIconUrl", "appIcons/ftm_generic.png")
            title_raw = story_app.get("title", book_name)
            story_title = title_raw.replace("Curious Reader ", "").strip()
            publications.append(
                {
                    "metadata": {
                        "title": story_title,
                        "author": "Curious Reader",
                        "identifier": f"https://curiousreader-respect-story.web.app/?lesson_id={book_name}",
                        "language": lang_code,
                        "modified": now_iso8601(),
                    },
                    "links": [
                        {
                            "rel": "self",
                            "href": f"{base_out_url}/lessons/book/{book_name}.json",
                            "type": "application/webpub+json",
                        },
                        {
                            "rel": "http://opds-spec.org/acquisition/open-access",
                            "href": f"https://curiousreader-respect-story.web.app/?lesson_id={book_name}",
                            "type": "text/html",
                        },
                    ],
                    "images": [
                        {
                            "href": f"{base_out_url}/{story_icon_rel}",
                            "type": "image/png",
                            "height": 128,
                            "width": 128,
                        }
                    ],
                }
            )

        grades_feed = {
            "metadata": {"title": app.get("title", f"Feed The Monster {lang_code}")},
            "links": [
                {
                    "rel": "self",
                    "href": f"{base_out_url}/grades/{lang_code}.json",
                    "type": "application/opds+json",
                }
            ],
            "publications": publications,
        }
        write_json(public_dir / f"grades/{lang_code}.json", grades_feed)

    # 3) Assessment lessons (data/*)
    for app in web_apps:
        if classify_web_app(app) != "assessment":
            continue
        app_url = app.get("appUrl", "")
        dataset = parse_query_param(app_url, "data")
        if not dataset:
            continue
        icon_rel = app.get("appIconUrl", "appIcons/assessment_icon_prod.png")
        lang_code = app.get("langCode", "")
        title = app.get("title", f"Assessment {dataset}")
        audio_urls = list_audio_urls_for_assessment(base_out_url, assessment_root, dataset)
        manifest = build_assessment_manifest(
            base_out_url=base_out_url,
            dataset=dataset,
            title=title,
            lang_code=lang_code,
            icon_rel_path=icon_rel,
            audio_urls=audio_urls,
        )
        write_json(public_dir / f"lessons/data/{dataset}.json", manifest)

    # 4) Story lessons (book/*)
    for app in web_apps:
        if classify_web_app(app) != "story":
            continue
        app_url = app.get("appUrl", "")
        book_name = parse_query_param(app_url, "book")
        if not book_name:
            continue
        icon_rel = app.get("appIconUrl", "appIcons/ftm_generic.png")
        lang_code = app.get("langCode", "")
        title_raw = app.get("title", book_name)
        # Drop the leading "Curious Reader " if present to keep parity with examples
        title = title_raw.replace("Curious Reader ", "").strip()
        manifest = build_story_manifest(
            base_out_url=base_out_url,
            book_name=book_name,
            title=title,
            lang_code=lang_code,
            icon_rel_path=icon_rel,
        )
        write_json(public_dir / f"lessons/book/{book_name}.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Curious Reader OPDS and lesson manifests")
    parser.add_argument(
        "--base-dir",
        default=str((Path(__file__).resolve().parent / "public")),
        help=(
            "Base directory aligned to the public folder. The script will read from "
            "<public>/web-apps and write generated files into <public> (default: ./public)."
        ),
    )
    parser.add_argument(
        "--base-out-url",
        default="https://curious-reader.web.app",
        help="Public base URL used in generated hrefs (default: https://curious-reader.web.app)",
    )
    parser.add_argument(
        "--ftm-lessons",
        type=int,
        default=int(os.environ.get("FTM_LESSONS", "100")),
        help="Number of FTM lessons per language to generate (default: 100)",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    generate(base_dir, args.base_out_url.rstrip("/"), args.ftm_lessons)


if __name__ == "__main__":
    main()

