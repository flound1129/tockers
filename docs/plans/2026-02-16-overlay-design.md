# TFT Tocker's Trials Overlay — Design Doc

## Goal

A real-time screen overlay for TFT Tocker's Trials on Windows that reads game state via computer vision and provides score-optimized strategy advice. The core scoring insight: hoarding item components (2,500 pts/component/round) dominates all other scoring, so the agent's job is to find the minimum investment needed to survive while maximizing component hoarding.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  TFT Overlay App                 │
│                                                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Screen   │→ │ Vision    │→ │ Strategy     │  │
│  │ Capture  │  │ Engine    │  │ Agent        │  │
│  │ (DXcam)  │  │ (OpenCV)  │  │ (Local+API)  │  │
│  └──────────┘  └───────────┘  └──────┬───────┘  │
│                                      ↓           │
│                              ┌──────────────┐    │
│                              │ Overlay UI   │    │
│                              │ (PyQt6)      │    │
│                              └──────────────┘    │
│                                      ↕           │
│                              ┌──────────────┐    │
│                              │ tft.db       │    │
│                              │ (SQLite)     │    │
│                              └──────────────┘    │
└─────────────────────────────────────────────────┘
```

Four components in a loop:

1. **Screen Capture** — DXcam/BetterCam grabs frames at ~1-2 FPS during planning, on-demand during combat.
2. **Vision Engine** — OpenCV template matching identifies champions, items, gold, level, shop, game phase.
3. **Strategy Agent** — Local rules engine for fast queries against tft.db; Claude API for complex decisions.
4. **Overlay UI** — PyQt6 transparent always-on-top window renders advice over the game.

## Screen Capture

- Library: DXcam or BetterCam (DXGI Desktop Duplication API)
- Returns numpy arrays directly, ready for OpenCV
- 4K resolution (3840x2160)
- Low capture rate is fine — TFT planning phases are static

## Vision Engine — Detection Zones

| Zone | What to Read | Method |
|------|-------------|--------|
| Board (center) | My champions + hex positions | Template match champion portraits |
| Bench (bottom row) | Champions on bench | Template match portraits |
| Item Bench (left side) | Components on bench | Template match item icons (score-critical) |
| Shop (bottom) | 5 champion cards | Template match + OCR fallback |
| Gold/Level (bottom left) | Gold, XP, level | Digit template matching (0-9) |
| Game Phase | Planning/combat/augment/carousel | Detect phase-specific UI elements |
| Augment Select (center) | 3 augment choices | Template match against 30 Tocker's augments |
| Enemy Preview (right) | Enemy army | Template match, cross-ref enemy_boards table |

### Reference Images

- Screenshot each champion portrait and item icon once at 4K
- ~60 champion portraits, ~15 component icons, 30 augment icons
- Stored in a `references/` directory, organized by type
- Can partially automate collection in practice mode

### Matching Strategy

- Crop to known fixed pixel regions per zone (positions are fixed at a given resolution)
- Match against small known set per zone — not full-frame scanning
- OpenCV `matchTemplate` with normalized cross-correlation

## Strategy Agent

### Tier 1: Local Rules Engine (instant)

Queries tft.db, no API calls:

- **Round identification** — match detected enemy units against `enemy_boards` to know current round and upcoming enemies
- **Component counting** — items on bench x 2,500 x rounds remaining = score impact
- **Trait activation** — look up `champion_traits` + `trait_breakpoints` for active traits
- **Interest tracking** — gold amount / 10 = interest tier (max 5g)
- **Augment evaluation** — rank 3 augment choices against current board
- **Star-up tracking** — detect level-ups, track one-time 1,000pt bonuses

### Tier 2: Claude API (on-demand)

Called during planning/augment phases when there's time. Sends current board state, known upcoming enemies, scoring context. Asks:

- Level vs save gold?
- Which augment maximizes score?
- Can I beat round X without items? Minimum item investment to survive?

## Overlay UI

### Tech

- PyQt6, `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowTransparentForInput`
- Background thread: capture + vision loop
- Main thread: UI rendering
- Queue-based communication between threads
- Hotkey toggle (F12)

### Persistent Display (planning phase)

- Score estimate (running total + projected final)
- Component count + their remaining point value
- Current round / next enemy board name
- Gold interest bracket

### Contextual Popups

- **Augment select:** Tier ranking with reasoning
- **Shop phase:** Highlight champions that activate useful trait breakpoints
- **Pre-combat:** Win/loss prediction based on enemy board lookup

### Layout

Small semi-transparent panel in top-right or bottom-right corner. Configurable position. Minimal footprint — does not block gameplay.

## Tech Stack

- Python 3.11+
- DXcam or BetterCam (screen capture)
- OpenCV (template matching)
- PyQt6 (overlay UI)
- SQLite / tft.db (game data)
- Anthropic Python SDK (Claude API for Tier 2 agent)

## Platform

- Windows PC (desktop League client)
- 3840x2160 (4K) resolution
