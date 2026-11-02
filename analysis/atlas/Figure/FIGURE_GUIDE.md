# Atlas report figures and tables

Open [the figure overview](../overview.png) or
[English results, captions and tables](../report_results.en.md).

The five figures are available as 300 dpi PNG, vector PDF and editable-text SVG:

| Figure | PNG | Vector PDF | Vector SVG |
| --- | --- | --- | --- |
| Strong-scaling runtime | [PNG](01_strong_runtime.png) | [PDF](01_strong_runtime.pdf) | [SVG](01_strong_runtime.svg) |
| Speedup and efficiency | [PNG](02_strong_scaling.png) | [PDF](02_strong_scaling.pdf) | [SVG](02_strong_scaling.svg) |
| Fixed 12-core layouts | [PNG](03_hybrid_layouts.png) | [PDF](03_hybrid_layouts.pdf) | [SVG](03_hybrid_layouts.svg) |
| V2/V3 accumulation | [PNG](04_thread_strategies.png) | [PDF](04_thread_strategies.pdf) | [SVG](04_thread_strategies.svg) |
| Communication strategies | [PNG](05_communication.png) | [PDF](05_communication.pdf) | [SVG](05_communication.svg) |

Individual figure files are stored in `analysis/atlas/Figure/` (capital F), alongside this guide; the contact-sheet preview remains at `analysis/atlas/overview.png`. Regenerated outputs use the same layout.

Figure 2 uses full-scale speedup above a zoomed efficiency panel (90–106%); endpoint labels sit in white callouts with leader lines. Figure 3 uses vertical boxplots with all five observations overlaid; boxes span the first to third quartile, black lines mark medians, and whiskers span the observed minimum/maximum. Figure 5 uses a horizontal time plot. Both time plots explicitly label their non-zero axis limits and retain the complete observed ranges. Printed median values and percentage changes make small differences readable without implying statistical significance.

## Reproduce

Figure rendering requires Python 3.9+ and the optional Matplotlib dependency:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

Run these commands from the repository root. The checked-in `analysis/atlas/`
already exists, so use a new output directory when regenerating. Existing
outputs and the archived evidence are never overwritten. To derive only tables
and text, Python 3.8+ and the standard library are sufficient:

```sh
python3 scripts/plot_atlas.py --tables-only --output artifacts/atlas-tables-new
```

The script validates the archived SHA-256 inventory and checks workloads,
configuration coverage, repeated runs, data identity and numerical consistency.
For the separate, full audit of placement/source evidence:

```sh
python3 scripts/reproduce_atlas.py --output artifacts/atlas-full-audit-new
```

## Data and definitions

- Source: the four formal jobs in `benchmarks/atlas/manifest.json`; 125 measurements
  in 25 configurations, with five repeats each. Validation/pilot timings are excluded.
- Metric: `kernel_seconds`, not total job time or external launch time.
- Dots: individual repeats. Diamonds: medians where used; Figure 3 uses black median lines.
  Figure 3 boxes show the middle 50% of observations. Whiskers/bands: observed min/max,
  **not confidence intervals**. No significance test or fitted scaling model is used.
- Strong speedup: V0 median / V3 median. Efficiency: speedup / (P × T).
  The additional baseline is explicitly labelled V3 P=1. Ratio bands hold the
  reference median fixed and do not include reference uncertainty.
- Fixed-resource layout and strategy comparisons use only measurements from
  their own job. Their relative time changes are not strong-scaling efficiencies.
- Only strong-scaling P=12 uses two sockets; hybrid and communication studies
  stay on one socket. The thread-strategy job spans two sockets while each
  tested rank stays on one socket. Preserve these conditions in the report.

`configuration_summary.csv` retains all five times and exact per-configuration
statistics. `comparison_summary.csv` names each reference and records speedup,
time change and applicable efficiency. Fixed-resource efficiency cells are blank.
`statistics.json` contains full numerical values. `provenance.json` records Python,
Matplotlib and source-script/input hashes. The checked-in files were rendered
with Matplotlib 3.9.4; PNG layout may differ slightly with another platform/font stack.

## Fixed-P=2 additions

Two additional figures share this Figure directory with the five originals. Ordinary observations total 175; 50 profiles remain separate. The overview.png montage shows the original five figures only.

- [Fixed-P timing and speedup](thread-scaling-performance.png) · [SVG](thread-scaling-performance.svg)
- [Independent phase diagnosis](thread-scaling-phases.png) · [SVG](thread-scaling-phases.svg)
- [Details](../THREAD_SCALING.md)
