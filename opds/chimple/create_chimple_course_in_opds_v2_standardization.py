import os
import json
import mimetypes
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from openpyxl import load_workbook
from urllib.parse import urlencode, urljoin, urlsplit

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Configuration
EXCEL_FILE = 'Respect Course Latest All Course Details From dashboard.xlsx'
# EXCEL_FILE = 'sheet (1).xlsx'

BASE_URL = 'https://chimple-respect.web.app/'  # Base URL for your OPDS catalog
TYPE_OPDS = 'application/opds+json'
PUB_TYPE = 'application/opds-publication+json'
DEFAULT_COLLECTION_FILENAME = 'opds.json'
COURSE_CONFIG_FILE = 'chimple_course_config.json'
LANGUAGE_SETTINGS = {
    'English': {
        'code': 'en',
        'locale': 'en-US',
        'catalog_file': 'opds.json',
        'catalog_title': 'Chimple Kids Learning',
        'app_manifest': 'launchable-app.json',
        'app_title': 'Chimple Kids Learning',
        'app_description': 'Interactive learning units for children.',
    },
    'Kannada': {
        'code': 'kn',
        'locale': 'kn-IN',
        'catalog_file': 'opds-kn-IN.json',
        'catalog_title': 'Chimple Kids Learning',
        'app_manifest': 'launchable-app-kn-IN.json',
        'app_title': 'ಚಿಂಪಲ್ ಕಿಡ್ಸ್ ಲರ್ನಿಂಗ್',
        'app_description': 'ಮಕ್ಕಳಿಗಾಗಿ ಸಂವಾದಾತ್ಮಕ ಕಲಿಕೆಯ ಘಟಕಗಳು.',
    },
    'Hindi': {
        'code': 'hi',
        'locale': 'hi-IN',
        'catalog_file': 'opds-hi-IN.json',
        'catalog_title': 'Chimple Kids Learning',
        'app_manifest': 'launchable-app-hi-IN.json',
        'app_title': 'चिम्पल किड्स लर्निंग',
        'app_description': 'बच्चों के लिए इंटरैक्टिव लर्निंग यूनिट्स।',
    },
}
SUBJECT_TITLES = {
    'English': {'English': 'English', 'Kannada': 'ಇಂಗ್ಲಿಷ್', 'Hindi': 'अंग्रेज़ी'},
    'Maths': {'English': 'Maths', 'Kannada': 'ಗಣಿತ', 'Hindi': 'गणित'},
    'Kannada': {'Kannada': 'ಕನ್ನಡ'},
    'Hindi': {'Hindi': 'हिंदी'},
    'Digital Skills': {
        'English': 'Digital Skills',
        'Kannada': 'ಡಿಜಿಟಲ್ ಕೌಶಲಗಳು',
        'Hindi': 'डिजिटल कौशल',
    },
}
LANGUAGES_BY_CODE = {
    settings['code']: settings for settings in LANGUAGE_SETTINGS.values()
}
# Native lessons must use an Intent URI in TinCan so RESPECT launches Chimple
# directly and sends missing-app cases to the app-store link in the manifest.
CHIMPLE_LESSON_LAUNCH_BASE = f'{BASE_URL}respect/launch'
CHIMPLE_PACKAGE_NAME = 'org.chimple.bahama'
# Use production's host so OpenEEL caches the same URL Chimple requests.
LIDO_BUNDLE_BASE_URL = 'https://pub-9d27d46558f64e93a979827424d3e766.r2.dev/'
LEGACY_GRADE_KEYS = {
    ('English', '1', 'English'): 'en_g1',
    ('English', '2', 'English'): 'en_g2',
    ('English', '1', 'Maths'): 'maths_g1',
    ('English', '2', 'Maths'): 'maths_g2',
    ('English', '1', 'Digital Skills'): 'puzzle',
    ('Hindi', '1', 'Maths'): 'hi_maths_g1',
    ('Hindi', '2', 'Maths'): 'hi_maths_g2',
}
SUBJECT_ICON_URLS = {
    'english': 'https://pub-3a82c17429da40d1989930ae7eb2f2d1.r2.dev/course-icons/6796ee8f-a237-42a3-beda-94d61a7139a1-4de8f55c.webp',
    'maths': 'https://pub-3a82c17429da40d1989930ae7eb2f2d1.r2.dev/course-icons/e5cda413-2f6c-485d-8985-27e3b6aad0d5-6cca9deb.webp',
    'digital': 'https://pub-3a82c17429da40d1989930ae7eb2f2d1.r2.dev/course-icons/19bb079f-bc69-44e4-bc1d-0b77f2683b6c-5a17f2ef.webp',
}

