import os
import json
import re

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