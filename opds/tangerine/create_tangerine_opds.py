import os
import json
import re
import datetime

# === CONFIGURATION ===
BASE_URL = "https://ibiza-stage-tangerine-dev.web.app"  # Replace with your actual Firebase Hosting domain
OUTPUT_DIR = "public"
GROUPS_DIR = os.path.join(OUTPUT_DIR, "groups")
FORMS_DIR = os.path.join(OUTPUT_DIR, "forms")
os.makedirs(GROUPS_DIR, exist_ok=True)
os.makedirs(FORMS_DIR, exist_ok=True)

# === READ LINKS FROM data.txt ===
groups = {}
all_form_links = set()

with open("data.txt", "r", encoding="utf-8") as f:
    for line in f:
        url = line.strip()
        if not url:
            continue
        # Extract group and form IDs using regex
        match = re.search(r"group-([a-f0-9\-]+)/form-([a-f0-9\-]+)", url)
        if match:
            group_id = f"group-{match.group(1)}"
            form_id = f"form-{match.group(2)}"
            groups.setdefault(group_id, []).append((form_id, url))
            all_form_links.add((form_id, url))

# === GENERATE OPDS.JSON ===
opds = {
    "metadata": {
        "title": "Tangerine Surveys"
    },
    "links": [
        {
            "rel": "self",
            "href": f"{BASE_URL}/opds.json",
            "type": "application/opds+json"
        }
    ],
    "navigation": []
}

for group_id in groups:
    opds["navigation"].append({
        "href": f"{BASE_URL}/groups/{group_id}.json",
        "title": f"Survey Group {group_id[6:14]}",
        "type": "application/opds+json",
        "alternate": [
            {
                "href": f"{BASE_URL}/icon.png",
                "rel": "icon",
                "type": "image/png",
                "title": "Tangerine"
            }
        ]
    })

os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(os.path.join(OUTPUT_DIR, "opds.json"), "w", encoding="utf-8") as f:
    json.dump(opds, f, indent=2)

print("Generated opds.json with group navigation and icons.")

# === GENERATE GROUP JSON FILES (CHIMPLE OPDS FORMAT) ===
for group_id, form_tuples in groups.items():
    group_json = {
        "metadata": {
            "title": f"Survey Group {group_id[6:14]}"
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}/groups/{group_id}.json",
                "type": "application/opds+json"
            }
        ],
        "publications": []
    }
    for form_id, link in form_tuples:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        form_json_url = f"{BASE_URL}/forms/{form_id}.json"
        form_identifier = form_json_url[:-5] if form_json_url.endswith('.json') else form_json_url
        group_json["publications"].append({
            "metadata": {
                "title": f"Form {form_id[5:]}" if form_id.startswith('form-') else f"Form {form_id}",
                "author": "Tangerine",
                "identifier": form_identifier,
                "language": "en",
                "modified": now
            },
            "links": [
                {
                    "rel": "self",
                    "href": form_json_url,
                    "type": "application/webpub+json"
                },
                {
                    "rel": "http://opds-spec.org/acquisition/open-access",
                    "href": link,
                    "type": "text/html"
                }
            ],
            "images": [
                {
                    "href": f"{BASE_URL}/icon.png",
                    "type": "image/png",
                    "height": 128,
                    "width": 128
                }
            ]
        })
    with open(os.path.join(GROUPS_DIR, f"{group_id}.json"), "w", encoding="utf-8") as f:
        json.dump(group_json, f, indent=2)

print("Generated group JSON files in public/groups/ (Chimple OPDS format)")

# === GENERATE FORM JSON FILES (CHIMPLE LESSON FORMAT) ===
for form_id, link in all_form_links:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    form_json_url = f"{BASE_URL}/forms/{form_id}.json"
    form_identifier = form_json_url[:-5] if form_json_url.endswith('.json') else form_json_url
    form_json = {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org"
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": f"Form {form_id[5:]}" if form_id.startswith('form-') else f"Form {form_id}",
            "author": "Tangerine",
            "identifier": form_identifier,
            "language": "en",
            "modified": now,
            "published": now,
            "description": "Tangerine survey form",
            "subject": ["Survey", "Data Collection"],
            "readingProgression": "ltr"
        },
        "links": [
            {
                "rel": "self",
                "href": form_json_url,
                "type": "application/webpub+json"
            },
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": link,
                "type": "text/html"
            }
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
                "href": link,
                "title": f"Form {form_id[5:]}" if form_id.startswith('form-') else f"Form {form_id}"
            }
        ],
        "resources": [
            {
                "type": "image/png",
                "href": f"{BASE_URL}/icon.png",
                "properties": {
                    "width": 128,
                    "height": 128
                }
            }
        ]
    }
    with open(os.path.join(FORMS_DIR, f"{form_id}.json"), "w", encoding="utf-8") as f:
        json.dump(form_json, f, indent=2)

print("Generated form JSON files in public/forms/ (Chimple lesson format)")