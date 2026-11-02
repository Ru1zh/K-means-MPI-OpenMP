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
    # 仅构造受控对照；每种 suite 明确保持哪些参数不变，避免无意改变工作量。
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
        # N0=a.n，固定每进程样本数和线程数，随 P 增大总样本数。
        for p in a.processes:
            add(p=p, n=a.n * p)
    elif a.suite == "hybrid":
        # 固定总核数 Q=P*T，只接受能够整除 Q 的进程数。
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
        # 每条配置只修改 N、D、K 中一个参数，不做三者的笛卡尔积。
        for p in a.processes:
            add(p=p)
            for n in a.sample_sizes:
                add(p=p, n=n)
            for d in a.dimensions:
                add(p=p, d=d)
            for k in a.clusters:
                add(p=p, k=k)
    # 参数列表可能含基准值，先去重，避免同一配置被意外多测而影响重复次数。
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
    # 启动器按 token 拆分并替换资源参数；以参数列表运行，路径中的空格不会被拆开。
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
            # 每批都覆盖全部配置并打乱顺序，减轻系统状态随时间变化造成的偏差。
            rng.shuffle(order)
            for row in order:
                cmd = command(a, row)
                print(f"[{repeat + 1}/{a.repeats}] {shlex.join(cmd)}", file=sys.stderr)
                start = time.perf_counter()
                proc = subprocess.run(
                    cmd, text=True, capture_output=True, timeout=a.timeout
                )
                # 此处立即停止外部计时，排除后续日志、解析和二进制哈希的开销。
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
                    # 核对实际执行结果，避免启动器资源配置错误却记录为目标配置。
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
                # 每次运行后落到 Python 文件缓冲之外，后续失败时仍保留已完成记录。
                output.flush()


if __name__ == "__main__":
    main()
