# Gemini architecture

## Boundaries

`app/` owns this role's card, interaction policy and local data readers. The role imports shared modules from `share/`, never another role's application. `app/main.py` is the source and frozen entry point. The shared entry handles single-instance recovery, isolated smoke-test state and crash logging.

## Animation playback

`GeminiSprite` retains ambient stars and extends `GeminiMotionSprite`, which owns the complete-action drag policy. The shared streaming decoder provides cancellation, bounded queues, immutable decoded frames and loop caching. Decoder cancellation does not block the GUI thread. Native geometry stays fixed while repainting animation frames.

The current resource descriptor is `assets/character/character.json`, with 14 actions prepared exclusively from the original MP4 inventory in `manifest.json`. Runtime files live in `playback-mp4/`. The canonical pose, exact endpoints, source hashes, frame counts and timing are verified during preparation. See `ANIMATIONS.md` for dimensions and drag frame ranges.

The local `Companion.drag_finished()` completes an early-released entrance instead of cutting it off. A held pose stops the animation timer. Release resumes the original tail; queued completion reactions remain ahead of optional activities. Lost pointer capture and hidden windows cancel safely.

## Desktop visibility

`gemini_windowing.py` filters ordinary maximized workspaces and screenshot surfaces out of media fullscreen hiding. Startup, tray recovery, settings changes and normal visibility polls restore visible HWNDs with non-activating `SetWindowPos` calls. Native z-order is checked even if TOPMOST remains set and the foreground HWND has not changed. Capture overlays do not interrupt animation, and closing them triggers recovery. The user's unpinned preference and genuine fullscreen-yield option remain supported.

## Card and data

The shared companion card contains a compact quota dashboard, today's hourly Token chart and a General / Actions settings editor. Navigation, expansion and collapse use cached snapshots on a stable native canvas. Editing maintains a draft until Apply; external changes retain dirty fields and surface conflicts.

Quota and Token readers run outside the GUI thread and consume real local records. The last valid data survives transient failures. Missing values remain unavailable. There are no synthetic quotas, embedded chats, updater services or application release identifiers.

## Validation and packaging

`tools/check.py` runs tests with isolated application state and Qt offscreen rendering, then verifies every prepared frame and every original source checksum. Unit fixtures do not inspect or reorder the real desktop. Native interactive acceptance is separate from headless tests.

`tools/build.py` bundles the current descriptor, referenced playback files, shared fonts and licenses. It preserves each resource's relative directory and excludes original MP4s, user data and build caches. `share/tools/package_all.py` can build and verify all roles while archiving replaced executables.
