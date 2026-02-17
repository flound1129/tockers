# Companion Window Design

**Date:** 2026-02-17
**Status:** Approved

## Overview

A secondary PyQt6 window that sits beside the TFT game window on the same screen. Displays live game state and provides an AI chat interface where the user can ask strategy questions. The AI automatically receives current game state with every message.

## Architecture

Two windows from a single `QApplication`:

- **OverlayWindow** (existing) — transparent, click-through, always on top. Minimal score/round/gold display.
- **CompanionWindow** (new) — standard opaque window, ~400px wide, positioned beside TFT.

Both windows share the same `GameState` object. The vision loop updates it; both windows read from it.

## CompanionWindow Layout

Three stacked panels:

### Game Info Panel (~25% height)
Auto-refreshes every second from shared game state:
- Round, gold, level, lives
- Current shop contents
- Items on bench + their score value
- Projected total score

### Chat Panel (~60% height)
- Scrollable message history, newest at bottom
- Each message shows sender ("You" / "AI") and text
- "Thinking..." indicator while awaiting API response
- Last ~10 messages sent to Claude for conversational continuity

### Input Bar (~15% height)
- Text input field (full width)
- Send button (also triggered by Enter key)

## AI Integration

Every message to Claude includes an injected game state context block:
- Current round, gold, level, lives
- Items on bench + score value
- Current shop
- Next enemy board (from DB)
- Projected score

Uses the existing `StrategyEngine.ask_claude()` method. API call runs on a background thread; UI remains responsive during calls.

## New Files

- `overlay/companion.py` — `CompanionWindow` widget

## Modified Files

- `overlay/main.py` — instantiate and show `CompanionWindow` alongside `OverlayWindow`; pass shared game state to both
- `overlay/strategy.py` — extend `ask_claude()` to accept a conversation history list
- `requirements.txt` — no new dependencies (PyQt6 already present)

## Out of Scope

- Voice input / speech recognition
- Text-to-speech
- Settings persistence beyond the session
