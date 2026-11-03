# Current ChatGPT animations

The active pack contains 23 actions from original MP4s: idle, two directional walks, nineteen gestures and drag. The source inventory lives in `assets/character/manifest.json`; `app/material_catalog.json` records the bundled resource checksums. The original MP4s remain under `MP4/`, and runtime resources live under `playback-mp4/`.

The idle MP4 first frame anchors every action. Contour-aware white-background removal keeps enclosed pale clothing opaque. Opaque native RGB is unchanged. Native 480 x 480 artwork is centered on a transparent 512 x 512 canvas without per-frame fitting, optical-flow texture borrowing or upscaling. Short premultiplied whole-frame bridges connect every action to the same exact reference pose.

All original frames remain in order. The independent-frame lossless WebP writer verifies decoded RGBA frames, frame counts and timing. The current source videos, frame ranges and individual checksums are authoritative in the runtime manifest; source clipping cannot be repaired by enlarging the window.

## Actions

Interactive variants are proud, greeting, inspiration, affection, snack, tsundere, sleepy, annoyed, dragon-breath, celebrate, heart, bond-mark, task-process, treasure, task-receive, inspect, quota-check, trust and dragon-pact. Directional walks move the window when space and settings allow. Existing Codex work and completion reaction mappings remain intact.

## Dragging

Holding the left button for 220 ms starts dragging even without movement; moving while pressed starts immediately. A quick click invalidates the hold callback. The source entrance starts at frame 27, reaches its last inverted pose at frame 170, and holds there while the pointer remains down. Early release completes the entrance before the original landing. Release resumes the next source frame and the untouched return. Menu previews play the entire supplied clip. Pointer capture loss, re-grabbing, inertia and window hiding have dedicated regression coverage.

## Commands

From this role's directory, run `python tools/prepare_character.py` to rebuild and `python tools/check.py test_mp4_matte test_mp4_character test_mp4_drag test_exit_and_single_pack` to validate. The default core suite checks application behavior separately. See `DEVELOPMENT.md` for data and packaging boundaries.
