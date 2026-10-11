#!/usr/bin/env bash
# Run the supplied recorder on a package directory inside Docker
# (2 CPUs, no network, no memory cap). Writes benchmark_results.json and
# benchmark_run.log into the directory.
set -euo pipefail

readonly IMAGE="python:3.11-slim"
readonly RESULTS="benchmark_results.json"
readonly RECORD_CMD='python benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json > benchmark_run.log 2>&1; echo rc=$?'

usage() {
  echo "usage: $(basename "$0") <package-dir>" >&2
}

err() {
  echo "run_recorded: $*" >&2
}

main() {
  if (( $# != 1 )); then
    usage
    exit 2
  fi
  if [[ ! -d "$1" ]]; then
    err "not a directory: $1"
    exit 2
  fi
  local dir
  dir="$(cd "$1" && pwd -P)"

  if ! command -v docker > /dev/null 2>&1; then
    err "docker is not installed or not on PATH"
    exit 2
  fi
  if ! docker info > /dev/null 2>&1; then
    err "the Docker daemon is not reachable"
    exit 2
  fi

  local name
  for name in context_solver.py benchmark_runner.py benchmark_inputs.json; do
    if [[ ! -f "${dir}/${name}" ]]; then
      err "missing ${name} in ${dir}"
      exit 2
    fi
  done
  # A leftover results file would hide a failed run; never delete it here.
  if [[ -e "${dir}/${RESULTS}" ]]; then
    err "${RESULTS} already exists in ${dir}; use a fresh directory"
    exit 2
  fi

  # Relative paths only: the recorder stores its argv verbatim.
  docker run --rm --cpus=2 --network none -v "${dir}":/work -w /work \
    "${IMAGE}" sh -c "${RECORD_CMD}"

  find "${dir}" -type d -name __pycache__ -prune -exec rm -rf {} +

  if [[ ! -f "${dir}/${RESULTS}" ]]; then
    err "${RESULTS} was not produced; see ${dir}/benchmark_run.log"
    exit 1
  fi
}

main "$@"
