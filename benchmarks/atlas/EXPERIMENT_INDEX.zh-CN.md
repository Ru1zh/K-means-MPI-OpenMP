# 已记录的 Atlas 实验

[English](EXPERIMENT_INDEX.md) | [简体中文](EXPERIMENT_INDEX.zh-CN.md) | [한국어](EXPERIMENT_INDEX.ko.md)

五组性能实验统一使用同一目录结构。旧四组在 2026-10-25 归档，固定 P=2 实验在 2026-10-27 合并。原始 runs 文件及历史源码包逐字节保留，索引、清单和校验表随目录合并更新。原始下载仍保留在项目的 HPC 目录。

```text
atlas/
  manifest.json
  checksums.sha256
  runs/
    atlas-validation.1027219.venus01/
    atlas-strong.1027222.venus01/
    atlas-hybrid.1027229.venus01/
    atlas-threads.1027231.venus01/
    atlas-communication.1027272.venus01/
    atlas-thread-scaling.1028185.venus01/
  source-packages/
    project3-atlas-<study>.tar.gz
```

| Study | Job ID | Ordinary observations | Raw measurements |
|---|---|---:|---|
| 强扩展 | 1027222.venus01 | 35 | [strong.jsonl](runs/atlas-strong.1027222.venus01/strong.jsonl) |
| 固定 12 核混合并行 | 1027229.venus01 | 30 | [hybrid.jsonl](runs/atlas-hybrid.1027229.venus01/hybrid.jsonl) |
| V2/V3 线程策略 | 1027231.venus01 | 30 | [raw.jsonl](runs/atlas-threads.1027231.venus01/raw.jsonl) |
| 通信策略 | 1027272.venus01 | 30 | [raw.jsonl](runs/atlas-communication.1027272.venus01/raw.jsonl) |
| 固定 P=2 线程扩展 | 1028185.venus01 | 50 | [timing.jsonl](runs/atlas-thread-scaling.1028185.venus01/timing.jsonl) |

175 条普通性能测量；50 条独立阶段诊断另计。验证/pilot 与最新 20 次小数据预检不计入普通性能测量。

N=1,000,000; D=32; K=32; seed=42; 20 timed iterations; 2 warmups; 5 repeats/configuration.

一次命令复核全部五组。只检查文件完整性使用 --verify-only；完整复核在新目录重算，原始记录不变。最新实验的专门入口仍可用于单项复核。

```sh
python3 -B scripts/reproduce_atlas.py --verify-only
python3 -B scripts/reproduce_atlas.py --output artifacts/atlas-audit-new
# Optional single-study entry point:
python3 -B scripts/reproduce_atlas_thread_scaling.py --output artifacts/thread-scaling-audit-new
```

最新一组的阶段数据为 profile.jsonl，普通计时为 timing.jsonl。每条诊断使用同次测量的内核最慢 rank 的全部阶段，不能把诊断并入普通计时。缺失 PBS 快照/外层日志和二进制未下载的限制见 manifest.json 中该作业条目。

说明与结果见 [统一报告结果](../../analysis/atlas/report_results.zh-CN.md) 和 [固定 P=2 说明](../../analysis/atlas/THREAD_SCALING.zh-CN.md)。