# Output folders
OUTPUT_DIR = 'public'
GRADE_DIR = os.path.join(OUTPUT_DIR, 'grades')
LESSON_DIR = os.path.join(OUTPUT_DIR, 'lessons')
ICONS_DIR = os.path.join(OUTPUT_DIR, 'images', 'icons')
GRADE_IMAGES_DIR = os.path.join(OUTPUT_DIR, 'images', 'grades')

def get_lesson_launch_url(activity_id, chimple_lesson_id='', lesson_name=''):
    """Return the native-app Intent URI required by RESPECT TinCan metadata."""
    launch_parameters = {'activity_id': activity_id}
    if chimple_lesson_id:
        launch_parameters['chimple_lesson_id'] = chimple_lesson_id
    if lesson_name:
        launch_parameters['lesson_name'] = lesson_name
    return (
        f'intent://{CHIMPLE_LESSON_LAUNCH_BASE.removeprefix("https://")}'
        f'?{urlencode(launch_parameters)}'
        f'#Intent;scheme=https;category=android.intent.category.BROWSABLE;'
        f'package={CHIMPLE_PACKAGE_NAME};end'
    )


def get_lesson_relative_path(lesson_id, language):
    locale = LANGUAGES_BY_CODE[language]['locale']
    return f'lessons/{locale}/{lesson_id}.json'


def get_lesson_output_dir(language):
    locale = LANGUAGES_BY_CODE[language]['locale']
    return os.path.join(LESSON_DIR, locale)


def get_grade_title(language, grade):
    if language == 'English':
        return f'Grade {grade}'
    if language == 'Kannada':
        return f'{grade}ನೇ ತರಗತಿ'
    return f'कक्षा {grade}'


def get_subject_title(language, subject):
    return SUBJECT_TITLES.get(subject, {}).get(language, subject)


def get_group_title(language, grade, subject):
    return f'{get_grade_title(language, grade)} {get_subject_title(language, subject)}'


def load_course_groups():
    with open(COURSE_CONFIG_FILE, 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)
    if config.get('application') != 'Chimple Kids Learning':
        raise ValueError("Course config application must be 'Chimple Kids Learning'.")

    groups = []
    seen_files = set()
    for language_entry in config.get('languages', []):
        language = language_entry.get('language', '')
        settings = LANGUAGE_SETTINGS.get(language)
        if settings is None:
            raise ValueError(f'Unsupported course language: {language}')
        for grade_entry in language_entry.get('grades', []):
            grade = str(grade_entry.get('grade', '')).strip()
            for subject_entry in grade_entry.get('subjects', []):
                subject = subject_entry.get('subject', '').strip()
                sheet = f'{language} Grade {grade} {subject}'
                legacy_key = LEGACY_GRADE_KEYS.get((language, grade, subject))
                subject_slug = re.sub(r'[^a-z0-9]+', '_', subject.lower()).strip('_')
                filename_stem = legacy_key or f"{settings['code']}_g{grade}_{subject_slug}"
                filename = f'{filename_stem}.json'
                if filename in seen_files:
                    raise ValueError(f'Duplicate grade output filename: {filename}')
                seen_files.add(filename)
                groups.append({
                    'language': language,
                    'language_code': settings['code'],
                    'grade': grade,
                    'subject': subject,
                    'sheet': sheet,
                    'title': get_group_title(language, grade, subject),
                    'grade_title': get_grade_title(language, grade),
                    'subject_title': get_subject_title(language, subject),
                    'grade_filename': f"grade_{settings['code']}_g{grade}.json",
                    'filename': filename,
                })

    if not groups:
        raise ValueError('Course config contains no language/grade/subject groups.')
    return groups

