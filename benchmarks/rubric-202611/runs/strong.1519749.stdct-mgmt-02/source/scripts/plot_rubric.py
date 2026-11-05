#!/usr/bin/env python3
"""Six English report figures; min/max ranges, same-job baselines, PNG/PDF/SVG."""
import math
from pathlib import Path


def plot(output, rows, profiles):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titlepad': 12, 'savefig.dpi': 220})
    output = Path(output)
    colors = {'v0': '#475569', 'v1': '#2563eb', 'v2': '#e87916', 'v3': '#0f8a71', 'v4': '#8b5cf6'}
    def save(fig, name):
        for extension in ('png', 'pdf', 'svg'):
            fig.savefig(output / (name + '.' + extension), bbox_inches='tight')
        plt.close(fig)
    def line(ax, data, x, y='median_seconds', label=None, color='#2563eb', errors=False):
        data = sorted(data, key=lambda r: r[x])
        xx, yy = [r[x] for r in data], [r[y] for r in data]
        err = [[r['median_seconds'] - r['min_seconds'] for r in data],
               [r['max_seconds'] - r['median_seconds'] for r in data]] if errors else None
        ax.errorbar(xx, yy, yerr=err, marker='o', markersize=5, capsize=3,
                    color=color, linewidth=1.6, label=label)
        ax.grid(axis='y', alpha=.2)
    def logp(ax, data):
        ax.set_xscale('log', base=2)
        ticks = sorted({r['p'] for r in data})
        ax.set_xticks(ticks, [str(x) for x in ticks])
        ax.set_xlabel('MPI ranks P (one CPU core per rank)')
    def bars(ax, data, labels, total=False):
        field = 'median_total_seconds' if total else 'median_seconds'
        lo = 'min_total_seconds' if total else 'min_seconds'
        hi = 'max_total_seconds' if total else 'max_seconds'
        xx = list(range(len(data)))
        ax.bar(xx, [r[field] for r in data], color=[colors[r['variant']] for r in data], width=.65)
        ax.errorbar(xx, [r[field] for r in data],
                    yerr=[[r[field] - r[lo] for r in data], [r[hi] - r[field] for r in data]],
                    fmt='none', ecolor='#111827', capsize=3)
        ax.set_xticks(xx, labels)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
        ax.set_ylabel('End-to-end seconds' if total else 'Timed-loop seconds')
    serial = [r for r in rows if r['suite'] == 'serial']
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.5), constrained_layout=True)
    for col, (x, fixed, title) in enumerate((('n', dict(d=32, k=32), 'Sample count N'),
                                           ('d', dict(n=1000000, k=32), 'Dimensions D'),
                                           ('k', dict(n=1000000, d=32), 'Clusters K'))):
        data = [r for r in serial if all(r[k] == v for k, v in fixed.items())]
        line(axes[0, col], data, x, errors=True)
        line(axes[1, col], data, x, y='seconds_per_inkd', color='#0f8a71')
        for ax in axes[:, col]:
            ax.set_xscale('log', base=2 if x != 'n' else 10)
            ax.set_xlabel(title)
        axes[0, col].set_ylabel('V0 timed-loop seconds')
        axes[1, col].set_ylabel('Seconds / (I N K D)')
    fig.suptitle('Figure 1. Serial problem-size scaling (one factor at a time)')
    save(fig, 'figure-1-serial')
    strong = [r for r in rows if r['suite'] == 'strong' and r['variant'] == 'v1']
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), constrained_layout=True)
    line(axes[0], strong, 'p', errors=True)
    axes[0].set_yscale('log'); axes[0].set_ylabel('Timed-loop seconds (log scale)')
    for field, label, color in (('speedup_serial', 'Relative to same-job V0', '#2563eb'),
                                ('speedup_mpi', 'Relative to V1 / P=1', '#e87916')):
        line(axes[1], strong, 'p', field, label, color)
    for field, label, color in (('efficiency_serial', 'V0 baseline', '#2563eb'),
                                ('efficiency_mpi', 'V1 / P=1 baseline', '#e87916')):
        line(axes[2], strong, 'p', field, label, color)
    axes[1].set_ylabel('Parallel speedup'); axes[2].set_ylabel('Parallel efficiency S/P')
    axes[1].legend(fontsize=8); axes[2].legend(fontsize=8)
    for ax in axes:
        logp(ax, strong)
        ax.axvline(strong[0]['cores_per_node'], color='#64748b', ls=':', label='One-node capacity')
    fig.suptitle('Figure 2. Pure MPI strong scaling; dotted line = one-node capacity C')
    save(fig, 'figure-2-strong')
    weak = sorted([r for r in rows if r['suite'] == 'weak'], key=lambda r: r['p'])
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), constrained_layout=True)
    line(axes[0], weak, 'p', errors=True)
    line(axes[1], weak, 'p', 'weak_efficiency', color='#0f8a71')
    line(axes[2], weak, 'p', 'throughput_speedup', color='#8b5cf6')
    for ax, label in zip(axes, ('Timed-loop seconds', 'Weak efficiency T1 / TP', 'Throughput speedup P T1 / TP')):
        logp(ax, weak); ax.set_ylabel(label)
    axes[1].axhline(1, ls=':', color='#64748b')
    fig.suptitle('Figure 3. Pure MPI weak scaling; 100,000 samples per rank')
    save(fig, 'figure-3-weak')
    comm = sorted([r for r in rows if r['suite'] == 'communication'], key=lambda r: (r['p'], r['communication']))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    bars(axes[0], comm, ['P=%d\n%s' % (r['p'], 'Allreduce' if r['communication'] == 'allreduce' else 'Reduce+Bcast') for r in comm])
    cp = sorted([r for r in profiles if r['suite'] == 'communication'], key=lambda r: (r['p'], r['communication']))
    bottoms = [0.] * len(cp)
    for field, label, color in (('accumulate', 'Local accumulation', '#2563eb'), ('thread_merge', 'Local merge', '#0f8a71'),
                                ('mpi_reduce', 'MPI reduction (includes waiting)', '#e87916'),
                                ('centroid_update', 'Centroid update', '#8b5cf6'), ('control_bcast', 'Control / broadcast', '#64748b')):
        values = [r[field] for r in cp]
        axes[1].bar(range(len(cp)), values, bottom=bottoms, label=label, color=color)
        bottoms = [a + b for a, b in zip(bottoms, values)]
    axes[1].set_xticks(range(len(cp)), ['P=%d\n%s' % (r['p'], r['communication']) for r in cp], fontsize=8)
    axes[1].set_ylabel('Diagnostic seconds\n(one sample / critical rank)')
    axes[1].legend(fontsize=7)
    fig.suptitle('Figure 4. Communication strategies; ordinary timing and independent diagnostics')
    save(fig, 'figure-4-communication')
    hybrid = sorted([r for r in rows if r['suite'] == 'hybrid' and r['variant'] != 'v1'], key=lambda r: (r['t'], r['variant']))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    bars(axes[0], hybrid, ['%d×%d\n%s' % (r['p'], r['t'], r['variant'].upper()) for r in hybrid])
    base = next(r['median_seconds'] for r in rows if r['suite'] == 'hybrid' and r['variant'] == 'v1')
    axes[0].axhline(base, ls='--', color='#475569', label='Same-job V1 / 256 ranks')
    axes[0].legend(fontsize=8)
    for variant, label in (('v2', 'V2 atomic'), ('v3', 'V3 thread-private')):
        line(axes[1], [r for r in hybrid if r['variant'] == variant], 't', 'time_change_percent', label, colors[variant])
    axes[1].axhline(0, ls=':', color='#64748b'); axes[1].legend()
    axes[1].set_xlabel('Threads per rank T (P = 256/T)'); axes[1].set_ylabel('Time change vs. pure MPI (%)')
    fig.suptitle('Figure 5. Fixed 256-core MPI+OpenMP layouts')
    save(fig, 'figure-5-hybrid')
    gpu = sorted([r for r in rows if r['suite'] == 'gpu'], key=lambda r: (r['n'], r['variant']))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    labels = ['N=%gM\n%s' % (r['n'] / 1e6, {'v0': 'CPU 1', 'v3': 'CPU 8', 'v4': 'GPU 1'}[r['variant']]) for r in gpu]
    bars(axes[0], gpu, labels)
    bars(axes[1], gpu, labels, total=True)
    for ax in axes:
        ax.tick_params(axis='x', labelsize=8)
        ax.set_yscale('log')
        ax.set_ylabel(ax.get_ylabel() + ' (log scale)')
    fig.suptitle('Figure 6. One GPU vs. same-job CPU baselines (FP64)')
    save(fig, 'figure-6-gpu')
    captions = [
        'Serial V0: three one-factor sweeps. Lower panels normalize by I*N*K*D; initialization and final evaluation are excluded.',
        'V1/T=1 strong scaling to 256 actual physical CPU cores. Baselines are the same-job V0 and V1/P=1 medians. Dotted vertical line marks C.',
        'Weak scaling fixes 100,000 samples per rank. Weak efficiency is T1/TP; throughput speedup is P*T1/TP. This is not strong-scaling serial speedup.',
        'Allreduce and Reduce+Bcast at P=C and P=256. Diagnostic stacks retain all phases from one actual critical rank of the median-kernel diagnostic sample; MPI includes waiting.',
        'V2 and V3 at P*T=256, with a separately repeated same-job V1/256 baseline. Lower time-change percentages are better.',
        'FP64 V0/CPU1, V3/CPU8 and V4/GPU1 measured in one GPU job. Internal end-to-end time includes generation, setup, warmup, loop and final evaluation; MPI initialization/process launch are excluded.'
    ]
    (output / 'captions.txt').write_text('\n\n'.join('Figure %d. %s' % (i + 1, text) for i, text in enumerate(captions)) +
                                       '\n\nOrdinary points/bars use five repeats: median and observed min–max, not confidence intervals. Diagnostic samples are separate.\n')
