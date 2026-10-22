#!/usr/bin/env bash
# Run a command in a verified Foundation v10 environment. Its interactive
# startup scripts contain optional probes that are incompatible with errexit.
set -eo pipefail

if (( $# == 0 )); then
    echo "Usage: bash scripts/with_openfoam10.sh COMMAND [ARG ...]" >&2
    exit 2
fi

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! command -v python3 > /dev/null; then
    echo "Python 3.11+ is required inside Linux/WSL to discover and run CleanroomX CFD." >&2
    exit 2
fi
foam_bashrc=$(python3 "$script_root/../src/cleanroomx/openfoam_runtime.py" --select) || exit 2
if [[ ! -r "$foam_bashrc" ]]; then
    echo "Cannot read OpenFOAM Foundation v10 environment: $foam_bashrc" >&2
    exit 1
fi
printf 'CleanroomX OpenFOAM environment: %s\n' "$foam_bashrc" >&2

load_openfoam_environment() {
    # A function with no arguments keeps COMMAND out of OpenFOAM's settings.
    source "$foam_bashrc"
}
set +e
load_openfoam_environment
source_status=$?
set -e
if (( source_status != 0 )); then
    echo "OpenFOAM environment initialization failed ($source_status)" >&2
    exit "$source_status"
fi

for executable in blockMesh checkMesh simpleFoam postProcess; do
    if ! command -v "$executable" > /dev/null; then
        echo "Required OpenFOAM executable is missing: $executable" >&2
        exit 1
    fi
done
if ! runtime_help=$(simpleFoam -help 2>&1); then
    printf '%s\n' "$runtime_help" >&2
    exit 1
fi
if [[ ! "$runtime_help" =~ Using:\ OpenFOAM-10[[:space:]] ]]; then
    echo "Expected OpenFOAM Foundation v10; refusing a different runtime" >&2
    exit 1
fi

exec "$@"
