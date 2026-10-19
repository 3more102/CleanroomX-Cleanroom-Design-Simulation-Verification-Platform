# Design Studio verification evidence

The current implementation is documented in `docs/GUI_REFERENCE_PARITY.md`.

- `design_studio_1536x960.png`: actual reference-sized Tk application capture.
- `design_studio_1920x1080.png`: actual larger desktop capture.
- Matching JSON files: screenshot hashes, imported source hashes, reference
  hash, dimensions, scene counts and capture platform.
- `verification.json`: source revision, regression result and visual review.

The capture script uses the running desktop window. No generated artwork or
image overlay is used as implementation evidence. Pressure is a configured
setpoint unless independently attributable solver evidence is available.

A Linux visual review and Windows CI interaction checks have distinct scopes;
consult `verification.json` and the current workflow run for their actual
results. The user's local Windows installation is not inspected or updated
by a remote Git branch push.
