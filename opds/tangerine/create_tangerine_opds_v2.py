import os
import json
import requests
import datetime
import re
import time
import mimetypes
from urllib.parse import quote, urljoin, urlparse

import shutil
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# === CONFIGURATION ===
BASE_URL = "https://tangerinestaging.ustadmobile.com" 
DATA_SOURCE_BASE = "https://tangerinestaging.ustadmobile.com"
GROUP_LIST_URL = f"{DATA_SOURCE_BASE}/nest/group/list"
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
if not AUTH_TOKEN:
    raise ValueError("AUTH_TOKEN not found. Please set it in the .env file.")

OUTPUT_DIR = "public"
GROUPS_DIR = os.path.join(OUTPUT_DIR, "groups")
FORMS_DIR = os.path.join(OUTPUT_DIR, "forms")

# Icon files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GROUPS_ICON_SRC = os.path.join(SCRIPT_DIR, "groups_icon.png")
FORMS_ICON_SRC = os.path.join(SCRIPT_DIR, "forms_icon.png")
GROUPS_ICON_DEST = "groups_icon.png" 
FORMS_ICON_DEST = "forms_icon.png"

# Ensure output dir exists relative to CWD or Script? 
# The OUTPUT_DIR is defined as "public" earlier, usually relative to CWD.
# Let's keep OUTPUT_DIR relative to CWD as likely intended by original script, 
# but make sure we copy FROM the script dir.

os.makedirs(GROUPS_DIR, exist_ok=True)
os.makedirs(FORMS_DIR, exist_ok=True)

# Copy icons to public dir
if os.path.exists(GROUPS_ICON_SRC):
    shutil.copy(GROUPS_ICON_SRC, os.path.join(OUTPUT_DIR, GROUPS_ICON_DEST))
else:
    print(f"Warning: {GROUPS_ICON_SRC} not found.")

if os.path.exists(FORMS_ICON_SRC):
    shutil.copy(FORMS_ICON_SRC, os.path.join(OUTPUT_DIR, FORMS_ICON_DEST))
else:
    print(f"Warning: {FORMS_ICON_SRC} not found.")

def safe_filename(name):
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in ('-', '_')]).strip()

def fetch_json(url):
    try:
        headers = {
            "authorization": f"{AUTH_TOKEN}"
        }
        # In case we need better headers
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Error: Status {response.status_code} for {url}")
            print(f"Response: {response.text[:200]}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def is_http_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"}
    except Exception:
        return False

def guess_mime_type_from_url(url):
    # Try standard mapping first
    mime, _ = mimetypes.guess_type(url)
    if mime:
        return mime
    # Common fallbacks
    lowered = url.lower()
    if lowered.endswith(".webp"): return "image/webp"
    if lowered.endswith(".mp3"): return "audio/mpeg"
    if lowered.endswith(".wav"): return "audio/wav"
    if lowered.endswith(".m4a"): return "audio/mp4"
    if lowered.endswith(".ogg"): return "audio/ogg"
    if lowered.endswith(".json"): return "application/json"
    if lowered.endswith(".woff2"): return "font/woff2"
    if lowered.endswith(".woff"): return "font/woff"
    if lowered.endswith(".ttf"): return "font/ttf"
    if lowered.endswith(".css"): return "text/css"
    if lowered.endswith(".js"): return "application/javascript"
    return "application/octet-stream"

def _static_discover_from_html(page_url, timeout_ms=10000):
    """Fallback static discovery using requests."""
    print(f"  [Static Discovery] Scanning {page_url}...")
    urls = []
    try:
        headers = {"authorization": AUTH_TOKEN}
        with requests.get(page_url, headers=headers, timeout=timeout_ms/1000.0) as resp:
            if resp.status_code >= 400:
                print(f"  [Static] Failed to fetch {page_url}: {resp.status_code}")
                return None  # Return None to indicate failure
            html = resp.text
    except Exception as e:
        print(f"  [Static] Error fetching {page_url}: {e}")
        return None

    # Naive extraction of src/href references
    # Look for common asset patterns
    patterns = [r'src="([^"]+)"', r'href="([^"]+)"', r'url\(([^)]+)\)']
    
    for pattern in patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            # Clean up url() matches which might have quotes
            raw = match.strip(' "\'')
            if not raw: continue
            
            # Skip obviously non-resource things (like #, mailto:)
            if raw.startswith('#') or raw.startswith('mailto:') or raw.startswith('tel:'):
                continue
                
            try:
                abs_url = urljoin(page_url, raw)
                if is_http_url(abs_url):
                    urls.append(abs_url)
            except Exception:
                pass

    # Deduplicate
    return list(set(urls))

