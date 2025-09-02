#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import time
import mimetypes
from urllib.parse import urljoin
import urllib.request
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from urllib.parse import quote as urlquote
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


def is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"}
    except Exception:
        return False


def guess_mime_type_from_url(url: str) -> str:
    # Try standard mapping first
    mime, _ = mimetypes.guess_type(url)
    if mime:
        return mime
    # Common fallbacks
    lowered = url.lower()
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".mp3"):
        return "audio/mpeg"
    if lowered.endswith(".wav"):
        return "audio/wav"
    if lowered.endswith(".m4a"):
        return "audio/mp4"
    if lowered.endswith(".ogg"):
        return "audio/ogg"
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".wasm"):
        return "application/wasm"
    if lowered.endswith(".map"):
        return "application/json"
    return "application/octet-stream"


def encode_path_segments(path: str) -> str:
    """Percent-encode each segment of a URL path, preserving slashes.

    Example: "img/survey/hot plate.jpeg" -> "img/survey/hot%20plate.jpeg"
    """
    try:
        parts = [p for p in path.split("/")]
        return "/".join(urlquote(p, safe="") for p in parts)
    except Exception:
        return path


def _static_discover_from_html(page_url: str, timeout_ms: int, verbose: bool) -> List[str]:
    urls: List[str] = []
    try:
        with urllib.request.urlopen(page_url, timeout=timeout_ms / 1000.0) as resp:
            if resp.status >= 400:
                return urls
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "javascript" not in content_type:
                return urls
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return urls

    # Naive extraction of src/href references
    for token in ["src=\"", "href=\""]:
        start = 0
        while True:
            idx = html.find(token, start)
            if idx == -1:
                break
            idx += len(token)
            end = html.find("\"", idx)
            if end == -1:
                break
            raw = html[idx:end]
            start = end + 1
            try:
                abs_url = urljoin(page_url, raw)
                if is_http_url(abs_url):
                    urls.append(abs_url)
            except Exception:
                pass

    # Deduplicate and cap
    seen: set[str] = set()
    deduped: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped[:500]


def _collect_media_paths_from_json(node: Any, out: List[str]) -> None:
    """Recursively collect media file paths from a story content.json structure.

    Captures strings that look like relative media paths such as:
    - images/file-....jpg/png/webp/gif/svg
    - audios/file-....mp3/wav/m4a/ogg
    - videos/file-....mp4/webm/ogg
    The function is resilient to different H5P schemas (slides/chapters/etc.).
    """
    try:
        media_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".webm"}
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "path" and isinstance(v, str):
                    # Typical H5P file object: { file: { path: "images/..." } }
                    if any(v.lower().endswith(ext) for ext in media_exts):
                        out.append(v.lstrip("/"))
                else:
                    _collect_media_paths_from_json(v, out)
        elif isinstance(node, list):
            for item in node:
                _collect_media_paths_from_json(item, out)
        elif isinstance(node, str):
            # Fallback: capture plain strings that look like media relative paths
            if "/" in node and any(node.lower().endswith(ext) for ext in media_exts):
                out.append(node.lstrip("/"))
    except Exception:
        return


def list_story_resources_from_content(web_apps_root: Path, book_name: str, assets_base_url: str) -> List[str]:
    """Parse content.json for a storybook and return absolute URLs for media resources.

    URLs are constructed under the assets domain (e.g., https://curious-reader.web.app)
    in the form:
      <assets_base_url>/web-apps/story/{book_name}/content/<relative_path>
    """
    content_dir = web_apps_root / "story" / book_name / "content"
    content_json_path = content_dir / "content.json"
    if not content_json_path.exists():
        return []
    try:
        data = read_json(content_json_path)
    except Exception:
        return []

    rel_paths: List[str] = []
    _collect_media_paths_from_json(data, rel_paths)
    # Deduplicate while preserving order
    seen: set[str] = set()
    urls: List[str] = []
    prefix = f"{assets_base_url.rstrip('/')}/web-apps/story/{book_name}/content/"
    for rel in rel_paths:
        rel_norm = encode_path_segments(rel.replace("\\", "/"))
        if rel_norm not in seen:
            seen.add(rel_norm)
            urls.append(prefix + rel_norm)
    return urls