def clean_lesson_value(value):
    value = str(value or '').strip()
    return '' if value.lower() in {'nan', 'none'} else value


def get_lido_lesson_id(cocos_lesson_code, lido_lesson_id=''):
    """Return Cuba's stored bundle ID unchanged, preferring Lido over Cocos."""
    lido_lesson_id = clean_lesson_value(lido_lesson_id)
    if lido_lesson_id and lido_lesson_id.lower() != 'default':
        return lido_lesson_id

    cocos_lesson_code = clean_lesson_value(cocos_lesson_code)
    if not cocos_lesson_code or cocos_lesson_code.lower() == 'default':
        return None

    return cocos_lesson_code


def get_lido_browser_launch_url(cocos_lesson_code, lido_lesson_id=''):
    lido_lesson_id = get_lido_lesson_id(cocos_lesson_code, lido_lesson_id)
    return f'https://chimple.cc/{lido_lesson_id}' if lido_lesson_id else None


def get_lido_bundle_url(cocos_lesson_code, lido_lesson_id=''):
    """Return the concrete Lido ZIP that RESPECT can retain for offline use."""
    lido_lesson_id = get_lido_lesson_id(cocos_lesson_code, lido_lesson_id)
    return f'{LIDO_BUNDLE_BASE_URL}{lido_lesson_id}.zip' if lido_lesson_id else None

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


def get_image_link(image_url):
    """Return a usable public HTTPS image link, or None for absent/unsafe URLs."""
    image_url = clean_lesson_value(image_url)
    parsed_url = urlsplit(image_url)
    if parsed_url.scheme.lower() != 'https' or not parsed_url.netloc:
        return None
    image_type = (
        'image/webp'
        if parsed_url.path.lower().endswith('.webp')
        else mimetypes.guess_type(parsed_url.path)[0] or 'image/png'
    )
    return {
        'href': image_url,
        'type': image_type,
    }


def get_lesson_image_link(lesson_data, cocos_lesson_code):
    return get_image_link(lesson_data.get('lesson_image')) or {
        'href': f"{BASE_URL}images/icons/{get_image_path(cocos_lesson_code or 'default')}",
        'type': 'image/png',
    }

# Load workbook
print(f"Loading workbook: {EXCEL_FILE}")
wb = load_workbook(EXCEL_FILE, read_only=True, data_only=True)
course_groups = load_course_groups()
missing_sheets = [group['sheet'] for group in course_groups if group['sheet'] not in wb.sheetnames]
if missing_sheets:
    wb.close()
    raise ValueError('Workbook is missing configured sheets: ' + ', '.join(missing_sheets))

def write_collection(path, url_path, title, navigation=None, publications=None, identifier=None):
    metadata = {'title': title}
    if identifier:
        metadata['identifier'] = identifier
    opds_catalog = {
        "metadata": metadata,
        "links": [{
            "rel": "self",
            "href": urljoin(BASE_URL, url_path),
            "type": TYPE_OPDS,
        }],
    }
    if navigation is not None:
        opds_catalog['navigation'] = navigation
    if publications is not None:
        opds_catalog['publications'] = publications
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(opds_catalog, f, indent=2, ensure_ascii=False)


