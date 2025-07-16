import os
import json

# Paths
LANGUAGES_JSON = 'languages.json'
FTM_ZIPS_DIR = os.path.join('public', 'zips', 'ftm')

def get_ftm_name_to_code():
    with open(LANGUAGES_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    mapping = {}
    for app in data.get('web_apps', []):
        app_url = app.get('appUrl', '')
        if '?cr_lang=' in app_url:
            # FTM app
            lang_code = app.get('langCode')
            cr_lang = app_url.split('?cr_lang=')[-1].split('&')[0]
            mapping[cr_lang.lower()] = lang_code
    return mapping

def main():
    name_to_code = get_ftm_name_to_code()
    # List all zip files in the FTM zips directory
    for fname in os.listdir(FTM_ZIPS_DIR):
        if not fname.lower().endswith('.zip'):
            continue
        base = fname[:-4]  # remove .zip
        # Try to find a mapping for this base name
        # Some zips may have underscores or other differences, so try to match smartly
        match = None
        for cr_lang, lang_code in name_to_code.items():
            if base.lower() == cr_lang:
                match = lang_code
                break
        if match and f'{match}.zip' != fname:
            src = os.path.join(FTM_ZIPS_DIR, fname)
            dst = os.path.join(FTM_ZIPS_DIR, f'{match}.zip')
            print(f'Renaming {fname} -> {match}.zip')
            os.rename(src, dst)

if __name__ == '__main__':
    main() 