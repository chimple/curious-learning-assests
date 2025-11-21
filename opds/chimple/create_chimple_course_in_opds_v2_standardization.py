import os
import json
from datetime import datetime, timezone
from openpyxl import load_workbook
from urllib.parse import urljoin

# Configuration
EXCEL_FILE = 'Respect Course Latest All Course Details From dashboard.xlsx'
# EXCEL_FILE = 'sheet (1).xlsx'

BASE_URL = 'https://chimple-respectify.web.app/'  # Base URL for your OPDS catalog
TYPE_OPDS = 'application/opds+json'
PUB_TYPE = 'application/opds-publication+json'
SKIP_SHEETS = {'All Courses', 'Sheet4', 'Sheet5'}  # adjust as needed

# Output folders
OUTPUT_DIR = 'public'
GRADE_DIR = os.path.join(OUTPUT_DIR, 'grades')
LESSON_DIR = os.path.join(OUTPUT_DIR, 'lessons')
ICONS_DIR = os.path.join(OUTPUT_DIR, 'images', 'icons')

os.makedirs(GRADE_DIR, exist_ok=True)
os.makedirs(LESSON_DIR, exist_ok=True)

def get_image_path(cocos_lesson_code):
    """Get the image path for a lesson, fallback to default if not found"""
    if not cocos_lesson_code or cocos_lesson_code == 'default':
        return 'default.png'
    
    # Try to find the image with the cocos_lesson_code
    possible_extensions = ['.png', '.png', '.png', '.webp']
    for ext in possible_extensions:
        image_path = os.path.join(ICONS_DIR, f"{cocos_lesson_code}{ext}")
        if os.path.exists(image_path):
            return f"{cocos_lesson_code}{ext}"
    
    # If not found, return default
    return 'default.png'

# Load workbook
print(f"Loading workbook: {EXCEL_FILE}")
wb = load_workbook(EXCEL_FILE, read_only=True, data_only=True)

# --- Gather navigation and learning units ---
navigation = []
learning_units = []
for sheet_name in wb.sheetnames:
    if sheet_name in SKIP_SHEETS:
        continue
    filename = sheet_name.replace(' ', '').lower() + '.json'
    
    # Determine icon based on grade type
    if 'english' in sheet_name.lower():
        icon = BASE_URL + 'images/icons/en0000.png'
    elif 'maths' in sheet_name.lower():
        icon = BASE_URL + 'images/icons/maths0000.png'
    elif 'digital' in sheet_name.lower():
        icon = BASE_URL + 'images/icons/puzzle0000.png'
    else:
        icon = BASE_URL + 'images/icons/default.png'
    
    nav_obj = {
        'href': BASE_URL + 'grades/' + filename,
        'title': sheet_name,
        'type': TYPE_OPDS,
        'alternate': [
            {
                'href': icon,
                'rel': "icon",
                'type': "image/png",
                'title': sheet_name
            }
        ]
    }
    navigation.append(nav_obj)
    learning_units.append({
        "id": filename.replace('.json', ''),
        "title": sheet_name,
        "href": nav_obj['href'],
        "type": TYPE_OPDS
    })

# --- Generate opds.json (OPDS catalog) ---
opds_catalog = {
    "metadata": {"title": "Chimple Learning"},
    "links": [{"rel": "self", "href": urljoin(BASE_URL, 'opds.json'), "type": TYPE_OPDS}],
    "navigation": navigation
}
with open(os.path.join(OUTPUT_DIR, 'opds.json'), 'w', encoding='utf-8') as f:
    json.dump(opds_catalog, f, indent=2)
print(f"Generated opds.json with {len(navigation)} grades.")

# --- Generate index.json (RESPECT App Manifest) ---
respect_manifest = {
    "name": {"en-US": "Chimple Learning"},
    "description": {"en-US": "A collection of interactive learning units for children."},
    "license": "MIT",
    "website": BASE_URL,
    "icon": BASE_URL + "icon.webp",
    "learningUnits": BASE_URL + "opds.json",
    "defaultLaunchUri": navigation[0]['href'] if navigation else BASE_URL,
    "android": {
        "packageId": "org.chimple.cuba",
        "stores": ["https://play.google.com/store/apps/details?id=org.chimple.cuba"]
    },
    "web": {
        "url": BASE_URL
    }
}
with open(os.path.join(OUTPUT_DIR, 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(respect_manifest, f, indent=2)
print(f"Generated index.json as RESPECT App Manifest.")

def create_lesson_manifest(lesson_data, lesson_id, title, asset_link):
    """Create a lesson manifest in Readium Web Publication Manifest format"""
    # Fix date format to RFC 3339 (UTC timezone)
    current_time = datetime.now(timezone.utc).isoformat()
    
    # Get image path
    cocos_lesson_code = str(lesson_data.get('cocos_lesson_code', '')).strip() or lesson_data.get('id') or 'default'
    image_filename = get_image_path(cocos_lesson_code)
    print(f"Using image for lesson {lesson_id}: {image_filename}")

    
    # Create Readium Web Publication Manifest
    lesson_manifest = {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org"
        ],
        "metadata": {
            "@type": "https://schema.org/Book",
            "title": title,
            "author": "Chimple",
            "identifier": f"https://chimple.cc/?activity_id={lesson_id}",
            "language": "en",
            "modified": current_time,
            "published": current_time,
            "description": f"Interactive learning lesson: {title}",
            "subject": ["Education", "Learning"],
            "readingProgression": "ltr"
        },
        "links": [
            {
                "rel": "self",
                "href": f"https://chimple-respectify.web.app/lessons/{lesson_id}.json",
                "type": "application/webpub+json"
            },
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": f"https://chimple.cc/?activity_id={lesson_id}",
                "type": "text/html"
            }
        ],
        "images": [
            {
                "href": f"https://chimple-respectify.web.app/images/icons/{image_filename}",
                "type": "image/png",
                "height": 128,
                "width": 128
            }
        ],

        "readingOrder": [
            {
                "type": "text/html",
                "href": f"https://chimple.cc/?activity_id={lesson_id}",
                "title": title
            }
        ],
        "resources": [
            {
                "type": "image/png",
                "href": f"https://chimple-respectify.web.app/images/icons/{image_filename}",
                "properties": {
                    "width": 128,
                    "height": 128
                }
            },
            {
                "type": "application/zip",
                "href": asset_link,
                "properties": {
                    "contains": ["application/xhtml+xml", "text/css", "image/*"]
                }
            }
        ]
    }
    
    return lesson_manifest

