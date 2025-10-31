import json
import os
from pathlib import Path

def extract_audio_urls(ftm_english_path):
    """Extract all audio URLs from ftm_english.json"""
    with open(ftm_english_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    audio_urls = set()
    
    # Add feedback audios
    for url in data.get('FeedbackAudios', []):
        audio_urls.add(url.strip())
    
    # Add other audios
    for url in data.get('OtherAudios', {}).values():
        audio_urls.add(url.strip())
    
    # Extract audio URLs from levels and puzzles
    for level in data.get('Levels', []):
        for puzzle in level.get('Puzzles', []):
            # Check prompt audio
            prompt = puzzle.get('prompt', {})
            if isinstance(prompt, dict) and 'PromptAudio' in prompt:
                audio_urls.add(prompt['PromptAudio'].strip())
            
            # Check target stones
            for stone in puzzle.get('targetstones', []):
                if 'StoneAudio' in stone:
                    audio_urls.add(stone['StoneAudio'].strip())
            
            # Check foil stones
            for stone in puzzle.get('foilstones', []):
                if 'StoneAudio' in stone:
                    audio_urls.add(stone['StoneAudio'].strip())
    
    return audio_urls

def update_json_file(file_path, audio_urls_to_keep):
    """Update a single JSON file to keep only specified audio URLs"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if 'resources' not in data:
        print(f"No 'resources' found in {file_path}, skipping...")
        return False
    
    # Filter resources to keep only audio files that are in our whitelist
    new_resources = []
    audio_kept = 0
    
    for resource in data['resources']:
        # Keep non-audio resources
        if not resource.get('type', '').startswith('audio/'):
            new_resources.append(resource)
            continue
            
        # For audio resources, check if URL is in our whitelist
        audio_url = resource.get('href', '').strip()
        if audio_url in audio_urls_to_keep:
            new_resources.append(resource)
            audio_kept += 1
    
    data['resources'] = new_resources
    
    # Save the updated file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return audio_kept

def main():
    # Paths
    base_dir = Path(__file__).parent
    ftm_english_path = base_dir / 'public' / 'web-apps' / 'ftm' / 'english' / 'ftm_english.json'
    target_dir = base_dir / 'public' / 'lessons' / 'cr_lang'
    
    if not ftm_english_path.exists():
        print(f"Error: {ftm_english_path} not found!")
        return
    
    if not target_dir.exists():
        print(f"Error: {target_dir} not found!")
        return
    
    print("Extracting audio URLs from ftm_english.json...")
    audio_urls = extract_audio_urls(ftm_english_path)
    print(f"Found {len(audio_urls)} unique audio URLs in ftm_english.json")
    
    # Find all ftm_en_*.json files
    json_files = list(target_dir.glob('ftm_en_*.json'))
    print(f"Found {len(json_files)} JSON files to process")
    
    # Process each file
    total_kept = 0
    for json_file in json_files:
        print(f"\nProcessing {json_file.name}...")
        kept = update_json_file(json_file, audio_urls)
        if kept is not False:
            print(f"  - Kept {kept} audio files")
            total_kept += kept
    
    print(f"\nDone! Processed {len(json_files)} files, kept a total of {total_kept} audio files.")

if __name__ == "__main__":
    main()
