# Claude desktop pet

A warm paper card with book-themed character actions. The current character uses its own 12 original MP4s and the first idle frame as the shared pose reference. The fixed transparent playback canvas preserves character proportions; all actions return to the same pose.

## Run

From this directory on Windows x64 with Python 3.13:

```powershell
python -m pip install -r requirements.txt
python app/main.py
```

`run.ps1` starts the same entry point. The sibling `share/` directory is required. A packaged copy runs from `dist/ClaudePet/ClaudePet.exe`; distribute the whole `ClaudePet` folder.

## Interactions

- Click for a response and the companion card. Double-click selects a larger response.
- Right-click for actions, walking, desktop controls, settings or exit. Tray recovery restores the character and card.
- Dragging requires a pressed mouse button and pointer movement; a stationary press remains a click. A short drag finishes the complete action and original return. A long drag holds the last lifted pose until release, then resumes the return.
- The always-on-top option is respected. Normal maximized workspaces do not trigger fullscreen hiding. Screenshot overlays keep the character mapped; actual native z-order is checked again when they close. Genuine borderless fullscreen content can still use the fullscreen-yield preference.
- Settings use General / Actions tabs and explicit Apply, Discard and Restore controls. Locking position also stops autonomous movement. Expanded views share the card's fixed native canvas.
- The character is silent. Manual actions can take over immediately; disabling that preference queues the latest choice. Automatic actions do not interrupt interactions or completion reminders.

## Local data

The quota card and today's Token chart use Claude desktop usage and Claude Code transcripts. Missing data stays unavailable instead of being invented; the last valid snapshot is retained when a read fails. Local quota reading can be disabled in settings.

User state is under `%LOCALAPPDATA%/ClaudeDesktopPet`, separate from other roles. Settings, logs, transcripts and credentials are excluded from Git.

## Prepare, verify and build

```powershell
python -m pip install -r ../share/requirements-assets.txt
python tools/prepare_assets.py
python tools/check.py
python tools/build.py
```

`prepare_assets.py` is the stable entry for `prepare_mp4_character.py`. Sources remain in `assets/character/MP4/`; transparent resources are in `playback-mp4/`. The original inventory and runtime descriptor carry sizes and SHA-256 checksums. Original videos are not bundled into the executable folder. Preparation cannot reconstruct artwork already outside a source video's boundaries.

Verification output and build caches belong in `build/`; current programs belong in `dist/`. Both directories are excluded from Git. Git LFS is required to obtain the MP4 and WebP assets after cloning.

See [animation contracts](docs/ANIMATIONS.md) and [architecture](docs/ARCHITECTURE.md).
