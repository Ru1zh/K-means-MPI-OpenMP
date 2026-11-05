# Vanda 实验证据索引

[English](CAMPAIGN_INDEX.md) · [中文](CAMPAIGN_INDEX.zh-CN.md) · [한국어](CAMPAIGN_INDEX.ko.md)

六个作业均已完成并验收：**275 条普通计时、75 条独立诊断**。封存归档保留源码快照、PBS/作业输出、资源与数值预检、绑核、原始 JSONL、每次调用 stdout/stderr、完成清单。`evidence-sha256.json` 核对全部证据文件。现有归档用 `--verify-only`，不重复 `--seal`。

```sh
python3 scripts/reproduce_rubric.py --verify-only
```

[Guide](../../RUBRIC_GUIDE.zh-CN.md) · [Results](../../analysis/rubric-202611/RESULTS.zh-CN.md)
