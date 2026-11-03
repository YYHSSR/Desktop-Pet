# Claude MP4 character

The original videos are in `assets/character/MP4/`; processing never rewrites them. `manifest.json` inventories those MP4s. `character.json` describes the twelve prepared playback actions in `playback-mp4/`. Only the prepared playback files are bundled.

| Action | Role |
| --- | --- |
| idle | Canonical idle reference and loop |
| rest | Quiet companion gesture |
| wave | Greeting |
| peek | Click response |
| idea | Inspiration |
| sparkles | Glowing pages |
| wind | Hair and dress adjustment |
| bow | Turn and bow |
| flower | Flower from the book |
| drag | Pointer drag only; manual full-clip preview remains available |
| walk-left | Directional travel |
| walk-right | Directional travel |

`python tools/prepare_mp4_character.py` rebuilds the pack. The canonical `prepare_assets.py` entry dispatches here when MP4 sources are present. The videos are native 480 x 480 at 24 fps. Pixels are centered on a 512px transparent canvas without geometric warping or texture synthesis. Pale outlined fabric stays opaque. Exterior diffuse glows in the inspiration and page-light actions receive fractional alpha. All source frames remain intact, with short additional premultiplied pose dissolves to the shared idle anchor. First and last RGBA frames match exactly across the pack.

Drag interaction skips its static opening and starts at source frame 36. It plays through source frame 176 once. Early release queues the remaining source frames, so a quick drag still completes the entire action. Continued dragging keeps frame 176 on screen without replaying or decoding a hold loop. Release resumes source frame 177 onward, including the return to idle. Mouse press prepares the visible entry asynchronously; a simple press without movement never starts dragging. Lost capture and hidden windows cancel safely.

Claude's local `app/claude_sprite.py` implements this policy as a subclass. Shared sprite code and the ChatGPT/Gemini implementations are unchanged. Idle caching is bounded to 160 MB with a 128 MB entry limit. Actions remain silent; original click weights, travel, quota data and completion priorities are retained.

Run `python tools/check.py` for regressions, source hashes, full-frame transparency and playback integrity. `build/mp4-rebuild/verification.json` records frame retention, opaque RGB equality, original hashes, and exact lossless output verification.
