import os
import json
import requests
import datetime
import re
from urllib.parse import quote, urljoin

# === CONFIGURATION ===
BASE_URL = "https://ibiza-stage-tangerine-dev.web.app" 
DATA_SOURCE_BASE = "https://tangerinestaging.ustadmobile.com"
GROUP_LIST_URL = f"{DATA_SOURCE_BASE}/nest/group/list"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InVzZXIxIiwicGVybWlzc2lvbnMiOnsiZ3JvdXBQZXJtaXNzaW9ucyI6W10sInNpdGV3aWRlUGVybWlzc2lvbnMiOlsiY2FuX2NyZWF0ZV9ncm91cCIsImNhbl92aWV3X3VzZXJzX2xpc3QiLCJjYW5fY3JlYXRlX3VzZXJzIiwiY2FuX2VkaXRfdXNlcnMiLCJjYW5fbWFuYWdlX3VzZXJzX3NpdGVfd2lkZV9wZXJtaXNzaW9ucyJdfSwiaWF0IjoxNzY3NzgwMTU3LCJleHAiOjE3Njc3ODM3NTcsImlzcyI6IlRhbmdlcmluZSIsInN1YiI6InVzZXIxIn0.c_L5kXae-hj3xVJujaekc67MHhEYQsaLKieNEIRQdYw"

OUTPUT_DIR = "public"
GROUPS_DIR = os.path.join(OUTPUT_DIR, "groups")
FORMS_DIR = os.path.join(OUTPUT_DIR, "forms")

os.makedirs(GROUPS_DIR, exist_ok=True)
os.makedirs(FORMS_DIR, exist_ok=True)

def safe_filename(name):
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in ('-', '_')]).strip()

