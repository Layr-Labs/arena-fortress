#!/bin/bash
# make_default_fort.sh: build the default start fort from its seed, for a checkout without fort_start_snapshot's save.
#
#   embark/make_default_fort.sh [--out DIR] [--force]      # inside the image; ~1.5 min on the Mac (Rosetta)
#
# fort_start_snapshot's world (PINNED POCKET, world seed 12345) embarked at its site (world tile (4,5), local (8,8))
# with "Play now!": embark/make_embark.sh with embark/rules/DEFAULT_FORT.json. Writes
# scenarios/snapshots/embark-default-fort-12345/, which reset_fort.sh and smoke.py load when fort_start_snapshot/
# has no world.sav (bench/key.py start_snapshot). On the host, `docker/embark.sh --rules DEFAULT_FORT --seeds 12345`
# makes the same directory; rebuild the image to bake it in. What matches the legacy save and what doesn't:
# docs/SEED-FORTS.md §6.
set -u
DFP=$(cd "$(dirname "$0")/.." && pwd -P)
OUT=$DFP/scenarios/snapshots/embark-default-fort-12345 FORCE=
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT=$2; shift 2;;
    --force) FORCE=1; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
if [ -f "$OUT/world.sav" ] && [ -z "$FORCE" ]; then echo "EXISTS $OUT (--force to rebuild)"; exit 0; fi
mkdir -p "$DFP/df/save"
exec "$DFP/embark/make_embark.sh" --seed 12345 --rules "$DFP/embark/rules/DEFAULT_FORT.json" --out "$OUT"
