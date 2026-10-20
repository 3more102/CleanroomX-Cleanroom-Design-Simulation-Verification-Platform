# CleanroomX multiroom CFD — screenshot gallery

These six screenshots are source documentation assets supplied on 2026-10-20. Their image pixels are preserved byte-for-byte; only two original filenames were normalized by removing `(1)`.

## Scope and interpretation

The screens show a four-room, open-door cleanroom example, including the Process, Preparation, Ante / Airlock, and Reference Corridor rooms. The UI separates *design pressure targets* from *computed pressure fields*; no target achievement should be inferred from the figures.

The primary 13,210-cell example reports **iteration 600 — NOT CONVERGED**. Its computed pressure differences are small compared with the design targets. The images are screenshots of the application, **not proof of solver convergence, mesh independence, mass conservation acceptance or regulatory compliance**. Full case files, mesh/BC settings, log history and independent validation are needed before engineering acceptance.

## Screenshots

### 1. Design workspace: 2D plan and 3D model

![CleanroomX design workspace](images/multiroom-cfd/minimum-window-design.png)

Shows project navigation, workflow controls, 2D/3D model views and pressure design overlay. Design pressure labels in this GUI are **targets**, not computed room pressures.

### 2. Computed multiroom dashboard

![Open-door computed CFD dashboard](images/multiroom-cfd/computed-dashboard.png)

Shows room-wise computed pressure, velocity, supply, return and door transfers for the selected case. It explicitly states that the 600-iteration run is **not converged**. The pressure reference is the computed mean in the corridor.

### 3. Computed CFD pressure section and velocity vectors

![Computed section and velocity vectors](images/multiroom-cfd/computed-section.png)

The section view displays reported cell values on a selected plane and projected velocity vectors. Blank regions are not interpolated by the viewer. This screenshot does not independently establish mesh adequacy or convergence.

### 4. Room airflow balance and open-door transfer

![Room airflow balance table](images/multiroom-cfd/actual-room-flow-balances.png)

Displays room supply/return rates, imbalance ratios, open-door pressure differences and net/reverse flow components for the case. The GUI states that no imbalance acceptance limit is assumed. The relative pressure field remains a provisional result while its simulation is not converged.

### 5. Actual-design residual review — nonconverged 600-iteration run

![Actual design residual graph](images/multiroom-cfd/actual-design-residual-review.png)

Shows a log-scale residual history for pressure (`p`) and velocity components (`Ux`, `Uy`, `Uz`). The selected iteration is 600 and the UI explicitly says the full run did not report convergence. Low linear-final residuals alone do not demonstrate outer SIMPLE convergence.

### 6. Earlier snapshot — selected iteration 50

![Earlier low-flow convergence-history snapshot](images/multiroom-cfd/earlier-snapshot-convergence.png)

This image is from a **different lower-flow case**. The screenshot selects iteration 50, which is not converged at that iteration, while separately reporting that the *full run* reached convergence at iteration 163. Do not conflate these two states or compare case outcomes as if the inputs were identical.

## Asset integrity

`images/multiroom-cfd/manifest.json` lists original-image SHA-256 checksums, byte counts and dimensions. Run:

```powershell
python tools/validate_multiroom_cfd_gallery.py
```

The validation checks presence, PNG image dimensions, hashes, README references and the complete gallery. Screenshots remain documentary evidence, not substitutes for reproducible solver case data or quality-gate results.