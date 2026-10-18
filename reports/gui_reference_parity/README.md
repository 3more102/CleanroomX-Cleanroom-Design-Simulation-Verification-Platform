# CleanroomX Design Studio — GUI Reference Parity Receipts

This directory is reserved for genuine visual captures and engineering receipts.

## Captured iteration

- Frozen baseline commit: `cf5506ffc5793313e023118209faafefc17e73b7`
- Implementation branch: `gui/design-studio-reference-parity-20261019`
- Real screenshot environment: Linux runner, Xvfb, Tkinter Canvas, 1920×1080
- [GitHub workflow with actual before/after PNG artifacts](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39170549682)
- Before viewport: 896×249 pixels; after: 1509×616 pixels
- Demo geometry: 3 rooms; 62 m²; 186 m³; 10 devices/openings
- Displayed pressure values are configured/analytical, not solver-computed.

## Artifact provenance

The CI job captures the original Tk application and proposed Tk application
against the same Linux display resolution and includes one JSON receipt per
PNG. The PNGs are stored as GitHub Actions workflow artifacts; do not substitute
AI-generated artwork for the captures.

A verified, separate Windows desktop comparison against the user's reference
image is still needed. No numeric visual-parity percentage is published until
each acceptance item and the actual reference comparison have evidence.

## Release status

**HOLD / DRAFT PR.** Focused tests and Linux captures validate that the
new GUI controls render and selected interactions work. Do not merge solely on
the basis of these receipts. The project's full cross-platform regression
and actual OpenFOAM execution still need sign-off.
