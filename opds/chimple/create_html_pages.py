import os
import json
from pathlib import Path

# Configuration
BASE_URL = 'https://chimple-respectify.web.app/'
DOWNLOAD_DIR = 'public/download'
LESSON_DIR = 'public/lessons'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def create_lesson_html(lesson_id, title, manifest_url):
    """Create an HTML page for a lesson with proper manifest link"""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link href="{manifest_url}" rel="manifest" type="application/webpub+json">
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
    
    <div class="lesson-info">
        <h2>Lesson Information</h2>
        <p><strong>Lesson ID:</strong> {lesson_id}</p>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Manifest URL:</strong> <a href="{manifest_url}">{manifest_url}</a></p>
    </div>
    
    <div class="manifest-link">
        <strong>Manifest Link Tag:</strong><br>
        &lt;link href="{manifest_url}" rel="manifest" type="application/webpub+json"&gt;
    </div>
    
    <p>This is a placeholder page for the lesson. The actual lesson content would be embedded here.</p>
    
    <p><a href="{manifest_url}">View Lesson Manifest</a></p>
</body>
</html>"""
    
    return html_content

def main():
    """Generate HTML pages for all lessons"""
    lesson_files = list(Path(LESSON_DIR).glob('*.json'))
    
    print(f"Found {len(lesson_files)} lesson files")
    
    for lesson_file in lesson_files:
        lesson_id = lesson_file.stem
        
        # Read the lesson manifest to get the title
        try:
            with open(lesson_file, 'r', encoding='utf-8') as f:
                lesson_data = json.load(f)
                title = lesson_data.get('metadata', {}).get('title', f'Lesson {lesson_id}')
        except Exception as e:
            print(f"Error reading {lesson_file}: {e}")
            title = f'Lesson {lesson_id}'
        
        # Create manifest URL
        manifest_url = f"{BASE_URL}lessons/{lesson_id}.json"
        
        # Generate HTML content
        html_content = create_lesson_html(lesson_id, title, manifest_url)
        
        # Write HTML file
        html_file = os.path.join(DOWNLOAD_DIR, f"{lesson_id}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated HTML for {lesson_id}: {title}")
    
    print(f"\nGenerated {len(lesson_files)} HTML files in {DOWNLOAD_DIR}")

if __name__ == "__main__":
    main() 