# Root catalogs link to grade feeds; grade feeds link to subject feeds.
grade_feeds = {}
for group in course_groups:
    subject_key = group['subject'].lower()
    if subject_key == 'digital skills':
        subject_key = 'digital'
    icon = SUBJECT_ICON_URLS.get(subject_key, BASE_URL + 'images/icons/default.png')
    grade_key = (group['language'], group['grade'])
    grade_feed = grade_feeds.setdefault(grade_key, {
        'title': group['grade_title'],
        'filename': group['grade_filename'],
        'navigation': [],
    })
    grade_feed['navigation'].append({
        'href': BASE_URL + 'grades/' + group['filename'],
        'title': group['subject_title'],
        'type': TYPE_OPDS,
        'alternate': [{
            'href': icon,
            'rel': 'icon',
            'type': 'image/webp' if icon.endswith('.webp') else 'image/png',
            'title': group['subject_title'],
        }],
    })

grade_navigation_by_language = {language: [] for language in LANGUAGE_SETTINGS}
for (language, grade), grade_feed in grade_feeds.items():
    grade_url = 'grades/' + grade_feed['filename']
    write_collection(
        os.path.join(GRADE_DIR, grade_feed['filename']),
        grade_url,
        grade_feed['title'],
        navigation=grade_feed['navigation'],
    )
    grade_entry = {
        'href': BASE_URL + grade_url,
        'title': grade_feed['title'],
        'type': TYPE_OPDS,
    }
    grade_image_filename = f'colorful_number_{grade}.png'
    if os.path.isfile(os.path.join(GRADE_IMAGES_DIR, grade_image_filename)):
        grade_image = get_image_link(
            f'{BASE_URL}images/grades/{grade_image_filename}'
        )
        if grade_image:
            grade_entry['alternate'] = [{
                **grade_image,
                'rel': 'icon',
                'title': grade_feed['title'],
            }]
    grade_navigation_by_language[language].append(grade_entry)

# --- Generate language catalogs (OPDS catalog) ---
for language, settings in LANGUAGE_SETTINGS.items():
    navigation = grade_navigation_by_language[language]
    write_collection(
        os.path.join(OUTPUT_DIR, settings['catalog_file']),
        settings['catalog_file'],
        settings['catalog_title'],
        navigation=navigation,
    )
    print(f"Generated {settings['catalog_file']} with {len(navigation)} grade feeds.")

