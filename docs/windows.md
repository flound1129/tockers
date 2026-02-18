# Windows Deployment Guide

## Prerequisites

### 1. Python 3.11+
Download and install from https://www.python.org/downloads/

During install, check **"Add Python to PATH"**.

Verify:
```
python --version
```

### 2. Git
Download from https://git-scm.com/download/win

### 3. Tesseract OCR
The overlay uses Tesseract for reading round number, gold, level, shop cards, etc.

Download the Windows installer from:
https://github.com/UB-Mannheim/tesseract/wiki

Install to the default location: `C:\Program Files\Tesseract-OCR\`

Verify:
```
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

The overlay expects Tesseract at that exact path. If you install elsewhere, set the environment variable:
```
TESSDATA_PREFIX=C:\path\to\Tesseract-OCR
```

---

## Setup

### 1. Clone the repo
```
git clone https://github.com/flound1129/tockers.git
cd tockers
```

### 2. Create virtualenv and install dependencies
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 3. Create `.env` file
Create a file named `.env` in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Build the database
The overlay reads enemy board data and game info from a local SQLite DB. You need the raw game data files to build it:

- `C:\tmp\map22.bin.json` — raw map data (53MB, ask for this file)
- Community Dragon data is downloaded automatically

Run:
```
.venv\Scripts\python build_db.py
```

This creates `tft.db` in the project root. Only needs to be re-run if game data changes.

### 5. Download reference icons (optional)
Used for template-matching items and augments on screen. If the `references/` directory is empty:
```
.venv\Scripts\python download_references.py
```

---

## Running the Overlay

Make sure TFT is running at **2560x1440** before launching.

```
.venv\Scripts\python -m overlay.main
```

Two windows will appear:
- **Overlay** — score projection and round info, positioned top-right of screen
- **Companion** — live game state, chat interface for strategy questions

To exit, close either window or press Ctrl+C in the terminal.

---

## Updating

```
git pull
.venv\Scripts\pip install -r requirements.txt
```

If `build_db.py` changed (new game data), re-run it:
```
.venv\Scripts\python build_db.py
```

---

## Troubleshooting

**`pytesseract.pytesseract.TesseractNotFoundError`**
Tesseract is not on the PATH. Either reinstall to the default location or add `C:\Program Files\Tesseract-OCR\` to your system PATH.

**`ModuleNotFoundError: No module named 'dxcam'`**
Run `.venv\Scripts\pip install dxcam` — it's Windows-only and occasionally drops off on reinstall.

**Shop names not reading correctly**
OCR accuracy depends on the game running at exactly 2560x1440. Check Display Settings → Resolution.

**Companion window AI chat not responding**
Check that `.env` exists and contains a valid `ANTHROPIC_API_KEY`. The key must start with `sk-ant-`.

**`tft.db` not found**
Run `build_db.py` first. See step 4 above.
