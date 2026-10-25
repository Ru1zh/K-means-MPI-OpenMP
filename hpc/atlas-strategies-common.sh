#!/bin/bash
# Sourced by the individual PBS scripts; algorithm sources remain shared.
set -eo pipefail
cd "$PBS_O_WORKDIR"
[[ "$ATLAS_STUDY" == threads || "$ATLAS_STUDY" == communication ]]
atlas_results="$PBS_O_WORKDIR/results/atlas-$ATLAS_STUDY.$PBS_JOBID"
mkdir -p "$atlas_results"
trap 'atlas_status=$?; printf "exit_status=%s\n" "$atlas_status" > "$atlas_results/status.txt"' EXIT
source /etc/profile.d/modules.sh
module purge
module load miniconda/4.12
module load openmpi/4.1.2
module load gcc/9.2.0
atlas_cxx=$(command -v g++)
atlas_python=$(command -v python3)
[[ $("$atlas_cxx" -dumpfullversion -dumpversion) == 9.2.0 ]]
export OMPI_CXX="$atlas_cxx"
"$atlas_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else "Python 3.8+ required")'
unset OMP_NUM_THREADS OMP_PLACES OMP_PROC_BIND GOMP_CPU_AFFINITY KMP_AFFINITY
export OMP_DYNAMIC=FALSE
{
  hostname
  module list
  "$atlas_cxx" --version
  mpicxx --showme:command
  mpirun --version
  "$atlas_python" --version
  lscpu
  taskset -pc $$
  cat "$PBS_NODEFILE"
} > "$atlas_results/environment.txt" 2>&1
atlas_process_list="${ATLAS_PROCESS_LIST:-2:4:6}"
atlas_process_list="${atlas_process_list//:/,}"
echo "Study: $ATLAS_STUDY; processes: $atlas_process_list"
sha256sum -c source-manifest.sha256 > "$atlas_results/source-check.txt"
make -B all CXX="$atlas_cxx" MPICXX=mpicxx
"$atlas_cxx" -O2 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp atlas-thread-probe.cpp -o build/atlas-thread-probe
sha256sum build/kmeans_serial build/kmeans_mpi build/atlas-thread-probe > "$atlas_results/binaries.sha256"
"$atlas_python" atlas-affinity.py snapshot --expected-cores 12 > "$atlas_results/allocation.json"
"$atlas_python" atlas-hybrid-launch.py plan "$atlas_results/allocation.json" "$atlas_results/layout-plan.json"
export KMEANS_BINDING_NOTE="Explicit rank masks and OMP places; per-launch placement records; paired $ATLAS_STUDY study"
"$atlas_python" atlas-strategy-study.py --kind "$ATLAS_STUDY" --processes "$atlas_process_list" \
  --directory "$atlas_results" --nodefile "$PBS_NODEFILE"
echo "Study finished. Results: $atlas_results"