try:
    from tqdm import tqdm
except Exception:
    # Provide a minimal no-op tqdm fallback
    class tqdm:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def update(self, *args, **kwargs):
            pass
        def set_postfix(self, *args, **kwargs):
            pass

def crawl_resources_for_url(
    open_access_url: str,
    base_out_url: str,
    save_path: Optional[Path] = None,
    timeout_ms: int = 15000,
    max_items: int = 1000,
    verbose: bool = False,
) -> Tuple[List[str], List[str]]:
    """Best-effort dynamic discovery of network resources used by a web app.

    Uses Playwright to load the page and record network responses.
    If `save_path` is provided, attempts to save response bodies to disk.
    Shows progress using tqdm progress bars.

    Returns a tuple:
    - A list of all discovered absolute resource URLs.
    - A list of absolute URLs for resources that were successfully saved locally
      (prefixed with `base_out_url`).
    """
    print(f"\n{'='*50}\nStarting resource crawl for: {open_access_url}\n{'='*50}")
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        if verbose:
            print(f"[crawl] Playwright not available; using static discovery for {open_access_url}")
        static_urls = _static_discover_from_html(open_access_url, timeout_ms, verbose)
        return (static_urls, [])

    collected_urls: List[str] = []
    saved_local_urls: List[str] = []
    seen_urls: set[str] = set()
    
    # Initialize progress bars
    with tqdm(desc="Crawling resources", unit="res") as pbar_outer:
        def update_progress():
            pbar_outer.set_postfix({
                'found': len(collected_urls),
                'saved': len(saved_local_urls)
            })
            pbar_outer.update(1)

    def add_url(u: str) -> None:
        if not is_http_url(u):
            return
        if u in seen_urls:
            return
        seen_urls.add(u)
        collected_urls.append(u)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        # Track the last time we observed any network response so we can
        # avoid closing the browser while responses are still arriving.
        last_event_time = time.time()

        def handle_response(resp):
            try:
                url = resp.url
                if not is_http_url(url):
                    return
                add_url(url)
                update_progress()
                # Mark activity
                nonlocal last_event_time
                last_event_time = time.time()

                # If save_path is specified, try to save the response
                if save_path and resp.ok:
                    parsed_url = urlparse(url)
                    # Sanitize path components
                    host = parsed_url.netloc.replace(":", "_")
                    rel_path = parsed_url.path.lstrip("/")
                    if not rel_path:
                        # Use a default name for root documents
                        rel_path = "index.html"

                    # Create a file path, ensuring it's within the save_path
                    local_path = save_path.joinpath(host, rel_path).resolve()
                    if not str(local_path).startswith(str(save_path.resolve())):
                        if verbose:
                            print(f"  [crawl] Skipping save for unsafe path: {rel_path}")
                        return

                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        body = resp.body()
                    except Exception as e:
                        body = None
                        if verbose:
                            print(f"  [crawl] Playwright body() failed for {url}: {e}. Falling back to direct download...")
                        # Fallback: try direct HTTP GET (best-effort; some opaque responses may still fail)
                        try:
                            with urllib.request.urlopen(url, timeout=max(5, min(30, int(timeout_ms/1000)))) as r:
                                # Only save successful responses
                                if getattr(r, 'status', 200) < 400:
                                    body = r.read()
                        except Exception as e2:
                            if verbose:
                                print(f"  [crawl] Fallback download failed for {url}: {e2}")
                    try:
                        if body:
                            local_path.write_bytes(body)
                            # Keep the original URL instead of creating a local one
                            saved_local_urls.append(url)
                            if verbose:
                                print(f"  [crawl] Saved {url} -> {local_path}")
                    except Exception as e3:
                        if verbose:
                            print(f"  [crawl] Failed to write body for {url}: {e3}")

            except Exception as e:
                if verbose:
                    print(f"  [crawl] Error handling response: {e}")

        page.on("response", handle_response)

        try:
            with tqdm(desc="Loading page", bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}'):
                page.goto(open_access_url, wait_until="networkidle", timeout=timeout_ms)
        except Exception as e:
            try:
                print(f"\n[WARNING] Initial page load failed, retrying with DOMContentLoaded: {e}")
                with tqdm(desc="Retrying page load", bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}'):
                    page.goto(open_access_url, timeout=timeout_ms)
                    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                print(f"\n[ERROR] Page load failed for {open_access_url}: {e}")
                return (collected_urls, saved_local_urls)

        # Wait for additional resources with progress
        print("\nWaiting for additional resources...")
        with tqdm(desc="Waiting", total=timeout_ms//1000, bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}') as pbar_wait:
            for _ in range(timeout_ms // 1000):
                time.sleep(1)
                pbar_wait.update(1)

        # Grace period: keep the page open a bit longer if network activity
        # is still occurring, up to a small cap, to reduce "context closed" races.
        grace_cap_seconds = 10
        start_grace = time.time()
        while (time.time() - last_event_time) < 2 and (time.time() - start_grace) < grace_cap_seconds:
            time.sleep(0.5)
        # One last attempt to ensure network is idle before closing.
        try:
            page.wait_for_load_state("networkidle", timeout=min(5000, timeout_ms))
        except Exception:
            pass

        browser.close()
        print("\n" + "="*50)
        print(f"Crawl completed for: {open_access_url}")
        print(f"Total resources found: {len(collected_urls)}")
        print(f"Resources saved: {len(saved_local_urls)}")
        print("="*50 + "\n")

    # Limit and return
    return (collected_urls[:max_items], saved_local_urls[:max_items])


def _collect_files_from_tree(node: Dict[str, Any], out: List[str]) -> None:
    """Recursively collect file 'path' entries from a tree object.

    The input is expected to follow the structure in
    `assessment_common_assests.json`, with keys: name, type, path, children.
    """
    try:
        ntype = node.get("type")
        if ntype == "file":
            p = node.get("path")
            if isinstance(p, str) and p:
                out.append(p.lstrip("/"))
        elif ntype == "folder":
            for child in node.get("children", []) or []:
                _collect_files_from_tree(child, out)
    except Exception:
        # Be resilient to malformed nodes
        return


def load_assessment_common_assets(assets_base_url: str, base_dir: Path) -> List[str]:
    """Load common assessment assets from assessment_common_assests.json and
    map them to absolute URLs under /web-apps/assessment/.

    Returns a list of absolute URLs suitable for inclusion in manifest resources.
    """
    json_path = base_dir / "assessment_common_assests.json"
    if not json_path.exists():
        return []
    try:
        tree = read_json(json_path)
    except Exception:
        return []

    file_paths: List[str] = []
    _collect_files_from_tree(tree, file_paths)

    urls: List[str] = []
    # For assessment common assets, they are expected to be served from the domain root
    # e.g., https://curiousreader-respect-assessment.web.app/img/... (strip leading 'dist/')
    prefix = f"{assets_base_url.rstrip('/')}/"
    for rel in file_paths:
        # Ensure forward slashes and trim leading ./ if any
        rel_norm = rel.replace("\\", "/").lstrip("./")
        if rel_norm.startswith("dist/"):
            rel_norm = rel_norm[len("dist/"):]
        rel_norm = encode_path_segments(rel_norm)
        urls.append(prefix + rel_norm)
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


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
        # Use the new domain for all audio URLs
        urls.append(f"{base_out_url}/lang/{slug}/audios/{file.name}")
    return urls


def list_audio_urls_for_assessment(base_out_url: str, assess_root: Path, dataset: str) -> List[str]:
    """Extract all audio URLs from the web-apps folder for the given assessment.
    
    Scans the web-apps/assessment/{dataset} directory and its subdirectories
    to find all audio files, including those in the audioAsset folder.
    """
    urls: List[str] = []
    
    # Define the base directories to scan for audio files
    base_dirs = [
        assess_root.parent / "web-apps" / "assessment" / dataset,
        assess_root.parent / "web-apps" / "assessment" / "audioAsset",
        assess_root.parent / "web-apps" / "assessment" / "audios"
    ]
    
    # Audio file extensions to include
    audio_extensions = {".mp3", ".wav", ".m4a", ".ogg"}
    
    # Scan each directory for audio files
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
            
        # Walk through all subdirectories
        for file_path in base_dir.rglob('*'):
            if not file_path.is_file():
                continue
                
            # Check if the file has an audio extension
            if file_path.suffix.lower() in audio_extensions:
                # Get the relative path from the web-apps directory
                rel_path = file_path.relative_to(assess_root.parent / "web-apps")
                # Convert Windows paths to forward slashes for URLs
                rel_path_str = str(rel_path).replace('\\', '/')
                # Add the base URL and path
                urls.append(f"{base_out_url}/web-apps/{rel_path_str}")
    
    # Also check the assessment's own directory
    if (assess_root / dataset).exists():
        for file in (assess_root / dataset).iterdir():
            if not file.is_file():
                continue
            if file.suffix.lower() in audio_extensions:
                urls.append(f"{base_out_url}/web-apps/assessment/{dataset}/{file.name}")
    

    
    # Remove duplicates and sort
    return sorted(list(set(urls)))


def list_common_assets(base_out_url: str, base_dir: Path) -> List[str]:
    """List common assets from /public/assets/images and /public/assets/audios directories."""
    urls: List[str] = []
    public_dir = base_dir / "public"
    
    # Define the common directories relative to public/
    common_dirs = [
        (public_dir / "assets" / "images", [".png", ".jpg", ".jpeg", ".gif", ".webp"]),
        (public_dir / "assets" / "audios", [".mp3", ".wav", ".m4a", ".ogg"])
    ]
    
    for dir_path, extensions in common_dirs:
        if not dir_path.exists():
            if base_dir.name == 'public':  # If we're already in public directory
                dir_path = base_dir / "assets" / dir_path.name
                if not dir_path.exists():
                    continue
            else:
                continue
                
        for file in sorted(dir_path.iterdir()):
            if not file.is_file():
                continue
            if file.suffix.lower() not in extensions:
                continue
            # Get path relative to public directory
            rel_path = file.relative_to(public_dir)
            urls.append(f"{base_out_url}/{rel_path}")
    
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
    additional_resource_urls: Optional[List[str]] = None,
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
    common_assets = list_common_assets(base_out_url, Path(__file__).parent)
    for url in audio_urls + common_assets:
        resources.append({"type": guess_mime_type_from_url(url), "href": url})
    if additional_resource_urls:
        for url in additional_resource_urls:
            # Avoid duplicating icon and audio urls
            if url == icon_abs_url or url in (r.get("href") for r in resources):
                continue
            resources.append({"href": url, "type": guess_mime_type_from_url(url)})

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
    additional_resource_urls: Optional[List[str]] = None,
    assets_base_url: Optional[str] = None,
    self_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    modified = now_iso8601()
    # For assessment, allow overriding the asset base domain (e.g., curious-reader.web.app)
    assets_base = (assets_base_url or base_out_url).rstrip("/")
    icon_abs_url = f"{assets_base}/{icon_rel_path}"
    open_access = f"https://curiousreader-respect-assessment.web.app/?lesson_id={dataset}"

    resources: List[Dict[str, Any]] = [
        {
            "type": "image/png",
            "href": icon_abs_url,
            "properties": {"width": 128, "height": 128},
        }
    ]
    # common_assets = list_common_assets(base_out_url, Path(__file__).parent)
    for url in audio_urls:
        resources.append({"type": guess_mime_type_from_url(url), "href": url})
    if additional_resource_urls:
        for url in additional_resource_urls:
            if url == icon_abs_url or url in (r.get("href") for r in resources):
                continue
            resources.append({"href": url, "type": guess_mime_type_from_url(url)})

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
                # Allow self link to be served from a different base (e.g., curious-reader.web.app)
                "href": f"{(self_base_url or base_out_url).rstrip('/')}/lessons/data/{dataset}.json",
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
    additional_resource_urls: Optional[List[str]] = None,
    assets_base_url: Optional[str] = None,
    self_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    modified = now_iso8601()
    assets_base = (assets_base_url or base_out_url).rstrip("/")
    icon_abs_url = f"{assets_base}/{icon_rel_path}"
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
                "href": f"{(self_base_url or base_out_url).rstrip('/')}/lessons/book/{book_name}.json",
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
        ] + (
            [
                {"href": url, "type": guess_mime_type_from_url(url)}
                for url in (additional_resource_urls or [])
                if url != icon_abs_url
            ]
        ),
    }


