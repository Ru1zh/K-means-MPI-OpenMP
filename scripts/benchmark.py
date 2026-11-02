#!/usr/bin/env python3
"""Run interleaved fixed-work experiments. No shell evaluation or third-party packages."""

import argparse
import hashlib
import json
import os
import platform
import random
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def number_list(value):
    try:
        return list(dict.fromkeys(positive(x) for x in value.split(",")))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def configurations(a):
    # Build controlled comparisons only; each suite explicitly fixes specific parameters so the workload cannot change unintentionally.
    base = dict(
        n=a.n, d=a.d, k=a.k, p=1, t=a.threads, variant="v3", communication="allreduce"
    )
    rows = []

    def add(**changes):
        rows.append(dict(base, **changes))

    if a.suite == "serial":
        add(variant="v0", t=1)
    elif a.suite == "strong":
        add(variant="v0", t=1)
        for p in a.processes:
            add(p=p)
    elif a.suite == "weak":
        # N0=a.n: fix samples per process and threads per process, so total sample count grows with P.
        for p in a.processes:
            add(p=p, n=a.n * p)
    elif a.suite == "hybrid":
        # Fix total cores Q=P*T and accept only process counts that divide Q.
        for p in a.processes:
            if a.total_cores % p == 0:
                add(p=p, t=a.total_cores // p)
    elif a.suite in ("threads", "communication", "smoke"):
        for p in a.processes:
            if a.suite == "smoke":
                add(p=p, t=1, variant="v1")
            if a.suite in ("threads", "smoke"):
                add(p=p, variant="v2")
            add(p=p)
            if a.suite in ("communication", "smoke"):
                add(p=p, communication="reduce-bcast")
        if a.suite == "smoke":
            add(variant="v0", t=1)
    elif a.suite == "sensitivity":
        # Each configuration changes exactly one of N, D or K; do not form the Cartesian product of all three.
        for p in a.processes:
            add(p=p)
            for n in a.sample_sizes:
                add(p=p, n=n)
            for d in a.dimensions:
                add(p=p, d=d)
            for k in a.clusters:
                add(p=p, k=k)
    # The argument list may contain a baseline value; deduplicate first so the same configuration is not measured twice by accident and repeats stay meaningful.
    unique = {json.dumps(row, sort_keys=True): row for row in rows}
    if not unique:
        raise ValueError(
            "No valid configurations; check process counts and total cores"
        )
    for row in unique.values():
        if row["k"] > row["n"]:
            raise ValueError("Every configuration requires K <= N")
    return list(unique.values())


def command(a, row):
    # Split the launcher into tokens and substitute resource parameters; run as an argument list so spaces in paths are not split.
    binary = (
        ROOT / "build" / ("kmeans_serial" if row["variant"] == "v0" else "kmeans_mpi")
    )
    launcher = a.serial_launcher if row["variant"] == "v0" else a.launcher
    cmd = [part.format(p=row["p"], t=row["t"]) for part in shlex.split(launcher)]
    cmd += [
        str(binary),
        "--n",
        str(row["n"]),
        "--d",
        str(row["d"]),
        "--k",
        str(row["k"]),
        "--iterations",
        str(a.iterations),
        "--warmup",
        str(a.warmup),
        "--seed",
        str(a.seed),
        "--threads",
        str(row["t"]),
        "--variant",
        row["variant"],
        "--comm",
        row["communication"],
    ]
    if a.skew:
        cmd.append("--skew")
    return cmd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--suite",
        choices=[
            "serial",
            "smoke",
            "strong",
            "weak",
            "hybrid",
            "threads",
            "communication",
            "sensitivity",
        ],
        default="smoke",
    )
    p.add_argument("--n", type=positive, default=10000)
    p.add_argument("--d", type=positive, default=8)
    p.add_argument("--k", type=positive, default=16)
    p.add_argument("--threads", type=positive, default=2)
    p.add_argument("--processes", type=number_list, default=[1, 2, 4])
    p.add_argument("--total-cores", type=positive, default=4)
    p.add_argument("--sample-sizes", type=number_list, default=[10000, 100000, 1000000])
    p.add_argument("--dimensions", type=number_list, default=[8, 32, 128])
    p.add_argument("--clusters", type=number_list, default=[8, 32, 128])
    p.add_argument("--iterations", type=positive, default=50)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--repeats", type=positive, default=5)
    p.add_argument("--order-seed", type=int, default=2026)
    p.add_argument("--timeout", type=positive, default=3600)
    p.add_argument(
        "--launcher",
        default="mpiexec -n {p}",
        help="tokenized command, placeholders {p}, {t}; no shell",
    )
    p.add_argument(
        "--serial-launcher", default="",
        help="optional serial command prefix, e.g. taskset -c 40; no shell",
    )
    p.add_argument("--output", type=Path, default=Path("results/raw.jsonl"))
    p.add_argument("--skew", action="store_true")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print each unique command once, without executing",
    )
    a = p.parse_args()
    if a.warmup < 0 or not 0 <= a.seed < 2**64:
        p.error("warmup must be nonnegative; seed must fit uint64")
    rows = configurations(a)
    if a.dry_run:
        for row in rows:
            print(json.dumps(dict(row, command=command(a, row))))
        return
    a.output.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.order_seed)
    run_id = str(uuid.uuid4())
    # Exclusive creation protects previous measurements from accidental overwrite.
    # Keep multiple context managers compatible with Atlas's Python 3.8.
    with a.output.open("x") as output, a.output.with_suffix(".stderr.log").open("x") as log:
        for repeat in range(a.repeats):
            order = rows.copy()
            # Each batch covers all configurations in shuffled order to reduce drift from system state changing over time.
            rng.shuffle(order)
            for row in order:
                cmd = command(a, row)
                print(f"[{repeat + 1}/{a.repeats}] {shlex.join(cmd)}", file=sys.stderr)
                start = time.perf_counter()
                proc = subprocess.run(
                    cmd, text=True, capture_output=True, timeout=a.timeout
                )
                # Stop the external timer immediately here to exclude subsequent logging, parsing and binary hashing.
                launch_seconds = time.perf_counter() - start
                log.write(shlex.join(cmd) + "\n" + proc.stderr + "\n")
                log.flush()
                if proc.returncode:
                    raise RuntimeError(
                        f"Command failed ({proc.returncode}); see {log.name}"
                    )
                result = json.loads(proc.stdout)
                if result["diagnostic"] or result["iterations"] != a.iterations:
                    raise RuntimeError("Unexpected workload or diagnostic run")
                for key in ["n", "d", "k", "p", "t", "variant", "communication"]:
                    # Check the actual execution result so a launcher misconfiguration cannot be recorded as the target configuration.
                    if result[key] != row[key]:
                        raise RuntimeError(f"Launcher/configuration mismatch: {key}")
                binary = Path(cmd[cmd.index("--n") - 1])
                result.update(
                    suite=a.suite,
                    repeat=repeat,
                    run_id=run_id,
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    host=platform.node(),
                    platform=platform.platform(),
                    command=cmd,
                    launcher=a.launcher,
                    serial_launcher=a.serial_launcher,
                    order_seed=a.order_seed,
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    launch_seconds=launch_seconds,
                    job_id=os.environ.get(
                        "SLURM_JOB_ID", os.environ.get("PBS_JOBID", "unset")
                    ),
                )
                output.write(json.dumps(result, allow_nan=False) + "\n")
                # Flush each run past the Python file buffer so completed records survive later failures.
                output.flush()


if __name__ == "__main__":
    main()
