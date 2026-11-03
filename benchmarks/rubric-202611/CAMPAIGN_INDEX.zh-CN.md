# 新评分标准实验证据索引

[English](CAMPAIGN_INDEX.md) · [한국어](CAMPAIGN_INDEX.ko.md)

状态：**等待新 HPC 实测**，未声称已有新耗时或图表。

在 `runs/` 中放入六个完整作业目录，各对应 serial、strong、weak、hybrid、communication、gpu。每个保留 `probe/`、`measurements/`、PBS 和调度输出，普通/诊断文件分开。目标共 275 条普通计时和 75 条独立诊断。

执行、验证、归档、打包见[实验指南](../../RUBRIC_GUIDE.zh-CN.md)。在仓库根目录运行 `python3 scripts/reproduce_rubric.py --status`。只有六个完整作业通过验收后，才用 `--seal --verify-only` 创建 `evidence-sha256.json`；后续核对全部证据文件。源码 ZIP 另有 `PACKAGE-SHA256.json`。

`campaign.json` 是计划矩阵和待完成状态，不是已完成测量清单；未完成真实 HPC 验收前不要标记完成。
