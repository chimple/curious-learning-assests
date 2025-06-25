import os
import json
from pathlib import Path

BASE_URL = 'https://curious-reader.web.app/lessons/'
LESSON_DIR = 'public/lessons'
DOWNLOAD_DIR = 'public/download'

TYPE_TO_FOLDER = {
    'cr_lang': 'ftm',
    'book': 'story',
    'data': 'assessment',
}
GITHUB_BASE = 'https://raw.githubusercontent.com/chimple/curious-learning-assests/main/'

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{title}</title>
    <link href=\"{manifest_url}\" rel=\"manifest\" type=\"application/webpub+json\">
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }}
        .lesson-info {{
            background: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .manifest-link {{
            background: #e3f2fd;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    
    <div class=\"lesson-info\">
        <h2>Lesson Information</h2>
        <p><strong>Lesson ID:</strong> {lesson_id}</p>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Manifest URL:</strong> <a href=\"{manifest_url}\">{manifest_url}</a></p>
    </div>
    
    <div class=\"manifest-link\">
        <strong>Manifest Link Tag:</strong><br>
        &lt;link href=\"{manifest_url}\" rel=\"manifest\" type=\"application/webpub+json\"&gt;
    </div>
    {download_html}
    <p>This is a placeholder page for the lesson. The actual lesson content would be embedded here.</p>
    
    <p><a href=\"{manifest_url}\">View Lesson Manifest</a></p>
</body>
</html>
"""

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def main():
    lesson_files = list(Path(LESSON_DIR).rglob('*.json'))
    print(f"Found {len(lesson_files)} lesson files")
    for lesson_file in lesson_files:
        rel_path = lesson_file.relative_to(LESSON_DIR)
        lesson_id = rel_path.with_suffix('').as_posix()  # e.g. cr_lang/amharic
        parts = rel_path.parts
        if len(parts) >= 2:
            type_key = parts[0]
            value = Path(parts[1]).stem
            folder = TYPE_TO_FOLDER.get(type_key)
            zip_url = f"{GITHUB_BASE}{folder}/{value}.zip" if folder else ""
        else:
            zip_url = ""
        try:
            with open(lesson_file, 'r', encoding='utf-8') as f:
                lesson_data = json.load(f)
                title = lesson_data.get('metadata', {}).get('title', f'Lesson {lesson_id}')
        except Exception as e:
            print(f"Error reading {lesson_file}: {e}")
            title = f'Lesson {lesson_id}'
        manifest_url = f"{BASE_URL}{rel_path.as_posix()}"
        download_html = f'<p><a href="{zip_url}" download>Download Lesson Zip</a></p>' if zip_url else ""
        html_content = HTML_TEMPLATE.format(
            title=title,
            lesson_id=lesson_id,
            manifest_url=manifest_url,
            download_html=download_html
        )
        # Output HTML to public/download/<type>/<value>.html
        html_out_path = Path(DOWNLOAD_DIR) / rel_path
        html_out_path = html_out_path.with_suffix('.html')
        ensure_dir(html_out_path.parent)
        with open(html_out_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Generated HTML for {lesson_id}: {title}")
    print(f"\nGenerated {len(lesson_files)} HTML files in {DOWNLOAD_DIR}")

if __name__ == "__main__":
    main() 