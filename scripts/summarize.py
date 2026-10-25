#!/usr/bin/env python3
"""Summarize raw JSONL without combining different workloads or environments."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

# 参数、输入指纹、二进制和环境共同定义可比较的一组，不能只按 P、T 合并时间。
KEYS = ['run_id', 'suite', 'n', 'd', 'k', 'p', 't', 'nodes', 'variant', 'communication',
        'mode', 'seed', 'skew', 'iterations', 'warmup', 'data_fingerprint', 'init_indices',
        'compiler', 'mpi_version', 'omp_places', 'omp_proc_bind', 'binding_note',
        'binary_sha256', 'host', 'platform', 'launcher', 'serial_launcher']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    groups = {}
    seen = set()
    for path in a.inputs:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            # Older runs predate explicit serial launcher/affinity recording.
            row.setdefault('serial_launcher', '')
            # trace/profile 增加额外工作，收敛模式轮数可变，均不能混入固定工作量比较。
            if row['diagnostic'] or row['mode'] != 'fixed':
                raise ValueError('Summary accepts only fixed-work, non-diagnostic measurements')
            if not math.isfinite(row['kernel_seconds']) or row['kernel_seconds'] <= 0:
                raise ValueError('Invalid kernel time')
            key = tuple(json.dumps(row[k], sort_keys=True) for k in KEYS)
            # 同一配置的同一次 repeat 只能计数一次，拒绝重叠输入文件虚增样本量。
            identity = key + (row['repeat'],)
            if identity in seen:
                raise ValueError('Duplicate measurement: overlapping inputs or repeated run/configuration/repeat')
            seen.add(identity)
            groups.setdefault(key, []).append(row)
    if not groups:
        raise ValueError('No measurements')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    columns = KEYS + ['q', 'repeats', 'median_seconds', 'min_seconds', 'max_seconds', 'min_sse', 'max_sse']
    with a.output.open('x', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for rows in groups.values():
            times = [r['kernel_seconds'] for r in rows]
            # 中位数描述典型耗时，范围保留波动信息；同时输出 SSE 范围检查质量变化。
            summary = {k: rows[0][k] for k in KEYS}
            summary.update(q=rows[0]['p'] * rows[0]['t'], repeats=len(rows),
                           median_seconds=statistics.median(times), min_seconds=min(times), max_seconds=max(times),
                           min_sse=min(r['sse'] for r in rows), max_sse=max(r['sse'] for r in rows))
            # Preserve raw JSONL; escape embedded NUL for portable CSV readers.
            writer.writerow({k: v.replace('\x00', r'\0') if isinstance(v, str) else v
                             for k, v in summary.items()})


if __name__ == '__main__':
    main()
