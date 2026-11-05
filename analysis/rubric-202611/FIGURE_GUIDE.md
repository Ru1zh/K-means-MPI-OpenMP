# Vanda report figure guide

[English](FIGURE_GUIDE.md) · [中文](FIGURE_GUIDE.zh-CN.md) · [한국어](FIGURE_GUIDE.ko.md)

All figures use the verified real Vanda measurements. The links below point to the report-size versions with larger labels. The original full-size plots and exact tables remain in `verified-20261105/`.

| Figure | Content | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | Serial N/D/K scaling | [PNG](paper-figures/figure-1-serial.png) | [PDF](paper-figures/figure-1-serial.pdf) | [SVG](paper-figures/figure-1-serial.svg) |
| 2 | Pure MPI strong scaling | [PNG](paper-figures/figure-2-strong.png) | [PDF](paper-figures/figure-2-strong.pdf) | [SVG](paper-figures/figure-2-strong.svg) |
| 3 | Pure MPI weak scaling | [PNG](paper-figures/figure-3-weak.png) | [PDF](paper-figures/figure-3-weak.pdf) | [SVG](paper-figures/figure-3-weak.svg) |
| 4 | Communication and phase timing | [PNG](paper-figures/figure-4-communication.png) | [PDF](paper-figures/figure-4-communication.pdf) | [SVG](paper-figures/figure-4-communication.svg) |
| 5 | Fixed-256-core MPI+OpenMP | [PNG](paper-figures/figure-5-hybrid.png) | [PDF](paper-figures/figure-5-hybrid.pdf) | [SVG](paper-figures/figure-5-hybrid.svg) |
| 6 | Same-job CPU/GPU comparison | [PNG](paper-figures/figure-6-gpu.png) | [PDF](paper-figures/figure-6-gpu.pdf) | [SVG](paper-figures/figure-6-gpu.svg) |

[Exact statistics](verified-20261105/statistics.csv) · [Independent phases](verified-20261105/profiles.csv) · [Captions](verified-20261105/captions.txt)

```sh
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py --output artifacts/paper-figures-new
```

Ordinary error bars are five-repeat observed min–max, not confidence intervals. Diagnostic stacks use all phases of one actual critical rank, never independent rank maxima. MPI includes waiting. No new timing or altered observations are introduced by report formatting.
