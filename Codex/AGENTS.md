# Project conventions

- Read README.md and docs/DEVELOPMENT.md before changing application behavior.
- Use English folder names. Application code belongs in app/, tests in tests/, developer tools in tools/, and character resources in assets/character/.
- Keep development caches and verification output in build/; do not commit credentials, user conversations, logs, settings, databases or generated executables.
- Preserve character proportions, animation boundaries, silent automatic actions and completion reminder priority.
- Read Codex state and account limits from real local sources. Keep valid prior data and explain failures.
- Use a fixed window canvas and local repainting. Do not block the GUI thread while cancelling decoders.
- Software version identifiers, changelogs, author profiles and software update/install mechanisms are intentionally absent. Do not reintroduce them.
- Resource integrity descriptors and external protocol/schema markers are data contracts, not software release identifiers. Preserve their checksums.
- Validate applicable regressions with tools/check.py. Real desktop/browser checks require prepared assets and actual interactive acceptance.
