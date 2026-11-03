# Gemini MP4 character

The active character uses only the fourteen original MP4s in `assets/character/MP4`. The idle MP4 first frame is the canonical reference pose. Original files remain unchanged and their sizes/checksums are recorded in `manifest.json`.

| Action ID | Source meaning |
| --- | --- |
| idle | Idle |
| greeting | Wave |
| curious | Curious peek |
| glance | Smile over shoulder |
| meow | Meow response |
| stretch | Stretch |
| hop | Gentle jump |
| pout | Comfort the cat |
| chase | Chase tail |
| pounce | Pounce toward you |
| catch | Catch starlight |
| drag | Dragging |
| walk-left | Chase left |
| walk-right | Pounce right |

`tools/prepare_assets.py` dispatches to `prepare_mp4_character.py`. Native 720 x 720, 24 fps frames receive contour-aware white-background removal with enclosed pale artwork protection. Opaque native pixels retain original decoded RGB. One fixed whole-frame Lanczos resize produces 480 x 480 artwork, centered in a 512 x 512 transparent canvas with sixteen pixels of padding. There is no frame-dependent fitting, pose warping, texture synthesis or cross-frame colour replacement. Catching starlight uses a soft exterior alpha for diffuse light.

Every source frame remains in order. A short premultiplied whole-frame dissolve joins the canonical idle pose to each source beginning and joins its ending back to idle. All playback actions start/end at the exact same RGBA pose. The lossless independent-frame WebP writer verifies frame count, each decoded RGBA frame and every frame delay. Runtime resources are in `playback-mp4`; original MP4s and prepared playback resources have separate manifests.

## Drag contract

A click or a stationary press does not start dragging. Crossing the movement threshold starts Gemini's own source frames 30 through 204, offset by any entry bridge. Releasing early completes that entire segment before source frame 205 and the remaining original return play. Continuing to hold freezes frame 204 without decoding or repeating the standing pose. Releasing then plays the same original return to the canonical idle reference. Re-grabbing during the entrance keeps progress. A lost mouse grab safely releases instead of leaving a permanent held pose.

The optional post-drag hop is disabled by default for the same return-to-idle behavior as the other rebuilt roles. If explicitly enabled, it runs only after the full return, and queued completion actions take priority. The action menu plays the entire original drag clip, including its entrance and return. There is no independent legacy lift action in the active MP4 pack because it has no new MP4 source.

## Source boundaries

Transparent padding prevents additional canvas clipping; it cannot reconstruct artwork already outside an original MP4 boundary. Preparation retains the source composition instead of fabricating missing curls or effects.
