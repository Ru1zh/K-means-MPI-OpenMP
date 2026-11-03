# 十一月图表指南

[English](FIGURE_GUIDE.md) · [한국어](FIGURE_GUIDE.ko.md)

图表**等待真实实测**。绘图代码为 `scripts/plot_rubric.py`，绘图前先验收完整归档。在仓库根目录运行：

```sh
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
```

新输出目录包含下列文件名主体，每张都有 `.png`、`.pdf`、`.svg`，始终生成 SVG：

| 图 | 文件名主体 | 内容 |
|---|---|---|
| 1 | `figure-1-serial` | N/D/K 单参数扫描与 O(INKD) 归一化耗时 |
| 2 | `figure-2-strong` | 耗时、两个基线的加速比/效率、单节点边界 |
| 3 | `figure-3-weak` | 耗时、T1/TP 效率、P×T1/TP 吞吐加速比 |
| 4 | `figure-4-communication` | 普通耗时与独立关键 rank 阶段堆叠 |
| 5 | `figure-5-hybrid` | 固定 256 核布局，以及相对纯 MPI 时间变化 |
| 6 | `figure-6-gpu` | 同作业内 CPU1/CPU8/GPU1 循环与端到端耗时 |

精确表为 `statistics.csv`、`profiles.csv` 和各 suite CSV，英文图注为 `captions.txt`。实际文件尚未生成，不添加悬空结果链接；真实输出审阅后，保留三种格式并补充实际链接。SVG 用于可编辑矢量，PDF 用于发表/导出，高清 PNG 便于插入 Word/Google Docs。

普通误差范围是五次最小–最大值，不是置信区间。诊断堆叠保留真实中位内核样本中关键 rank 的完整向量。MPI 包含等待；CUDA events 属于独立诊断，不能代替同步后的完整循环/端到端计时。详见[完整方法与报告框架](../../RUBRIC_GUIDE.zh-CN.md)。
