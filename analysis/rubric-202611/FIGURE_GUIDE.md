# November figure guide

[中文](FIGURE_GUIDE.zh-CN.md) · [한국어](FIGURE_GUIDE.ko.md)

Figures are **pending real measurements**. The plotting implementation is `scripts/plot_rubric.py`; full archival validation runs before plotting. From the repository root:

```sh
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
```

The fresh output directory contains the following stems, each with `.png`, `.pdf` and `.svg` (SVG is always generated):

| Figure | Stem | Meaning |
|---|---|---|
| 1 | `figure-1-serial` | N/D/K sweeps plus normalized O(INKD) cost |
| 2 | `figure-2-strong` | Runtime, two baseline speedups and efficiency; one-node boundary |
| 3 | `figure-3-weak` | Runtime, T1/TP efficiency and P×T1/TP throughput speedup |
| 4 | `figure-4-communication` | Ordinary runtime plus independent critical-rank phase stacks |
| 5 | `figure-5-hybrid` | Fixed 256-core layouts and percent change vs pure MPI |
| 6 | `figure-6-gpu` | Same-job CPU1/CPU8/GPU1 loop and end-to-end times |

CSV: `statistics.csv`, `profiles.csv` and one file per suite. English captions: `captions.txt`. No result links are provided until the files actually exist. After collecting and reviewing the real output, keep all three formats here and add links to the actual files. Use SVG for editable vectors, PDF for publication/export, and high-resolution PNG for Word/Google Docs image insertion.

Ordinary error ranges are five-repeat min–max, not confidence intervals. Diagnostic stacks use the complete phase vector of the critical rank from one real median-kernel diagnostic sample. MPI timing includes rank waiting. CUDA events are independent diagnostics, not a substitute for synchronized complete-loop or end-to-end timing. See [full methodology and report blueprint](../../RUBRIC_GUIDE.md).
