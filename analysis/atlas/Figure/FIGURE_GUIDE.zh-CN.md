# Atlas 报告图表

[English](FIGURE_GUIDE.md) | [简体中文](FIGURE_GUIDE.zh-CN.md) | [한국어](FIGURE_GUIDE.ko.md)

打开[图表总览](../overview.png)或
[中文结果、图注和表格](../report_results.zh-CN.md)。

五幅图均提供 300 dpi PNG、矢量 PDF 和文字可编辑的 SVG：

| 图 | PNG | 矢量 PDF | 矢量 SVG |
| --- | --- | --- | --- |
| 强扩展运行时间 | [PNG](01_strong_runtime.png) | [PDF](01_strong_runtime.pdf) | [SVG](01_strong_runtime.svg) |
| 加速比与效率 | [PNG](02_strong_scaling.png) | [PDF](02_strong_scaling.pdf) | [SVG](02_strong_scaling.svg) |
| 固定 12 核布局 | [PNG](03_hybrid_layouts.png) | [PDF](03_hybrid_layouts.pdf) | [SVG](03_hybrid_layouts.svg) |
| V2/V3 累加 | [PNG](04_thread_strategies.png) | [PDF](04_thread_strategies.pdf) | [SVG](04_thread_strategies.svg) |
| 通信策略 | [PNG](05_communication.png) | [PDF](05_communication.pdf) | [SVG](05_communication.svg) |

各图文件存放于 `analysis/atlas/Figure/`（F 大写），与本指南同目录；拼图预览仍位于 `analysis/atlas/overview.png`。重新生成的输出沿用相同布局。

图 2 上方为完整尺度的加速比，下方为放大的效率面板（90–106%）；端点标签位于带引导线的白色标注框中。
图 3 使用竖直箱线图，并叠加全部五次观测；箱体覆盖第一至第三四分位数，黑线表示中位数，须线覆盖观测到的最小值至最大值。
图 5 使用水平时间图。两幅时间图均明确标出非零坐标轴界限，并保留完整观测范围。
标出的中位数和百分比变化让微小差异更易读，但不暗示统计显著性。

## 复现

渲染图表需要 Python 3.9+ 和可选的 Matplotlib 依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

请从仓库根目录运行这些命令。已检入的 `analysis/atlas/` 目录已经存在，因此重新生成时请使用新的输出目录。
现有输出和归档证据始终不会被覆盖。若只生成表格和文本，Python 3.8+ 及其标准库即可：

```sh
python3 scripts/plot_atlas.py --tables-only --output artifacts/atlas-tables-new
```

脚本会验证归档 SHA-256 清单，并检查工作负载、配置覆盖、重复运行、数据身份和数值一致性。
若需单独执行完整的进程放置/源代码证据审计：

```sh
python3 scripts/reproduce_atlas.py --output artifacts/atlas-full-audit-new
```

## 数据与定义

- 来源：`benchmarks/atlas/manifest.json` 中的四个正式作业；共 25 种配置、125 次测量，每种配置重复五次。排除验证/试运行的计时数据。
- 指标：`kernel_seconds`，不是作业总时间，也不是外部启动时间。
- 圆点：单次重复。使用菱形时，菱形表示中位数；图 3 用黑色中位数线。
  图 3 的箱体表示中间 50% 的观测。须线/带状范围：观测到的最小值/最大值，**不是置信区间**。
  未进行显著性检验，也未拟合扩展模型。
- 强扩展加速比：V0 中位数 / V3 中位数。效率：加速比 / (P × T)。
  额外基线明确标为 V3 P=1。比值带固定参考中位数，不包含参考值的不确定性。
- 固定资源布局及策略比较只使用各自作业内的测量值。其相对时间变化不是强扩展效率。
- 只有强扩展的 P=12 配置使用两个 CPU 插槽；混合并行与通信研究均在单插槽内运行。
  线程策略作业跨两个插槽，但每个被测 MPI rank 均位于单个插槽内。报告中应保留这些条件。

`configuration_summary.csv` 保留全部五次耗时和每种配置的精确统计量。
`comparison_summary.csv` 标明每项参考，并记录加速比、时间变化及适用的效率；固定资源比较的效率单元格留空。
`statistics.json` 包含完整数值。`provenance.json` 记录 Python、Matplotlib 以及源脚本/输入的哈希。
已检入文件使用 Matplotlib 3.9.4 渲染；其他平台或字体组合下的 PNG 布局可能略有差异。

## 固定 P=2 新增图

新增两张图已与原五张图统一保存在本 Figure 目录。普通性能测量总计 175 条，50 条阶段诊断另计。overview.png 保留原五图的历史拼图。

- [Fixed-P timing and speedup](thread-scaling-performance.png) · [SVG](thread-scaling-performance.svg)
- [Independent phase diagnosis](thread-scaling-phases.png) · [SVG](thread-scaling-phases.svg)
- [Details](../THREAD_SCALING.zh-CN.md)