def generate(
    base_dir: str | Path,
    base_out_url: str,
    ftm_lessons_count: int,
    crawl_resources_enabled: bool,
    crawl_timeout_ms: int,
    verbose: bool,
    skip_ftm: bool = False,
    skip_assessment: bool = False,
    skip_book: bool = False,
) -> None:
    # Ensure base_dir is a Path object and resolve it
    base_dir = Path(str(base_dir)).resolve()
    if verbose:
        print(f"Base directory: {base_dir}")
        print(f"Base output URL: {base_out_url}")
        print(f"Skip FTM: {skip_ftm}")
        print(f"Skip Assessment: {skip_assessment}")
        print(f"Skip Book: {skip_book}")
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
    if verbose:
        print(f"Web apps root: {web_apps_root}")
    
    ftm_root = web_apps_root / "ftm"
    assessment_root = web_apps_root / "assessment"
    
    # Ensure required directories exist
    if not web_apps_root.exists():
        raise FileNotFoundError(f"Web apps directory not found: {web_apps_root}")
    if not assessment_root.exists():
        print(f"Warning: Assessment directory not found: {assessment_root}", file=sys.stderr)
    if not skip_ftm and not ftm_root.exists():
        print(f"Warning: FTM directory not found: {ftm_root}", file=sys.stderr)

    # languages.json may live in several locations - check them all
    lang_candidates: List[Path] = [
        public_dir / "languages.json",
        public_dir.parent / "languages.json",
        base_dir / "languages.json",
        Path.cwd() / "languages.json",
    ]
    if verbose:
        print("\nSearching for languages.json in:", ", ".join(f'"{p}"' for p in lang_candidates))
    languages_path: Optional[Path] = next((p for p in lang_candidates if p.exists()), None)
    if languages_path is None:
        error_msg = f"Missing languages.json. Checked:\n" + "\n".join(f"- {p}" for p in lang_candidates)
        raise FileNotFoundError(error_msg)
    
    if verbose:
        print(f"Found languages.json at: {languages_path}")

    if verbose:
        print(f"Using public dir: {public_dir}")
        print(f"Using languages.json: {languages_path}")
        print(f"Base out URL: {base_out_url}")
    languages_data = read_json(languages_path)
    web_apps: List[Dict[str, Any]] = languages_data.get("web_apps", [])

    # 1) OPDS top-level feed
    build_opds_feed(base_out_url, web_apps, public_dir / "opds.json")

    # 2) FTM lessons + grades per language (skip if --skip-ftm is set)
    if skip_ftm:
        if verbose:
            print("\n[FTM] Skipping FTM lesson generation as requested")
    else:
        ftm_apps_by_code: Dict[str, Dict[str, Any]] = {}
        for app in web_apps:
            if classify_web_app(app) != "ftm":
                continue
            code = app.get("langCode")
            if not code:
                continue
            ftm_apps_by_code[code] = app
    
    # Iterate over FTM apps only when not skipping; avoid chaining .items() on dict_items
    iter_items = ftm_apps_by_code.items() if not skip_ftm else []
    for lang_code, app in iter_items:
        icon_rel = app.get("appIconUrl", "")
        slug = parse_query_param(app.get("appUrl", ""), "cr_lang") or app.get("languageInEnglishName", lang_code).lower()
        right_to_left = detect_right_to_left(ftm_root, slug)
        audio_urls = list_audio_urls_for_ftm(base_out_url, ftm_root, slug)

        # Determine lessons count from FTM config Levels; fallback to provided default
        detected_count = detect_ftm_lesson_count(ftm_root, slug)
        lessons_count = detected_count if detected_count is not None else ftm_lessons_count

        if verbose:
            print(f"\n[FTM] {lang_code} ({slug}) lessons={lessons_count} rtl={right_to_left}")
        # Build lessons. If crawling is enabled, crawl once per language (lesson 1) and reuse
        per_language_saved_urls: List[str] = []
        if crawl_resources_enabled:
            save_path = public_dir / "external_resources"
            open_access_for_resources = (
                f"https://curiousreader-respect-ftm.web.app/?lang={slug}&lesson_id=1"
            )
            _, per_language_saved_urls = crawl_resources_for_url(
                open_access_url=open_access_for_resources,
                base_out_url=base_out_url,
                save_path=save_path,
                timeout_ms=crawl_timeout_ms,
                verbose=verbose,
            )
            if verbose:
                print(f"  Crawled and saved FTM shared resources: {len(per_language_saved_urls)}")

        for lesson_id in range(1, lessons_count + 1):
            lesson_manifest = build_ftm_lesson_manifest(
                base_out_url=base_out_url,
                ftm_slug=slug,
                lang_code=lang_code,
                lesson_id=lesson_id,
                icon_rel_path=icon_rel,
                right_to_left=right_to_left,
                audio_urls=audio_urls,
                additional_resource_urls=per_language_saved_urls,
            )
            lesson_out_path = public_dir / f"lessons/cr_lang/ftm_{lang_code}_{lesson_id}.json"
            write_json(lesson_out_path, lesson_manifest)
            if verbose:
                print(f"  Wrote {lesson_out_path}")

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
        if not skip_assessment:
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
        if not skip_book:
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
    if not skip_assessment:
        # Domains:
        # - Common assets (img/css/etc.) stay on assessment domain
        # - Web app assets under /web-apps/assessment/* must use curious-reader.web.app
        assessment_common_base_url = "https://curiousreader-respect-assessment.web.app"
        web_apps_assets_base_url = "https://curious-reader.web.app"
        # Load common assessment assets once (uses assessment domain)
        common_assessment_urls = load_assessment_common_assets(assessment_common_base_url, Path(__file__).parent)

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
            # Remap any /web-apps/assessment URLs to the curious-reader domain
            audio_urls = [
                u.replace(f"{base_out_url.rstrip('/')}/web-apps/assessment/", f"{web_apps_assets_base_url}/web-apps/assessment/")
                if u.startswith(f"{base_out_url.rstrip('/')}/web-apps/assessment/") else
                (
                    u.replace(f"{assessment_common_base_url}/web-apps/assessment/", f"{web_apps_assets_base_url}/web-apps/assessment/")
                    if u.startswith(f"{assessment_common_base_url}/web-apps/assessment/") else u
                )
                for u in audio_urls
            ]
            saved_assess_urls: List[str] = []
            if crawl_resources_enabled:
                save_path = public_dir / "external_resources"
                open_access_assess = f"https://curiousreader-respect-assessment.web.app/?lesson_id={dataset}"
                _, saved_assess_urls = crawl_resources_for_url(
                    open_access_url=open_access_assess,
                    base_out_url=base_out_url,
                    save_path=save_path,
                    timeout_ms=crawl_timeout_ms,
                    verbose=verbose,
                )
            if verbose and crawl_resources_enabled:
                print(f"\n[ASSESS] dataset={dataset} lang={lang_code} saved_urls={len(saved_assess_urls)}")
            # Merge common assessment assets with any crawled URLs
            # Ensure any crawled /web-apps/assessment URLs also use the curious-reader domain
            saved_assess_urls = [
                (
                    u.replace(f"{base_out_url.rstrip('/')}/web-apps/assessment/", f"{web_apps_assets_base_url}/web-apps/assessment/")
                    if u.startswith(f"{base_out_url.rstrip('/')}/web-apps/assessment/")
                    else u
                )
                for u in (saved_assess_urls or [])
            ]
            addl_urls = list(dict.fromkeys(saved_assess_urls + common_assessment_urls))
            manifest = build_assessment_manifest(
                base_out_url=base_out_url,
                dataset=dataset,
                title=title,
                lang_code=lang_code,
                icon_rel_path=icon_rel,
                audio_urls=audio_urls,
                additional_resource_urls=addl_urls,
                assets_base_url=web_apps_assets_base_url,
                self_base_url=web_apps_assets_base_url,
            )
            write_json(public_dir / f"lessons/data/{dataset}.json", manifest)
            if verbose:
                print(f"  Wrote {public_dir / f'lessons/data/{dataset}.json'}")

    # 4) Story lessons (book/*)
    if not skip_book:
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
            saved_story_urls: List[str] = []
            # Extract static media URLs directly from content.json using curious-reader assets domain
            story_assets_base_url = "https://curious-reader.web.app"
            content_urls = list_story_resources_from_content(web_apps_root, book_name, story_assets_base_url)
            if crawl_resources_enabled:
                save_path = public_dir / "external_resources"
                open_access_story = f"https://curiousreader-respect-story.web.app/?lesson_id={book_name}"
                _, saved_story_urls = crawl_resources_for_url(
                    open_access_url=open_access_story,
                    base_out_url=base_out_url,
                    save_path=save_path,
                    timeout_ms=crawl_timeout_ms,
                    verbose=verbose,
                )
            if verbose and crawl_resources_enabled:
                print(f"\n[STORY] book={book_name} lang={lang_code} saved_urls={len(saved_story_urls)}")
            # Merge content.json derived URLs with any crawled URLs, de-duping
            merged_urls: List[str] = list(dict.fromkeys((content_urls or []) + (saved_story_urls or [])))
            manifest = build_story_manifest(
                base_out_url=base_out_url,
                book_name=book_name,
                title=title,
                lang_code=lang_code,
                icon_rel_path=icon_rel,
                additional_resource_urls=merged_urls,
                assets_base_url=story_assets_base_url,
                self_base_url=story_assets_base_url,
            )
            write_json(public_dir / f"lessons/book/{book_name}.json", manifest)
            if verbose:
                print(f"  Wrote {public_dir / f'lessons/book/{book_name}.json'}")


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
        default="https://curiousreader-respect-ftm.web.app",
        help="Public base URL used in generated hrefs (default: https://curiousreader-respect-ftm.web.app)",
    )
    parser.add_argument(
        "--ftm-lessons",
        type=int,
        default=int(os.environ.get("FTM_LESSONS", "100")),
        help="Number of FTM lessons per language to generate (default: 100)",
    )
    parser.add_argument(
        "--crawl-resources",
        action="store_true",
        help=(
            "If set, attempts to launch Playwright Chromium to load each open-access URL "
            "and capture network resources, embedding them into the manifest resources."
        ),
    )
    parser.add_argument(
        "--crawl-timeout-ms",
        type=int,
        default=int(os.environ.get("CRAWL_TIMEOUT_MS", "15000")),
        help="Timeout in milliseconds for each resource crawl (default: 15000)",
    )
    parser.add_argument(
        "--skip-ftm",
        action="store_true",
        help="Skip generation of FTM lesson manifests",
    )
    parser.add_argument(
        "--skip-assessment",
        action="store_true",
        help="Skip generation of assessment manifests",
    )
    parser.add_argument(
        "--skip-book",
        action="store_true",
        help="Skip generation of story book manifests",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress while generating (paths, writes, crawl counts)",
    )
    args = parser.parse_args()

    try:
        base_dir = Path(args.base_dir).resolve()
        generate(
            base_dir=base_dir,
            base_out_url=args.base_out_url.rstrip("/"),
            ftm_lessons_count=args.ftm_lessons,
            crawl_resources_enabled=args.crawl_resources,
            crawl_timeout_ms=args.crawl_timeout_ms,
            verbose=args.verbose,
            skip_ftm=args.skip_ftm,
            skip_assessment=args.skip_assessment,
            skip_book=args.skip_book,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