# --- Process sheets ---
for sheet_name in wb.sheetnames:
    if sheet_name in SKIP_SHEETS:
        continue
    
    print(f"\nProcessing sheet: {sheet_name}")
    ws = wb[sheet_name]
    grade_key = sheet_name.replace(' ', '').lower()
    grade_file = f"{grade_key}.json"
    publications = []
    
    headers = [str(cell.value).strip() if cell.value else '' for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    print(f"Headers (columns) fetched from sheet '{sheet_name}': {headers}")
    for i, h in enumerate(headers):
        print(f"Header {i}: '{h}' (len={len(h)})")

    row_count = 0
    valid_lessons = 0
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_count += 1
        data = dict(zip(headers, row))
        data = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        if row_count <= 5:
            print(f"Row {row_count} keys: {list(data.keys())}")
            print(f"Row {row_count} values: {list(data.values())}")
            print(f"Row {row_count} data: {data}")
        lesson_id = str(data.get('lesson_id', '')).strip()
        if not isinstance(lesson_id, str):
            print(f"Skipping row {row_count}: lesson_id is not a string: {lesson_id}")
            continue
        if not lesson_id or lesson_id.lower() == 'nan':
            print(f"Skipping row {row_count}: Missing lesson_id (value: '{lesson_id}')")
            continue
        title = str(
            data.get('title') or
            data.get('title ') or
            data.get('lesson_name') or
            ''
        ).strip()
        print(f"Row {row_count}: lesson_id={lesson_id}, title='{title}'")
            
        asset = str(
            data.get('Asset Link') or
            data.get('Asset L') or
            ''
        ).strip()
        cocos_lesson_code = str(data.get('cocos_lesson_code', '')).strip() or data.get('id') or 'default'

        if not title or title.lower() == 'nan':
            title = f"Lesson {lesson_id}"
            print(f"Row {row_count}: Using default title: {title}")
            
        if not asset or asset.lower() == 'nan':
            print(f"Skipping row {row_count}: Missing asset link")
            continue

        valid_lessons += 1
        print(f"Processing lesson {lesson_id}: {title}")

        lesson_filename = f"{lesson_id}.json"

        lesson_manifest = create_lesson_manifest(data, lesson_id, title, asset)

        with open(os.path.join(LESSON_DIR, lesson_filename), 'w', encoding='utf-8') as lf:
            json.dump(lesson_manifest, lf, indent=2)
        print(f"Generated lesson manifest: {lesson_filename}")

        # Get image path for OPDS
        image_filename = get_image_path(cocos_lesson_code)

        # For OPDS catalog, create a simplified publication entry
        publication = {
            'metadata': {
                'title': lesson_manifest['metadata']['title'],
                'author': 'Chimple',
                'identifier': f"https://chimple.cc/?activity_id={lesson_id}",
                'language': 'en',
                'modified': lesson_manifest['metadata']['modified']
            },
            'links': [
                {
                    'rel': 'self',
                    'href': f"https://chimple-respectify.web.app/lessons/{lesson_id}.json",
                    'type': 'application/webpub+json'
                },
                {
                    'rel': 'http://opds-spec.org/acquisition/open-access',
                    'href': f"https://chimple.cc/?activity_id={lesson_id}",
                    'type': 'text/html'
                }
            ],
            'images': [
                {
                    'href': f"https://chimple-respectify.web.app/images/icons/{image_filename}",
                    'type': 'image/png',
                    'height': 128,
                    'width': 128
                }
            ]
        }
        
        cocos_chapter_code = str(data.get('cocosChapterCode', '')).strip() or data.get('cocos_chapter_code', '')
        if cocos_chapter_code and cocos_chapter_code.lower() != 'nan':
             publication['metadata']['subject'] = [
                {
                    'name': title,
                    'scheme': "https://chimple.cc/curriculum",
                    'code': cocos_chapter_code
                }
            ]
        publications.append(publication)

    grade_json = {
        'metadata': {'title': f"{sheet_name}"},
        'links': [{'rel': 'self', 'href': urljoin(BASE_URL + "/grades/", grade_file), 'type': TYPE_OPDS}],
        'publications': publications
    }
    with open(os.path.join(GRADE_DIR, grade_file), 'w', encoding='utf-8') as gf:
        json.dump(grade_json, gf, indent=2)
    print(f"Generated {grade_file} with {len(publications)} valid lessons (skipped {row_count - valid_lessons} rows)")

print("\nAll files generated successfully!")