def crawl_resources_for_url(open_access_url, timeout_ms=15000):
    """
    Crawls a URL to discover static resources (JS, CSS, Images, Fonts).
    Uses Playwright if available, otherwise falls back to static HTML analysis.
    Returns None if the page cannot be loaded (e.g. 404).
    """
    print(f"Crawling resources for: {open_access_url}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Warning] Playwright not installed. Falling back to static analysis.")
        return _static_discover_from_html(open_access_url, timeout_ms)

    collected_urls = set()
    found_404 = False
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            def handle_response(resp):
                try:
                    url = resp.url
                    if not is_http_url(url):
                        return
                    collected_urls.add(url)
                except Exception:
                    pass

            page.on("response", handle_response)
            
            try:
                response = page.goto(open_access_url, wait_until="networkidle", timeout=timeout_ms)
                if response and response.status == 404:
                    print(f"  [Playwright] Page returned 404: {open_access_url}")
                    found_404 = True
            except Exception as e:
                print(f"  [Playwright] Page load timeout/error: {e}")
                # Even if it timed out, we might have caught some resources
                # But if checking for 404 is critical, we might want to return None if response is None?
                # For now, let's assume if it fails hard, we might skip it or fallback.
                pass
            
            browser.close()
    except Exception as e:
        print(f"  [Playwright] Critical error: {e}. Falling back to static.")
        return _static_discover_from_html(open_access_url, timeout_ms)
        
    if found_404:
        return None

    print(f"  Found {len(collected_urls)} resources.")
    return list(collected_urls)

