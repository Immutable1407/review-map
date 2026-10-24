# Contributing

Use fictional places and temporary data in tests. Keep original source captures, API keys, login state, calibration exports and review databases out of commits.

Run the checks in README.md. Add tests for identity changes, evidence gates, matching/calibration decisions and review permissions. UI changes should retain the map-first layout, responsive behavior, keyboard access and reduced-motion support.

Keep the English and Chinese READMEs aligned. Changes involving acquisition must retain the yichen-skills attribution and separate-license boundary; do not vendor its executors or skill text here.

To enable GitHub Actions, copy `.github/ci.example.yml` into `.github/workflows/ci.yml` and commit it with a credential authorized to update workflows. The template runs the same offline checks documented in the README.
