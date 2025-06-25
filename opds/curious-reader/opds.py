import json
import os
import urllib.parse
from datetime import datetime, timezone

# Paths
LANGUAGES_INPUT = 'languages.json'
OPDS_OUTPUT = os.path.join('public', 'opds.json')
GRADES_DIR = os.path.join('public', 'grades')
LESSONS_DIR = os.path.join('public', 'lessons')

TYPE_TO_FOLDER = {
    'cr_lang': 'ftm',
    'book': 'story',
    'data': 'assessment',
}
GITHUB_BASE = 'https://curious-reader.web.app/zips/'

# Load files
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_type_and_value(app_url):
    parsed = urllib.parse.urlparse(app_url)
    query = urllib.parse.parse_qs(parsed.query)
    if 'data' in query:
        return 'data', query['data'][0]
    elif 'cr_lang' in query:
        return 'cr_lang', query['cr_lang'][0]
    elif 'book' in query:
        return 'book', query['book'][0]
    else:
        return 'app', os.path.basename(parsed.path)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def generate_grade_catalog(apps, lang_code):
    publications = []
    for app in apps:
        type_key, value = parse_type_and_value(app["appUrl"])
        pub = {
            "metadata": {
                "title": app["title"],
                "author": app.get("author", "Curious Reader"),
                "identifier": f"https://curious-reader.web.app/id/{type_key}/{value}",
                "language": lang_code,
                "modified": datetime.now(timezone.utc).isoformat()
            },
            "links": [
                {
                    "rel": "self",
                    "href": f"https://curious-reader.web.app/lessons/{type_key}/{value}.json",
                    "type": "application/webpub+json"
                },
                {
                    "rel": "http://opds-spec.org/acquisition/open-access",
                    "href": f"https://curious-reader.web.app/download/{type_key}/{value}.html",
                    "type": "text/html"
                }
            ],
            "images": [
                {
                    "href": "https://curious-reader.web.app/" + app["appIconUrl"],
                    "type": "image/png",
                    "height": 128,
                    "width": 128
                }
            ]
        }
        publications.append(pub)
    catalog = {
        "metadata": {
            "title": apps[0]["title"] if apps else lang_code
        },
        "links": [
            {
                "rel": "self",
                "href": f"https://curious-reader.web.app/grades/{lang_code}.json",
                "type": "application/opds+json"
            }
        ],
        "publications": publications
    }
    return catalog

def generate_lesson_json(pub, type_key, value):
    icon = pub["images"][0]["href"] if pub["images"] else ""
    title = pub["metadata"].get("title", "Lesson")
    download_url = f"https://curious-reader.web.app/download/{type_key}/{value}.html"
    folder = TYPE_TO_FOLDER.get(type_key)
    zip_href = f"{GITHUB_BASE}{folder}/{value}.zip" if folder else ""
    lesson_json = {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org"
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": title,
            "author": pub["metadata"].get("author", "Curious Reader"),
            "identifier": pub["metadata"].get("identifier"),
            "language": pub["metadata"].get("language"),
            "modified": pub["metadata"].get("modified"),
            "published": pub["metadata"].get("modified"),
            "description": f"Interactive learning lesson: {title}",
            "subject": ["Education", "Learning"],
            "readingProgression": "ltr"
        },
        "links": pub["links"],
        "images": [
            {
                "href": icon,
                "type": "image/png",
                "height": 128,
                "width": 128
            }
        ],
        "readingOrder": [
            {
                "type": "text/html",
                "href": download_url,
                "title": title
            }
        ],
        "resources": [
            {
                "type": "image/png",
                "href": icon,
                "properties": {
                    "width": 128,
                    "height": 128
                }
            },
            {
                "type": "application/zip",
                "href": zip_href,
                "properties": {
                    "contains": [
                        "application/xhtml+xml",
                        "text/css",
                        "image/*"
                    ]
                }
            }
        ]
    }
    return lesson_json

def main():
    languages = load_json(LANGUAGES_INPUT)

    new_opds = {
        "metadata": {
            "title": "Curious Reader",
        },
        "links": [
            {
                "rel": "self",
                "href": "https://curious-reader.web.app/opds.json",
                "type": "application/opds+json"
            }
        ],
        "navigation": []
    }

    ensure_dir(GRADES_DIR)
    ensure_dir(LESSONS_DIR)
    langcode_to_apps = {}
    for app in languages.get("web_apps", []):
        lang_code = app.get("langCode")
        if not lang_code:
            continue
        langcode_to_apps.setdefault(lang_code, []).append(app)

    for lang_code, apps in langcode_to_apps.items():
        # Use the first app for the navigation entry
        app = apps[0]
        nav_entry = {
            "href": f"grades/{lang_code}.json",
            "title": app["title"],
            "type": "application/opds+json",
            "alternate": [
                {
                    "href": app["appIconUrl"],
                    "rel": "icon",
                    "type": "image/png",
                    "title": app["title"]
                }
            ]
        }
        new_opds["navigation"].append(nav_entry)

        # Generate the sub-catalog for this language with all apps for this langCode
        grade_catalog = generate_grade_catalog(apps, lang_code)
        grade_path = os.path.join(GRADES_DIR, f"{lang_code}.json")
        with open(grade_path, 'w', encoding='utf-8') as f:
            json.dump(grade_catalog, f, ensure_ascii=False, indent=2)

        # Generate lessons for each publication
        for pub in grade_catalog["publications"]:
            # Parse type and value from identifier or links
            identifier = pub["metadata"].get("identifier", "")
            # identifier is like https://curious-reader.web.app/id/<type>/<value>
            parts = identifier.split("/id/")
            if len(parts) == 2:
                type_value = parts[1]
                if "/" in type_value:
                    type_key, value = type_value.split("/", 1)
                else:
                    type_key, value = "app", type_value
            else:
                type_key, value = "app", identifier
            lesson_json = generate_lesson_json(pub, type_key, value)
            lesson_dir = os.path.join(LESSONS_DIR, type_key)
            ensure_dir(lesson_dir)
            lesson_path = os.path.join(lesson_dir, f"{value}.json")
            with open(lesson_path, 'w', encoding='utf-8') as f:
                json.dump(lesson_json, f, ensure_ascii=False, indent=2)

    # Save the new opds.json
    with open(OPDS_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(new_opds, f, ensure_ascii=False, indent=2)
    print(f"Generated {OPDS_OUTPUT}, sub-catalogs in {GRADES_DIR}, and lessons in {LESSONS_DIR}")

if __name__ == "__main__":
    main()