# --- Generate index.json (RESPECT App Manifest) ---
respect_manifest = {
    "name": {
        settings['locale']: settings['app_title']
        for settings in LANGUAGE_SETTINGS.values()
    },
    "description": {"en-US": "A collection of interactive learning units for children."},
    "license": "MIT",
    "website": BASE_URL,
    "icon": BASE_URL + "icon.webp",
    "learningUnits": BASE_URL + DEFAULT_COLLECTION_FILENAME,
    "defaultLaunchUri": (
        grade_navigation_by_language['English'][0]['href']
        if grade_navigation_by_language['English']
        else BASE_URL
    ),
    "android": {
        "packageId": "org.chimple.cuba",
        "stores": ["https://play.google.com/store/apps/details?id=org.chimple.cuba"]
    },
    "web": {
        "url": BASE_URL
    }
}
with open(os.path.join(OUTPUT_DIR, 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(respect_manifest, f, indent=2, ensure_ascii=False)
print(f"Generated index.json as RESPECT App Manifest.")

def write_launchable_app_manifest(language_name):
    settings = LANGUAGE_SETTINGS[language_name]
    alternate_links = [
        {
            'href': f"{BASE_URL}{other['app_manifest']}",
            'rel': 'alternate',
            'language': other['locale'],
        }
        for other_name, other in LANGUAGE_SETTINGS.items()
        if other_name != language_name
    ]
    app_manifest = {
        'metadata': {
            '@type': 'https://id.openeel.org/schema/launchable-app',
            'title': settings['app_title'],
            'description': settings['app_description'],
            'author': {'name': 'Chimple Kids Learning'},
            'identifier': f"{BASE_URL}app/{settings['locale']}",
            'language': settings['code'],
            'modified': datetime.now(timezone.utc).isoformat(),
        },
        'links': [
            {
                'rel': 'self',
                'href': f"{BASE_URL}{settings['app_manifest']}",
                'type': PUB_TYPE,
            },
            *alternate_links,
            {
                'rel': 'collection',
                'href': f"{BASE_URL}{settings['catalog_file']}",
                'type': TYPE_OPDS,
            },
            {
                'rel': 'https://id.openeel.org/rel/app-launch-uri',
                'href': f'{BASE_URL}respect/launch',
            },
            {
                'rel': 'https://id.openeel.org/rel/appstore-android',
                'href': 'https://play.google.com/store/apps/details?id=org.chimple.bahama',
                'title': 'Get it on Google Play',
            },
            {'rel': 'terms-of-service', 'href': 'https://www.chimple.org/privacy-policy'},
            {'rel': 'license', 'href': 'https://www.gnu.org/licenses/agpl-3.0.html'},
        ],
        'images': [
            {
                'href': 'https://raw.githubusercontent.com/chimple/cuba/RESPECTify/public/assets/icons/favicon.png',
                'type': 'image/png',
            }
        ],
    }
    output_files = [settings['app_manifest']]
    if language_name == 'English':
        output_files.append('manifest.json')
    for filename in output_files:
        with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as manifest_file:
            json.dump(app_manifest, manifest_file, indent=2, ensure_ascii=False)
    print(f"Generated {', '.join(output_files)}.")


for language_name in LANGUAGE_SETTINGS:
    write_launchable_app_manifest(language_name)

def create_lesson_manifest(
    lesson_data, lesson_id, title, asset_link, language='en'
):
    """Create a lesson manifest in Readium Web Publication Manifest format"""
    # Fix date format to RFC 3339 (UTC timezone)
    current_time = datetime.now(timezone.utc).isoformat()
    
    # Get image path
    cocos_lesson_code = clean_lesson_value(lesson_data.get('cocos_lesson_code'))
    lido_lesson_id = get_lido_lesson_id(
        cocos_lesson_code,
        lesson_data.get('lido_lesson_id'),
    )
    image_link = get_lesson_image_link(lesson_data, cocos_lesson_code)
    browser_launch_url = get_lido_browser_launch_url(cocos_lesson_code, lido_lesson_id)
    lido_bundle_url = get_lido_bundle_url(cocos_lesson_code, lido_lesson_id)
    lesson_path = get_lesson_relative_path(lesson_id, language)
    app_manifest = LANGUAGES_BY_CODE[language]['app_manifest']
    print(f"Using image for lesson {lesson_id}: {image_link['href'].rsplit('/', 1)[-1]}")

    
    # Create Readium Web Publication Manifest
    lesson_manifest = {
        "@context": [
            "https://readium.org/webpub-manifest/context.jsonld",
            "https://schema.org"
        ],
        "metadata": {
            "@type": "http://schema.org/Game",
            "title": title,
            "author": "Chimple",
            "identifier": f"{BASE_URL}activities/{lesson_id}",
            "language": language,
            "modified": current_time,
            "published": current_time,
            "description": f"Interactive learning lesson: {title}",
            "subject": ["Education", "Learning"],
            "readingProgression": "ltr"
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}{lesson_path}",
                "type": PUB_TYPE
            },
            {
                "rel": "https://id.openeel.org/rel/tincanxml",
                "href": f"{BASE_URL}{lesson_path[:-5]}/tincan.xml",
                "type": "application/xml"
            },
            {
                "rel": "https://id.openeel.org/rel/launchable-app",
                "href": f"{BASE_URL}{app_manifest}",
                "type": PUB_TYPE
            }
        ],
        "images": [
            {
                **image_link,
                "height": 128,
                "width": 128
            }
        ],

        "readingOrder": [
            {
                "type": "text/html",
                "href": browser_launch_url or get_lesson_launch_url(f'{BASE_URL}activities/{lesson_id}'),
                "title": title
            }
        ],
        "resources": [
            {
                **image_link,
                "properties": {
                    "width": 128,
                    "height": 128
                }
            }
        ]
    }

    # Include the same Lido ZIP that Cuba launches. RESPECT's Download action
    # only retains declared resources, so omitting this link leaves it unable
    # to prepare Lido lessons for offline use.
    if lido_bundle_url:
        lesson_manifest['resources'].append({
            "type": "application/zip",
            "href": lido_bundle_url,
            "properties": {
                "contains": ["application/xhtml+xml", "text/css", "image/*", "audio/*"]
            }
        })

    if cocos_lesson_code and asset_link:
        lesson_manifest['resources'].append({
            "type": "application/zip",
            "href": asset_link,
            "properties": {
                "contains": ["application/xhtml+xml", "text/css", "image/*"]
            }
        })
    
    return lesson_manifest


