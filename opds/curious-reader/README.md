# Curious Reader OPDS Generator

This tool generates OPDS (Open Publication Distribution System) feeds and lesson manifests for the Curious Reader application. It supports multiple content types including FTM (Feed The Monster), assessments, and storybooks.

## Features

- Generates OPDS feed structure for Curious Reader content
- Supports multiple languages and content types:
  - FTM (Feed The Monster) lessons
  - Assessments
  - Storybooks
- Resource crawling capability for web content
- Configurable lesson counts per language
- Right-to-left (RTL) language support
- Automatic audio resource detection and inclusion

## Prerequisites

- Python 3.x
- Required Python packages:
  - `tqdm` (for progress bars)
  - `playwright` (optional, only for resource crawling)

## Installation

If you plan to use the resource crawling feature:

```bash
pip install playwright
playwright install chromium
```

## Usage

Basic usage:

```bash
python opds.py
```

Common options:

```bash
python opds.py --verbose                          # Show detailed progress
python opds.py --ftm-lessons 50                   # Set custom lesson count
python opds.py --crawl-resources                  # Enable resource crawling
python opds.py --skip-ftm                         # Skip FTM content
python opds.py --skip-assessment                  # Skip assessment content
python opds.py --skip-book                        # Skip storybook content
```

### Command Line Options

- `--base-dir`: Base directory aligned to the public folder (default: ./public)
- `--base-out-url`: Public base URL for generated hrefs (default: https://curiousreader-respect-ftm.web.app)
- `--ftm-lessons`: Number of FTM lessons per language (default: 100)
- `--crawl-resources`: Enable resource crawling with Playwright
- `--crawl-timeout-ms`: Timeout for resource crawling in milliseconds (default: 15000)
- `--skip-ftm`: Skip generation of FTM lesson manifests
- `--skip-assessment`: Skip generation of assessment manifests
- `--skip-book`: Skip generation of story book manifests
- `--verbose`: Print detailed progress information

## Output Structure

The script generates the following structure under the public directory:

```
public/
├── opds.json                    # Main OPDS feed
├── lessons/
│   ├── cr_lang/                # FTM lesson manifests
│   ├── data/                   # Assessment manifests
│   └── book/                   # Storybook manifests
├── grades/                     # Language-specific grade feeds
└── web-apps/                   # Web application resources
```

## Configuration

The script requires a `languages.json` file that defines the available languages and web applications. The file should be located in one of these locations:
- ./public/languages.json
- ../public/languages.json
- ./languages.json

## Resource Crawling

When enabled with `--crawl-resources`, the script will:
1. Launch a headless Chromium browser
2. Load each open-access URL
3. Capture network resources
4. Save and include them in the manifests

This ensures offline availability of required resources.

## Generated Files

1. `opds.json` - Main OPDS feed containing language navigation
2. Language-specific lesson manifests in `lessons/cr_lang/`
3. Grade feeds per language in `grades/`
4. Assessment and storybook manifests
5. Resource manifests for offline access

## Error Handling

The script includes error handling for:
- Missing languages.json
- Invalid directory structures
- Network resource crawling failures
- Malformed input files

## Environment Variables

- `FTM_LESSONS`: Set default number of FTM lessons (overridden by --ftm-lessons)
- `CRAWL_TIMEOUT_MS`: Set default crawling timeout (overridden by --crawl-timeout-ms)