def create_publication_entry(form_data, group_id):
    form_id = form_data.get('id') or form_data.get('formId') 
    if not form_id:
        return None

    title = form_data.get('title', form_id)
    
    # Fetch details for authoritative title
    config_url = f"{DATA_SOURCE_BASE}/releases/prod/online-survey-apps/{group_id}/{form_id}/assets/app-config.json"
    config = fetch_json(config_url)
    
    if config and 'appName' in config:
        title = config['appName']
    
    launch_url = f"{DATA_SOURCE_BASE}/releases/prod/online-survey-apps/{group_id}/{form_id}/#/form/{form_id}"
    
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    form_manifest_filename = f"{form_id}.json"
    
    # === RESOURCE DISCOVERY ===
    # Crawl the launch URL to find all resources
    discovered_urls = crawl_resources_for_url(launch_url)
    
    if discovered_urls is None:
        print(f"Skipping form {form_id} because it returned 404 or failed to load.")
        return None
    
    resources = []
    
    # Always include the launch URL itself (the HTML entry point)
    resources.append({
        "href": launch_url,
        "type": "text/html"
    })
    
    # Add discovered resources
    for url in discovered_urls:
        if url == launch_url: continue # Don't duplicate
        
        # Sanitize URL: encode | which causes java.net.URI issues on Android
        url = url.replace('|', '%7C')

        mime_type = guess_mime_type_from_url(url)
        
        # Filter commonly unwanted types if necessary (e.g. tracking pixels)
        # For now, we include everything to ensure offline functionality
        
        resources.append({
            "href": url,
            "type": mime_type
        })
    
    form_manifest_url = f"{BASE_URL}/forms/{form_manifest_filename}"
    
    # Build structured subject per Readium/RESPECT spec
    subjects = {
        "name": "Education: Evaluation & Assessment",
        "scheme": "https://www.bisg.org/#bisac",
        "code": "EDU011000"
    }

    manifest = {
        "@context": ["https://readium.org/webpub-manifest/context.jsonld", "https://schema.org"],
        "metadata": {
            "@type": "https://schema.org/LearningResource",
            "title": title,
            "author": "Tangerine",
            "identifier": launch_url,
            "language": "en",
            "modified": now,
            "published": now,
            "description": f"Tangerine Form: {title}",
            "subject": subjects
        },
        "links": [
            {"rel": "self", "href": form_manifest_url, "type": "application/webpub+json"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": launch_url, "type": "text/html"}
        ],
        "images": [
            {
                "href": f"{BASE_URL}/{FORMS_ICON_DEST}",
                "type": "image/png",
                "height": 128,
                "width": 128
            }
        ],
        "readingOrder": [
            {
                "type": "text/html",
                "href": launch_url,
                "title": title
            }
        ],
        "resources": resources
    }
    
    with open(os.path.join(FORMS_DIR, form_manifest_filename), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    return {
        "metadata": {
            "@type": "https://schema.org/LearningResource",
            "title": title,
            "author": "Tangerine",
            "identifier": launch_url,
            "modified": now,
            "language": "en",
            "subject": subjects,
            "description": f"Tangerine Form: {title}"
        },
        "links": [
            {"rel": "self", "href": form_manifest_url, "type": "application/webpub+json"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": launch_url, "type": "text/html"}
        ],
        "images": [
             {
                "href": f"{BASE_URL}/{FORMS_ICON_DEST}",
                "type": "image/png",
                "height": 128,
                "width": 128
            }
        ]
    }

def main():
    print("Fetching Group List...")
    groups = fetch_json(GROUP_LIST_URL)
    
    if not groups:
        print("API fetch failed. Exiting.")
        return

    opds_navigation = []
    processed_group_ids = set()

    for group in groups:
        group_id = group.get('_id')
        label = group.get('label', group_id)
        
        if not group_id: 
            continue
        
        if group_id in processed_group_ids:
            print(f"Skipping duplicate group: {group_id}")
            continue
            
        processed_group_ids.add(group_id)
            
        print(f"Processing Group: {label} ({group_id})")
        
        forms_url = f"{DATA_SOURCE_BASE}/app/{group_id}/assets/forms.json"
        forms_list = fetch_json(forms_url)
        
        if forms_list is None:
            print(f"  Warning: Could not fetch forms.json for group {group_id}. Skipping group.")
            continue
            
        all_publications = []
        
        for form in forms_list:
            if form.get('id') == 'about':
                continue
                
            pub_entry = create_publication_entry(form, group_id)
            if pub_entry:
                all_publications.append(pub_entry)
        
        if not all_publications:
            print(f"Skipping group {group_id} (no valid forms found).")
            continue

        url_prefix = f"{BASE_URL}"
        
        group_feed_filename = f"{group_id}.json"
        
        group_feed = {
            "metadata": {"title": label},
            "links": [
                {"rel": "self", "href": f"{url_prefix}/groups/{group_feed_filename}", "type": "application/opds+json"}
            ],
            "publications": all_publications
        }
        
        with open(os.path.join(GROUPS_DIR, group_feed_filename), 'w', encoding='utf-8') as f:
            json.dump(group_feed, f, indent=2)

        opds_navigation.append({
            "href": f"{url_prefix}/groups/{group_feed_filename}",
            "title": label,
            "type": "application/opds+json",
            "alternate": [
                {
                    "href": f"{url_prefix}/{GROUPS_ICON_DEST}",
                    "rel": "icon",
                    "type": "image/png",
                    "title": label
                }
            ]
        })

    url_prefix = f"{BASE_URL}"
    root_opds = {
        "metadata": {"title": "Tangerine Groups"},
        "links": [
            {"rel": "self", "href": f"{url_prefix}/opds.json", "type": "application/opds+json"}
        ],
        "navigation": opds_navigation
    }
    
    with open(os.path.join(OUTPUT_DIR, "opds.json"), 'w', encoding='utf-8') as f:
        json.dump(root_opds, f, indent=2)

    respect_manifest = {
        "name": {
            "en-US": "Tangerine"
        },
        "description": {
            "en-US": "Tangerine is an Android app designed for data collection and assessment."
        },
        "license": "GPL-3.0",
        "website": "https://tangerinecentral.org",
        "icon": f"{url_prefix}/{GROUPS_ICON_DEST}", 
        "learningUnits": f"{url_prefix}/opds.json",
        "defaultLaunchUri": f"{url_prefix}/opds.json",
        "android": {
            "packageId": "org.rti.tangerineclientapp",
            "stores": [
                "https://github.com/chimple/tangerine-client-app/tree/apk"
            ],
            "sourceCode": "https://github.com/chimple/tangerine-client-app"
        }
    }
    
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), 'w', encoding='utf-8') as f:
        json.dump(respect_manifest, f, indent=2)
        
    print("Done! OPDS catalog and Respect App Manifest generated.")

if __name__ == "__main__":
    main()