def create_tincan_xml(
    lesson_id, title, chimple_lesson_id, language='en'
):
    """Create the Rustici launch metadata for a lesson's canonical xAPI activity."""
    lesson_dir = os.path.join(get_lesson_output_dir(language), lesson_id)
    os.makedirs(lesson_dir, exist_ok=True)

    namespace = 'http://projecttincan.com/tincan.xsd'
    ET.register_namespace('', namespace)
    root = ET.Element(f'{{{namespace}}}tincan')
    activities = ET.SubElement(root, 'activities')
    activity = ET.SubElement(
        activities,
        'activity',
        {
            'id': f'{BASE_URL}activities/{lesson_id}',
            'type': 'http://activitystrea.ms/schema/1.0/game',
        },
    )
    ET.SubElement(activity, 'name').text = title
    description = ET.SubElement(activity, 'description', {'lang': language})
    description.text = f'Chimple Kids Learning activity: {title}'
    launch = ET.SubElement(activity, 'launch', {'lang': language})
    launch.text = get_lesson_launch_url(
        f'{BASE_URL}activities/{lesson_id}',
        chimple_lesson_id,
        title,
    )

    ET.ElementTree(root).write(
        os.path.join(lesson_dir, 'tincan.xml'),
        encoding='utf-8',
        xml_declaration=True,
    )

