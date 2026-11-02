#!/usr/bin/env python3
"""Regenerate supplementary PNG/SVG figures from preserved ordinary/profile samples."""
import json
import argparse
from pathlib import Path
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
TS = [1, 2, 3, 4, 6]
COLORS = {'v2': '#c26627', 'v3': '#176b87'}
PHASES = ['accumulate', 'thread_merge', 'mpi_reduce', 'centroid_update', 'control_bcast']


def load(run, name):
    return [json.loads(line) for line in (run / name).read_text().splitlines() if line.strip()]


def save(fig, name, output):
    for extension in ('png', 'svg'):
        fig.savefig(output / (name + '.' + extension), dpi=180, facecolor='white')
    plt.close(fig)


def render(output, bundle):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    run = bundle / manifest['studies']['thread-scaling']['directory']
    timing, profile = load(run, 'timing.jsonl'), load(run, 'profile.jsonl')
    assert len(timing) == len(profile) == 50
    assert all(not r['diagnostic'] and 'profile_ranks' not in r for r in timing)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'axes.titleweight': 'bold'})
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4))
    fig.subplots_adjust(left=.07, right=.98, top=.80, bottom=.22, wspace=.25)
    fig.suptitle('Fixed P=2: V3 retains near-linear thread scaling', fontsize=16, y=.97, ha='center')
    fig.text(.5, .895, 'N=1,000,000 · D=32 · K=32 · 20 timed iterations · Allreduce · job 1028185.venus01', ha='center', color='#505050')
    for variant, offset in [('v2', -.16), ('v3', .16)]:
        values = [[r['kernel_seconds'] for r in sorted(timing, key=lambda r:r['repeat'])
                   if r['variant'] == variant and r['t'] == t] for t in TS]
        assert all(len(v) == 5 for v in values)
        positions = [i + offset for i in range(len(TS))]
        boxes = axes[0].boxplot(values, positions=positions, widths=.26, whis=(0,100),
                               patch_artist=True, showfliers=False, manage_ticks=False,
                               medianprops={'color': COLORS[variant], 'linewidth': 2},
                               whiskerprops={'color': COLORS[variant]}, capprops={'color': COLORS[variant]})
        for patch in boxes['boxes']:
            patch.set(facecolor=COLORS[variant], alpha=.15, edgecolor=COLORS[variant])
        for x, ys in zip(positions, values):
            axes[0].scatter([x+(j-2)*.028 for j in range(5)], ys, s=16, color=COLORS[variant], zorder=4)
        medians = [statistics.median(v) for v in values]
        speedups = [medians[0]/m for m in medians]
        axes[1].plot(TS, speedups, 'o-', color=COLORS[variant], lw=2, label=variant.upper())
        axes[1].annotate(f'{speedups[-1]:.3f}×', (6, speedups[-1]), xytext=(-8,-18 if variant=='v3' else 8),
                         textcoords='offset points', ha='right', color=COLORS[variant], weight='bold')
    axes[0].set(xticks=range(len(TS)), xticklabels=TS, xlabel='OpenMP threads per rank (T)',
                ylabel='Ordinary kernel time (s)', ylim=(0,6.5), title='A. Five ordinary repetitions per configuration')
    axes[0].legend(handles=[Line2D([0],[0], color=COLORS[v], marker='o', label=v.upper()) for v in COLORS], frameon=False)
    axes[1].plot(TS, TS, '--', color='#888888', lw=1, label='Ideal thread scaling')
    axes[1].set(xticks=TS, xlabel='OpenMP threads per rank (T)', ylabel='Speedup vs same variant at T=1',
                ylim=(0,6.5), xlim=(.8,6.2), title='B. Ratios of ordinary timing medians')
    axes[1].legend(frameon=False, loc='upper left')
    for ax in axes: ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    fig.text(.07,.10,'Active cores = 2T; 12 cores reserved throughout. Timing and diagnostic samples remain separate.', color='#444444')
    fig.text(.07,.055,'Boxes: quartiles and median; whiskers: observed min–max; points: all five samples. These are not confidence intervals.', fontsize=9,color='#555555')
    save(fig, 'thread-scaling-performance', output)

    fig, ax = plt.subplots(figsize=(10.5,5.8))
    fig.subplots_adjust(left=.10, right=.98, top=.79, bottom=.24)
    fig.suptitle('At T=6, accumulation dominates the measured phase budget', fontsize=15, y=.97)
    fig.text(.5,.895,'Independent profiles · P=2 · five repetitions/variant · logarithmic percentage scale', ha='center', color='#505050')
    for variant, offset in [('v2',-.12),('v3',.12)]:
        selected=[]
        for r in profile:
            if r['variant'] != variant or r['t'] != 6: continue
            ranks=r['profile_ranks']
            rank=max(ranks, key=lambda item:(item['kernel_seconds'],-item['rank']))
            assert rank['rank']==r['profile_critical_rank']
            selected.append(rank)
        assert len(selected)==5
        for i,phase in enumerate(PHASES):
            shares=[100*r['phase_seconds'][phase]/r['kernel_seconds'] for r in selected]
            x=i+offset; med=statistics.median(shares)
            ax.vlines(x,min(shares),max(shares),color=COLORS[variant],lw=1.5)
            ax.scatter([x+(j-2)*.018 for j in range(5)],shares,color=COLORS[variant],s=15,alpha=.65)
            ax.scatter([x],[med],marker='D',s=40,facecolor=COLORS[variant],edgecolor='white',zorder=5)
    ax.set_yscale('log')
    ax.set(ylim=(1e-5,300),xticks=range(5),xticklabels=['Accumulation','Thread merge*','MPI reduce','Centroid update','Control broadcast'],
           ylabel='Phase time / same rank kernel time (%)')
    ax.grid(axis='y',alpha=.22);ax.set_axisbelow(True)
    ax.legend(handles=[Line2D([0],[0],color=COLORS[v],marker='D',label=v.upper()) for v in COLORS],frameon=False,loc='upper right')
    fig.text(.10,.14,'Each sample uses every phase from its maximum-kernel rank. Diamonds: medians; ranges: observed min–max.',fontsize=9)
    fig.text(.10,.095,'*V2 has no private-buffer merge: this slot records timer/control overhead. Independent medians are not additive.',fontsize=9)
    fig.text(.10,.05,'Accumulation includes clearing, distances, updates and barriers; this does not isolate pure atomic waiting.',fontsize=9,color='#555555')
    save(fig,'thread-scaling-phases', output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'benchmarks/atlas')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/atlas/Figure')
    args = parser.parse_args()
    from reproduce_atlas import verify_bundle
    try:
        verify_bundle(args.bundle)
        render(args.output, args.bundle)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, 'Error: %s\n' % error)


if __name__ == '__main__':
    main()
