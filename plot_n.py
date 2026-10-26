#!/usr/bin/env python3
"""Visualize V2/V3 performance across sample sizes."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter


COLORS = {"v2": "#4477AA", "v3": "#EE7733"}


def save_figure(fig, output_dir, name):
    for extension in ("png", "pdf"):
        fig.savefig(
            output_dir / f"{name}.{extension}",
            dpi=300,
            bbox_inches="tight",
        )
    plt.close(fig)


def load_results(path):
    df = pd.read_csv(path)

    required = {
        "n", "d", "k", "p", "t", "nodes",
        "variant", "communication", "mode", "seed", "skew",
        "iterations", "warmup", "repeats",
        "median_seconds", "min_seconds", "max_seconds",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = df[df["variant"].isin(["v2", "v3"])].copy()
    if df.empty:
        raise ValueError("No V2/V3 measurements found.")

    numeric_columns = [
        "n", "d", "k", "p", "t", "nodes",
        "iterations", "warmup", "repeats",
        "median_seconds", "min_seconds", "max_seconds",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="raise")

    if not np.isfinite(
        df[numeric_columns].to_numpy(dtype=float)
    ).all():
        raise ValueError("Non-finite numeric values found.")

    integer_columns = [
        "n", "d", "k", "p", "t", "nodes",
        "iterations", "warmup", "repeats",
    ]
    for column in integer_columns:
        if (df[column] % 1 != 0).any():
            raise ValueError(f"Expected integer values in '{column}'.")

    positive_columns = [
        "n", "d", "k", "p", "t", "nodes",
        "iterations", "repeats",
        "median_seconds", "min_seconds", "max_seconds",
    ]
    if (df[positive_columns] <= 0).any().any():
        raise ValueError("Sizes, repeats, and execution times must be positive.")

    if (df["warmup"] < 0).any():
        raise ValueError("Warmup must be nonnegative.")

    if (df["k"] > df["n"]).any():
        raise ValueError("Expected K <= N.")

    if (
        (df["min_seconds"] > df["median_seconds"])
        | (df["median_seconds"] > df["max_seconds"])
    ).any():
        raise ValueError("Expected min <= median <= max.")

    if not (df["mode"] == "fixed").all():
        raise ValueError("Expected fixed-work measurements.")

    # N changes; other experimental conditions should remain fixed.
    fixed_columns = [
        "suite", "d", "k", "p", "t", "nodes",
        "communication", "mode", "seed", "skew",
        "iterations", "warmup",
        "compiler", "mpi_version", "omp_places", "omp_proc_bind",
        "binding_note", "binary_sha256", "host", "platform",
        "launcher",
    ]
    for column in fixed_columns:
        if column in df and df[column].nunique(dropna=False) != 1:
            raise ValueError(
                f"Multiple values in '{column}'. "
                "Select one experiment with fixed conditions."
            )

    if df.duplicated(["n", "variant"]).any():
        raise ValueError(
            "Duplicate N/variant rows found. "
            "Do not average separate summary rows automatically."
        )

    sizes_v2 = set(df.loc[df["variant"] == "v2", "n"])
    sizes_v3 = set(df.loc[df["variant"] == "v3", "n"])
    if sizes_v2 != sizes_v3:
        raise ValueError("V2 and V3 must have matching N values.")

    if len(sizes_v2) < 2:
        raise ValueError("At least two sample sizes are required.")

    # Inputs may differ across N, but must match between V2/V3 at each N.
    for n, group in df.groupby("n"):
        for column in ("data_fingerprint", "init_indices", "run_id"):
            if column in group and group[column].nunique(dropna=False) != 1:
                raise ValueError(
                    f"N={n}: V2/V3 differ in '{column}'. "
                    "Check whether these measurements form a matched comparison."
                )

        if group["repeats"].nunique() != 1:
            raise ValueError(f"N={n}: V2/V3 repeat counts differ.")

    return df.sort_values(["n", "variant"])


def format_n_axis(ax, sizes):
    ax.set_xscale("log")
    ax.set_xticks(sizes)
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value:,.0f}")
    )
    ax.minorticks_off()
    ax.set_xlabel("Number of samples (N)")
    ax.grid(True, which="major", alpha=0.25)
    ax.set_axisbelow(True)
    ax.margins(x=0.10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--linear-y",
        action="store_true",
        help="Use a linear time axis in the execution-time plot.",
    )
    args = parser.parse_args()

    df = load_results(args.input)

    output_dir = args.output_dir or args.input.parent / "figures_by_n"
    output_dir.mkdir(parents=True, exist_ok=True)

    sizes = sorted(df["n"].unique())
    rows = {
        variant: (
            df[df["variant"] == variant]
            .set_index("n")
            .loc[sizes]
        )
        for variant in ("v2", "v3")
    }

    first = df.iloc[0]
    context = (
        f"P={int(first['p'])}, T={int(first['t'])}, "
        f"D={int(first['d'])}, K={int(first['k'])}, "
        f"iterations={int(first['iterations'])}"
    )

    plt.rcParams.update({
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlepad": 12,
        "figure.facecolor": "white",
    })

    # 1. Median kernel times with min/max ranges.
    fig, ax = plt.subplots(figsize=(8, 5.5))

    for variant in ("v2", "v3"):
        group = rows[variant]
        median = group["median_seconds"].to_numpy()
        minimum = group["min_seconds"].to_numpy()
        maximum = group["max_seconds"].to_numpy()

        ax.errorbar(
            sizes,
            median,
            yerr=np.vstack([median - minimum, maximum - median]),
            marker="o",
            markersize=6,
            linewidth=2,
            capsize=4,
            color=COLORS[variant],
            label=variant.upper(),
        )

    format_n_axis(ax, sizes)
    if not args.linear_y:
        ax.set_yscale("log")
    else:
        ax.set_ylim(bottom=0)

    ax.set_ylabel("Median kernel time (seconds)")
    ax.set_title(f"V2 vs V3: Execution Time by Sample Size\n{context}")
    ax.legend()

    fig.text(
        0.5, 0.02,
        "Points: medians; error bars: minimum–maximum, not confidence intervals",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save_figure(fig, output_dir, "01_time_by_n")

    v2 = rows["v2"]["median_seconds"].to_numpy()
    v3 = rows["v3"]["median_seconds"].to_numpy()
    speedup = v2 / v3
    reduction = (1 - v3 / v2) * 100

    # 2. Ratio of median times at the same N.
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        sizes,
        speedup,
        marker="o",
        linewidth=2,
        color=COLORS["v3"],
        label="V2 median time / V3 median time",
    )
    ax.axhline(
        1.0,
        linestyle="--",
        color="gray",
        label="Equal performance",
    )

    for n, value in zip(sizes, speedup):
        ax.annotate(
            f"{value:.2f}x",
            (n, value),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=10,
        )

    format_n_axis(ax, sizes)
    ax.set_ylabel("V3 speedup over V2")
    ax.set_title(f"V3 Relative Performance by Sample Size\n{context}")
    ax.set_ylim(0, max(1.0, speedup.max()) * 1.25)
    ax.legend()
    fig.tight_layout()
    save_figure(fig, output_dir, "02_speedup_by_n")

    # 3. Time reduction relative to V2; negatives mean V3 is slower.
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        sizes,
        reduction,
        marker="o",
        linewidth=2,
        color=COLORS["v3"],
    )
    ax.axhline(0, linestyle="--", color="gray")

    for n, value in zip(sizes, reduction):
        ax.annotate(
            f"{value:.1f}%",
            (n, value),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=10,
        )

    format_n_axis(ax, sizes)
    ax.set_ylabel("Execution time reduction relative to V2 (%)")
    ax.set_title(f"V3 Time Reduction by Sample Size\n{context}")

    lower = min(0.0, float(reduction.min()))
    upper = max(0.0, float(reduction.max()))
    padding = max(5.0, (upper - lower) * 0.20)
    ax.set_ylim(lower - padding, upper + padding)

    fig.tight_layout()
    save_figure(fig, output_dir, "03_time_reduction_by_n")

    comparison = pd.DataFrame({
        "n": sizes,
        "p": int(first["p"]),
        "t": int(first["t"]),
        "q": int(first["p"]) * int(first["t"]),
        "v2_repeats": rows["v2"]["repeats"].to_numpy(),
        "v3_repeats": rows["v3"]["repeats"].to_numpy(),
        "v2_median_seconds": v2,
        "v2_min_seconds": rows["v2"]["min_seconds"].to_numpy(),
        "v2_max_seconds": rows["v2"]["max_seconds"].to_numpy(),
        "v3_median_seconds": v3,
        "v3_min_seconds": rows["v3"]["min_seconds"].to_numpy(),
        "v3_max_seconds": rows["v3"]["max_seconds"].to_numpy(),
        "v3_speedup_over_v2": speedup,
        "time_reduction_percent": reduction,
    })
    comparison.to_csv(
        output_dir / "comparison_by_n.csv",
        index=False,
    )

    print(f"Saved results to: {output_dir.resolve()}")
    print(comparison.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()