# --- Process configured language/grade/subject sheets ---
for group in course_groups:
    sheet_name = group['sheet']
    language = group['language_code']
    app_manifest = LANGUAGE_SETTINGS[group['language']]['app_manifest']
    subject_file = group['filename']
    print(f"\nProcessing {group['language']} {group['title']} from sheet: {sheet_name}")
    ws = wb[sheet_name]
    chapters_by_id = {}

    headers = [str(cell.value).strip() if cell.value else '' for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    row_count = 0
    valid_lessons = 0
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_count += 1
        data = dict(zip(headers, row))
        data = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        lesson_id_value = data.get('lesson_id')
        if lesson_id_value is None:
            print(f"Skipping row {row_count}: Missing lesson_id")
            continue
        lesson_id = str(lesson_id_value).strip()
        if not lesson_id or lesson_id.lower() == 'nan':
            print(f"Skipping row {row_count}: Missing lesson_id (value: '{lesson_id}')")
            continue
        title = str(
            data.get('title') or
            data.get('title ') or
            data.get('lesson_name') or
            ''
        ).strip()

        asset = clean_lesson_value(
            data.get('Asset Link') or
            data.get('Asset L') or
            ''
        )
        cocos_lesson_code = clean_lesson_value(data.get('cocos_lesson_code'))
        lido_lesson_id = get_lido_lesson_id(
            cocos_lesson_code,
            data.get('lido_lesson_id'),
        )

        if not title or title.lower() == 'nan':
            title = f"Lesson {lesson_id}"
            
        if not cocos_lesson_code and not lido_lesson_id:
            print(f"Skipping row {row_count}: Missing Cocos and Lido lesson IDs")
            continue

        if cocos_lesson_code and not asset:
            print(f"Skipping row {row_count}: Missing Cocos asset link")
            continue

        chapter_id = clean_lesson_value(data.get('chapter_id'))
        chapter_name = clean_lesson_value(data.get('chapter_name'))
        if not chapter_id or not chapter_name:
            print(f"Skipping row {row_count}: Missing chapter_id or chapter_name")
            continue

        valid_lessons += 1
        print(f"Processing lesson {lesson_id}: {title}")

        lesson_filename = f"{lesson_id}.json"

        lesson_manifest = create_lesson_manifest(
            data,
            lesson_id,
            title,
            asset,
            language=language,
        )
        # Match Cuba's bundle lookup: stored Lido ID first, then Cocos ID.
        create_tincan_xml(lesson_id, title, lido_lesson_id, language=language)

        lesson_path = get_lesson_relative_path(lesson_id, language)
        with open(
            os.path.join(get_lesson_output_dir(language), lesson_filename),
            'w',
            encoding='utf-8',
        ) as lf:
            json.dump(lesson_manifest, lf, indent=2, ensure_ascii=False)
        print(f"Generated lesson manifest: {lesson_filename}")

        # Get image path for OPDS
        image_link = get_lesson_image_link(data, cocos_lesson_code)
        browser_launch_url = get_lido_browser_launch_url(cocos_lesson_code, lido_lesson_id)

        # For OPDS catalog, create a simplified publication entry
        publication = {
            'metadata': {
                'title': lesson_manifest['metadata']['title'],
                'author': 'Chimple',
                'identifier': f"{BASE_URL}activities/{lesson_id}",
                'language': language,
                'modified': lesson_manifest['metadata']['modified']
            },
            'links': [
                {
                    'rel': 'self',
                    'href': f"{BASE_URL}{lesson_path}",
                    'type': PUB_TYPE
                },
                {
                    'rel': 'https://id.openeel.org/rel/tincanxml',
                    'href': f"{BASE_URL}{lesson_path[:-5]}/tincan.xml",
                    'type': 'application/xml'
                },
                {
                    'rel': 'https://id.openeel.org/rel/launchable-app',
                    'href': f"{BASE_URL}{app_manifest}",
                    'type': PUB_TYPE
                },
            ],
            'images': [
                {
                    **image_link,
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
        chapter = chapters_by_id.setdefault(chapter_id, {
            'name': chapter_name,
            'image': '',
            'publications': [],
        })
        if chapter['name'] != chapter_name:
            raise ValueError(
                f"Conflicting chapter names for {chapter_id} in {sheet_name}: "
                f"'{chapter['name']}' and '{chapter_name}'"
            )
        chapter_image = clean_lesson_value(data.get('chapter_image'))
        if chapter_image and not chapter['image']:
            chapter['image'] = chapter_image
        chapter['publications'].append(publication)

    chapter_navigation = []
    subject_stem = os.path.splitext(subject_file)[0]
    for chapter_number, (chapter_id, chapter) in enumerate(chapters_by_id.items(), start=1):
        chapter_file = f'{subject_stem}_chapter_{chapter_number}.json'
        chapter_url = f'grades/{chapter_file}'
        write_collection(
            os.path.join(GRADE_DIR, chapter_file),
            chapter_url,
            chapter['name'],
            publications=chapter['publications'],
            identifier=chapter_id,
        )
        chapter_entry = {
            'href': BASE_URL + chapter_url,
            'title': chapter['name'],
            'type': TYPE_OPDS,
        }
        chapter_icon = get_image_link(chapter['image'])
        if chapter_icon:
            chapter_entry['alternate'] = [{
                **chapter_icon,
                'rel': 'icon',
                'title': chapter['name'],
            }]
        chapter_navigation.append(chapter_entry)

    write_collection(
        os.path.join(GRADE_DIR, subject_file),
        f'grades/{subject_file}',
        group['subject_title'],
        navigation=chapter_navigation,
    )
    print(
        f"Generated {subject_file} with {len(chapters_by_id)} chapters and "
        f"{valid_lessons} valid lessons (skipped {row_count - valid_lessons} rows)"
    )

wb.close()
print("\nAll files generated successfully!")
