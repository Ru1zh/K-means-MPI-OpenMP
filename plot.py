#!/usr/bin/env python3
"""Plot V2/V3 results from timing_summary.csv."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COLORS = {"v2": "#4477AA", "v3": "#EE7733"}


def save_figure(fig, output_dir, name):
    fig.savefig(
        output_dir / f"{name}.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or args.input.parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)

    required = {
        "variant", "p", "t", "n", "d", "k", "nodes",
        "iterations", "warmup", "mode", "communication",
        "seed", "skew", "repeats",
        "median_seconds", "min_seconds", "max_seconds",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = df[df["variant"].isin(["v2", "v3"])].copy()
    if df.empty:
        raise ValueError("No V2/V3 measurements found.")

    # Do not silently combine different workloads or environments.
    fixed_columns = [
        "suite", "n", "d", "k", "p", "nodes",
        "iterations", "warmup", "mode", "communication",
        "seed", "skew", "data_fingerprint", "init_indices",
        "compiler", "mpi_version", "omp_places", "omp_proc_bind",
        "binding_note", "binary_sha256", "host", "platform",
        "launcher",
    ]
    for column in fixed_columns:
        if column in df and df[column].nunique(dropna=False) != 1:
            raise ValueError(
                f"Multiple values in '{column}'. "
                "Use a CSV containing one comparable experiment."
            )

    if df.duplicated(["variant", "t"]).any():
        raise ValueError(
            "Duplicate variant/thread rows found. "
            "Select one experiment instead of averaging summaries."
        )

    if not (df["mode"] == "fixed").all():
        raise ValueError("This script expects fixed-work measurements.")

    numeric = [
        "p", "t", "repeats",
        "median_seconds", "min_seconds", "max_seconds",
    ]
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors="raise")

    if not np.isfinite(df[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite numeric values found.")

    if (df[["p", "t", "repeats", "min_seconds"]] <= 0).any().any():
        raise ValueError("P, T, repeats, and execution times must be positive.")

    if (
        (df["min_seconds"] > df["median_seconds"])
        | (df["median_seconds"] > df["max_seconds"])
    ).any():
        raise ValueError("Expected min <= median <= max.")

    thread_sets = {
        variant: set(df.loc[df["variant"] == variant, "t"])
        for variant in ("v2", "v3")
    }
    if thread_sets["v2"] != thread_sets["v3"]:
        raise ValueError("V2 and V3 must have the same thread counts.")

    threads = sorted(thread_sets["v2"])
    if 1 not in threads:
        raise ValueError("T=1 is required for the thread-speedup baseline.")

    rows = {
        variant: (
            df[df["variant"] == variant]
            .set_index("t")
            .loc[threads]
        )
        for variant in ("v2", "v3")
    }

    p = int(df["p"].iloc[0])
    n = int(df["n"].iloc[0])
    d = int(df["d"].iloc[0])
    k = int(df["k"].iloc[0])
    iterations = int(df["iterations"].iloc[0])

    context = (
        f"P={p}, N={n:,}, D={d}, K={k}, "
        f"iterations={iterations}"
    )

    plt.rcParams.update({
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlepad": 12,
        "figure.facecolor": "white",
    })

    # 1. Kernel execution time: median with min/max ranges.
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(threads))
    width = 0.34

    for variant, offset in (("v2", -width / 2), ("v3", width / 2)):
        group = rows[variant]
        median = group["median_seconds"].to_numpy()
        lower = median - group["min_seconds"].to_numpy()
        upper = group["max_seconds"].to_numpy() - median

        bars = ax.bar(
            x + offset,
            median,
            width,
            color=COLORS[variant],
            label=variant.upper(),
            yerr=np.vstack([lower, upper]),
            capsize=4,
            error_kw={"elinewidth": 1.2},
        )
        for bar, value in zip(bars, median):
            ax.annotate(
                f"{value:.3f}",
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(x, [str(t) for t in threads])
    ax.set_xlabel("OpenMP threads per MPI process (T)")
    ax.set_ylabel("Kernel time (seconds)")
    ax.set_title(f"V2 vs V3: Kernel Execution Time\n{context}")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend()
    ax.margins(y=0.18)
    fig.text(
        0.5, 0.02,
        "Bars: median; error bars: minimum–maximum (not confidence intervals)",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save_figure(fig, output_dir, "01_kernel_time")

    # 2. Thread scaling with P fixed.
    fig, ax = plt.subplots(figsize=(8, 5))

    for variant in ("v2", "v3"):
        median = rows[variant]["median_seconds"]
        speedup = median.loc[1] / median

        ax.plot(
            threads,
            speedup,
            marker="o",
            linewidth=2,
            color=COLORS[variant],
            label=variant.upper(),
        )
        for t, value in zip(threads, speedup):
            ax.annotate(
                f"{value:.2f}x",
                (t, value),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )

    ax.plot(
        threads, threads,
        linestyle="--",
        color="gray",
        label="Ideal thread scaling",
    )
    ax.set_xticks(threads)
    ax.set_xlabel("OpenMP threads per MPI process (T)")
    ax.set_ylabel("Speedup relative to T=1 of the same variant")
    ax.set_title(f"Thread Scaling at Fixed MPI Process Count\n{context}")
    ax.grid(alpha=0.25)
    ax.legend()
    ax.margins(y=0.12)
    fig.tight_layout()
    save_figure(fig, output_dir, "02_thread_scaling")

    # 3. V3 speedup over V2 at matching thread counts.
    v2 = rows["v2"]["median_seconds"].to_numpy()
    v3 = rows["v3"]["median_seconds"].to_numpy()
    relative_speedup = v2 / v3

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        x,
        relative_speedup,
        width=0.55,
        color=COLORS["v3"],
    )
    ax.axhline(
        1.0, linestyle="--", color="gray",
        label="Equal performance",
    )
    for bar, value in zip(bars, relative_speedup):
        ax.annotate(
            f"{value:.2f}x",
            (bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
        )

    ax.set_xticks(x, [str(t) for t in threads])
    ax.set_xlabel("OpenMP threads per MPI process (T)")
    ax.set_ylabel("V3 speedup over V2 (V2 time / V3 time)")
    ax.set_title(f"Relative Performance of V3\n{context}")
    ax.set_ylim(0, max(1.0, relative_speedup.max()) * 1.2)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend()
    fig.tight_layout()
    save_figure(fig, output_dir, "03_v3_speedup")

    # Save the derived values used in the plots.
    comparison = pd.DataFrame({
        "p": p,
        "t": threads,
        "q": p * np.asarray(threads),
        "v2_median_seconds": v2,
        "v3_median_seconds": v3,
        "v3_speedup_over_v2": relative_speedup,
        "time_reduction_percent": (1 - v3 / v2) * 100,
        "v2_thread_speedup": v2[0] / v2,
        "v3_thread_speedup": v3[0] / v3,
        "v2_thread_efficiency": (v2[0] / v2) / np.asarray(threads),
        "v3_thread_efficiency": (v3[0] / v3) / np.asarray(threads),
    })
    comparison.to_csv(output_dir / "comparison.csv", index=False)

    print(f"Saved figures and comparison.csv to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()