def fetch_json(url):
    try:
        headers = {
            "authorization": f"{AUTH_TOKEN}"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def create_publication_entry(form_data, group_id):
    # Support both 'formId' (from group list) and 'id' (from forms.json)
    form_id = form_data.get('id') or form_data.get('formId') 
    if not form_id:
        return None

    # Title strategy: 
    # 1. Try 'title' from forms.json (if available)
    # 2. Try fetching app-config.json
    # 3. Fallback to form_id
    title = form_data.get('title', form_id)
    
    # Fetch details for authoritative title
    config_url = f"{DATA_SOURCE_BASE}/releases/prod/online-survey-apps/{group_id}/{form_id}/assets/app-config.json"
    config = fetch_json(config_url)
    
    if not config:
        return None
        
    if 'appName' in config:
        title = config['appName']
    
    # Direct launch URL as per user instruction
    # https://tangerinestaging.ustadmobile.com/releases/prod/online-survey-apps/{group_id}/{form_id}/#/form/{form_id}
    launch_url = f"{DATA_SOURCE_BASE}/releases/prod/online-survey-apps/{group_id}/{form_id}/#/form/{form_id}"
    
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Determine status for subject
    # forms.json might not have 'published' field, default to "Published" if using forms.json as it lists active forms?
    # Or check if it exists. 
    # In forms.json, we observed 'hideProfile', etc. It usually lists updated forms.
    # We will assume "Published" if not specified, or "Unpublished" if explicitly false.
    is_published = form_data.get('published', True) # Defaulting to true for forms.json items
    status_subject = "Published" if is_published else "Unpublished"
    
    # Create the internal manifest file (optional, but good for standardization)
    form_manifest_filename = f"{form_id}.json"
    # Build resources list
    resources = []
    
    # Add main source file and scan for assets
    src = form_data.get('src')
    if src:
        # Resolve form.html URL
        # Based on analysis: {DATA_SOURCE_BASE}/app/{group_id}/assets/{src_cleaned}
        # where src starts with ./assets/...
        
        cleaned_src = src.lstrip('./') if src.startswith('./') else src
        
        # Note: Debugging showed that even though src is 'assets/...', the app endpoint needs '/assets/' prefix
        # constructing .../app/{group_id}/assets/assets/... which worked.
        asset_base_path = f"{DATA_SOURCE_BASE}/app/{group_id}/assets"
        form_html_url = f"{asset_base_path}/{cleaned_src}"
        
        # Add form.html itself
        resources.append({
            "href": form_html_url,
            "type": "text/html"
        })
        
        # Fetch and scan form.html for other assets
        try:
            headers = {"authorization": AUTH_TOKEN}
            res = requests.get(form_html_url, headers=headers, timeout=10)
            if res.status_code == 200:
                content = res.text
                # Regex for common media types
                extensions = ['mp3', 'ogg', 'wav', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm']
                found_assets = set()
                # Pattern to capture src="..." or href="..."
                # We simply look for filenames ending in extensions to be robust against quoting styles
                for ext in extensions:
                    # Capture full relative path if possible
                    matches = re.findall(r'[\w\-\./]+\.' + ext, content)
                    for m in matches:
                        found_assets.add(m)

                for asset_path in sorted(found_assets):
                    # Resolve relative to form.html
                    asset_url = urljoin(form_html_url, asset_path)
                    
                    # Guess mime type simple
                    mime_type = "application/octet-stream"
                    if asset_path.endswith('.png'): mime_type = "image/png"
                    elif asset_path.endswith('.jpg') or asset_path.endswith('.jpeg'): mime_type = "image/jpeg"
                    elif asset_path.endswith('.mp3'): mime_type = "audio/mpeg"
                    elif asset_path.endswith('.ogg'): mime_type = "audio/ogg"
                    
                    resources.append({
                        "href": asset_url,
                        "type": mime_type
                    })
            else:
                print(f"Warning: Could not fetch form.html for scanning: {res.status_code}")
        except Exception as e:
            print(f"Error scanning form assets: {e}")

    form_manifest_url = f"{BASE_URL}/forms/{form_manifest_filename}"
    
    manifest = {
        "@context": ["https://readium.org/webpub-manifest/context.jsonld", "https://schema.org"],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": title,
            "author": "Tangerine",
            "identifier": launch_url,
            "language": "en",
            "modified": now,
            "published": now,
            "description": f"Tangerine Form: {title}",
            "subject": ["Survey", "Tangerine", status_subject],
            "readingProgression": "ltr"
        },
        "links": [
            {"rel": "self", "href": form_manifest_url, "type": "application/webpub+json"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": launch_url, "type": "text/html"}
        ],
        "images": [
            {
                "href": f"{BASE_URL}/icon.png",
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

    # Return the publication object for the feed (Group Feed entry)
    # The group feed entry should also be aligned if necessary, but typically sticking to OPDS feed entry standard is safe.
    # We will keep the group feed entry similar to before but consistent with metadata.
    return {
        "metadata": {
            "title": title,
            "author": "Tangerine",
            "identifier": launch_url,
            "modified": now,
            "language": "en",
            "subject": [
                {
                    "name": status_subject,
                    "code": status_subject.lower()
                }
            ],
            "description": f"Tangerine Form: {title}"
        },
        "links": [
            {"rel": "self", "href": form_manifest_url, "type": "application/webpub+json"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": launch_url, "type": "text/html"}
        ],
        "images": [
             {
                "href": f"{BASE_URL}/icon.png",
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
        
        # 1. Fetch Forms from forms.json endpoint
        forms_url = f"{DATA_SOURCE_BASE}/app/{group_id}/assets/forms.json"
        forms_list = fetch_json(forms_url)
        
        if forms_list is None:
            print(f"  Warning: Could not fetch forms.json for group {group_id}. Skipping group.")
            continue
            
        all_publications = []
        
        for form in forms_list:
            if form.get('id') == 'about': # Skip the 'about' form/page
                continue
                
            pub_entry = create_publication_entry(form, group_id)
            if pub_entry:
                all_publications.append(pub_entry)
        
        # 2. Create Group Feed (Directly listing publications)
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

        # Add to Main Navigation
        opds_navigation.append({
            "href": f"{url_prefix}/groups/{group_feed_filename}",
            "title": label,
            "type": "application/opds+json",
            "alternate": [
                {
                    "href": f"{url_prefix}/icon.png",
                    "rel": "icon",
                    "type": "image/png",
                    "title": label
                }
            ]
        })

    # 4. Create Main OPDS Feed
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

    # 5. Create Respect App Manifest (manifest.json)
    # Aligned with Chimple's manifest.json structure
    respect_manifest = {
        "name": {
            "en-US": "Tangerine"
        },
        "description": {
            "en-US": "Tangerine is an Android app designed for data collection and assessment."
        },
        "license": "GPL-3.0",
        "website": "https://tangerinecentral.org",
        "icon": f"{url_prefix}/icon.png", 
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
