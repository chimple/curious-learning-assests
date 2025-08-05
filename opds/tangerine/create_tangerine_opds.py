import os
import json
import re
import datetime

# === CONFIGURATION ===
BASE_URL = "https://ibiza-stage-tangerine-dev.web.app"  # Replace with your actual Firebase Hosting domain
OUTPUT_DIR = "public"
GROUPS_DIR = os.path.join(OUTPUT_DIR, "groups")
os.makedirs(GROUPS_DIR, exist_ok=True)

# === READ LINKS FROM data.txt ===
groups = {}

with open("data.txt", "r", encoding="utf-8") as f:
    for line in f:
        url = line.strip()
        if not url:
            continue
        # Extract group and form IDs using regex
        match = re.search(r"group-([a-f0-9\-]+)/form-([a-f0-9\-]+)", url)
        if match:
            group_id = f"group-{match.group(1)}"
            groups.setdefault(group_id, []).append(url)

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
for group_id, form_links in groups.items():
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
    for link in form_links:
        # Extract form ID for title
        match = re.search(r"form-([a-f0-9\-]+)", link)
        form_id = match.group(1) if match else "unknown"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        group_json["publications"].append({
            "metadata": {
                "title": f"Form {form_id}",
                "author": "Tangerine",
                "identifier": link,
                "language": "en",
                "modified": now
            },
            "links": [
                {
                    "rel": "self",
                    "href": link,
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