# Vanda 报告图表指南

[English](FIGURE_GUIDE.md) · [中文](FIGURE_GUIDE.zh-CN.md) · [한국어](FIGURE_GUIDE.ko.md)

全部图表使用已验收的真实 Vanda 测量。下列链接为适合论文栏宽、字号更大的版本；原始大图和精确表仍在 `verified-20261105/`。

| Figure | Content | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | 串行 N/D/K 规模 | [PNG](paper-figures/figure-1-serial.png) | [PDF](paper-figures/figure-1-serial.pdf) | [SVG](paper-figures/figure-1-serial.svg) |
| 2 | 纯 MPI 强扩展 | [PNG](paper-figures/figure-2-strong.png) | [PDF](paper-figures/figure-2-strong.pdf) | [SVG](paper-figures/figure-2-strong.svg) |
| 3 | 纯 MPI 弱扩展 | [PNG](paper-figures/figure-3-weak.png) | [PDF](paper-figures/figure-3-weak.pdf) | [SVG](paper-figures/figure-3-weak.svg) |
| 4 | 通信与阶段计时 | [PNG](paper-figures/figure-4-communication.png) | [PDF](paper-figures/figure-4-communication.pdf) | [SVG](paper-figures/figure-4-communication.svg) |
| 5 | 固定 256 核 MPI+OpenMP | [PNG](paper-figures/figure-5-hybrid.png) | [PDF](paper-figures/figure-5-hybrid.pdf) | [SVG](paper-figures/figure-5-hybrid.svg) |
| 6 | 同作业内 CPU/GPU 对照 | [PNG](paper-figures/figure-6-gpu.png) | [PDF](paper-figures/figure-6-gpu.pdf) | [SVG](paper-figures/figure-6-gpu.svg) |

[Exact statistics](verified-20261105/statistics.csv) · [Independent phases](verified-20261105/profiles.csv) · [Captions](verified-20261105/captions.txt)

```sh
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py --output artifacts/paper-figures-new
```

普通误差线为五次实测最小–最大值，不是置信区间。诊断堆叠使用某次实际关键 rank 的完整阶段，不拼接各 rank 的独立最大值。MPI 包含等待；论文排图不新增计时，也不修改测量值。
