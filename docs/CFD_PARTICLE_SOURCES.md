# Recorded-field particle sources

The source scheduler reuses `cfd_particles.py` and the existing recorded-cell
velocity grid. It introduces no new particle forces. This is one-way numerical
screening of spherical particles in **one frozen recorded OpenFOAM U field**.
It is not time-dependent OpenFOAM Lagrangian transport or a concentration model.

## Source inputs and release clock

Each source has a unique ID, enabled flag, 3D position in an occupied solved
fluid voxel, numerical particle count, start time, release duration, diameter,
density, and optional initial velocity. A null initial velocity uses the
recorded carrier-gas velocity at injection. Inactive sources are retained.

For N > 1, releases occur at `start + duration * i / (N - 1)`, i = 0…N−1.
Zero duration gives simultaneous releases. A single particle requires zero
duration. These are deterministic numerical releases, not a measured aerosol
emission rate or independent statistical sample. Enabled sources are limited
to 20 numerical particles in total; observation end is at most 60 seconds.

Every release must precede the common observation end. Particle age starts
at zero at its release; its integration horizon is observation end minus
release time. Source release time and particle age are distinct from the
OpenFOAM **SIMPLE iteration** recorded in the source provenance.

The integrator retains its documented Stokes/Cunningham drag, inertia,
buoyancy-adjusted gravity and piecewise-constant occupied-voxel U lookup.
There is no interpolation across solid cells. Boundary contact remains
**unresolved**: it is not classified as outlet escape, deposition or rebound.
High slip Reynolds is reported by the existing model-validity warning.

## API and persistence

`cfd_particle_sources.py` supplies validation, source configuration export/import,
atomic source integration, population accounting, independently replayed JSON
export, and trajectory CSV export. Configurations are bound to the selected
solver iteration plus manifest and execution-receipt SHA-256 identities.
Import rejects a different source run, unknown metadata, duplicate JSON keys,
nonfinite inputs, invalid seeds, duplicate source IDs and unsupported physics.
Exports use exclusive creation and do not overwrite existing evidence.

Playback uses actual recorded integration vertices with last-sample hold and
hides numerical particles until their release. Completed/contacted particles
hold their final recorded position; a held marker is not evidence of continued
motion or physical deposition. CSV contains release time, particle age,
observation sample time, xyz, particle velocity, recorded carrier U, room,
termination and solver source identity.

The numerical population ledger partitions every scheduled numerical particle
into not released, currently tracked, unresolved boundary contact, integration
step limit or observation complete. Room counts use the last available sample
label, including held terminal samples. This ledger checks accounting; it
does not prove physical mass conservation, concentration or cleanroom class.

All results retain `engineering_release=HOLD` and
`validated_particle_transport=false`.

## Verification scope

Synthetic numerical tests check release ordering, exact constant-U drag
relaxation, delayed playback, deterministic multi-source runs, source enablement,
occupied-voxel validation, boundary-contact accounting, cancellation, stale
provenance, strict JSON, exclusive creation, trajectory replay and tamper
rejection. Such fixtures are unit tests, not genuine CFD execution evidence.
See `PROJECT_STATE.md` for the current session's executed commands and results.
