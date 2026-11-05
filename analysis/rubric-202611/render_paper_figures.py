#!/usr/bin/env python3
"""Regenerate report-size figures from the audited Vanda tables (no new timing)."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from reproduce_rubric import verify_manifest
from rubric_analysis import read_runs, audit_records, summarize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path(__file__).parent / 'paper-figures')
    a = p.parse_args()
    evidence = ROOT / 'benchmarks/rubric-202611'
    verify_manifest(evidence)
    rows, profiles = summarize(audit_records(*read_runs(evidence / 'runs')))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.labelsize': 9, 'axes.titlesize': 9.5,
                         'xtick.labelsize': 8, 'ytick.labelsize': 8,
                         'legend.fontsize': 8, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.dpi': 300})
    a.output.mkdir(parents=True, exist_ok=False)
    colors = dict(v0='#475569', v1='#2563eb', v2='#e87916', v3='#0f8a71', v4='#8b5cf6')
    def save(fig, name):
        for ext in ('png','pdf','svg'):
            fig.savefig(a.output / (name + '.' + ext), bbox_inches='tight')
        plt.close(fig)
    def select(suite): return [r for r in rows if r['suite'] == suite]
    def line(ax, data, x, y='median_seconds', label=None, color='#2563eb', error=False):
        data=sorted(data,key=lambda r:r[x]);xx=[r[x] for r in data]; yy=[r[y] for r in data]
        e=[[r['median_seconds']-r['min_seconds'] for r in data],
           [r['max_seconds']-r['median_seconds'] for r in data]] if error else None
        ax.errorbar(xx,yy,yerr=e,marker='o',markersize=3,capsize=2,linewidth=1.2,label=label,color=color)
        ax.grid(axis='y',alpha=.2)
    def paxis(ax):
        ax.set_xscale('log',base=2);ax.set_xticks([1,4,16,64,256],['1','4','16','64','256'])
        ax.set_xlabel('MPI ranks P')
    serial=select('serial');fig,axes=plt.subplots(2,3,figsize=(6.25,4.4),layout='constrained')
    for col,(x,constants) in enumerate((('n',dict(d=32,k=32)),('d',dict(n=1000000,k=32)),('k',dict(n=1000000,d=32)))):
        data=[r for r in serial if all(r[k]==v for k,v in constants.items())]
        line(axes[0,col],data,x,error=True)
        normalized=[dict(r,normalized=r['seconds_per_inkd']*1e12) for r in data]
        line(axes[1,col],normalized,x,'normalized',color=colors['v3'])
        for ax in axes[:,col]:
            ax.set_xscale('log',base=2); ax.set_xlabel(x.upper())
            ticks=[100000,1000000,4000000] if x=='n' else [8,32,128]
            labels=['100k','1M','4M'] if x=='n' else ['8','32','128']
            ax.set_xticks(ticks,labels)
        axes[0,col].set_title({'n':'Sample count','d':'Dimensions','k':'Clusters'}[x])
        axes[0,col].set_ylabel('Loop time (s)')
        axes[1,col].set_ylabel('ps per INKD')
    save(fig,'figure-1-serial')
    strong=[r for r in select('strong') if r['variant']=='v1']
    fig,axes=plt.subplots(1,3,figsize=(6.25,2.35),layout='constrained')
    line(axes[0],strong,'p',error=True);axes[0].set_yscale('log');axes[0].set_ylabel('Seconds')
    for field,label,color in [('speedup_serial','V0 reference',colors['v1']),('speedup_mpi','V1 / P=1',colors['v2'])]:
        line(axes[1],strong,'p',field,label,color)
    for field,label,color in [('efficiency_serial','V0 reference',colors['v1']),('efficiency_mpi','V1 / P=1',colors['v2'])]:
        line(axes[2],strong,'p',field,label,color)
    axes[1].set_ylabel('Speedup');axes[2].set_ylabel('Efficiency')
    for ax,title in zip(axes,('Loop time','Strong speedup','Efficiency S/P')):
        paxis(ax);ax.set_title(title);ax.axvline(64,color='#64748b',ls=':',lw=1)
    axes[1].legend(loc='upper left',fontsize=7.5)
    save(fig,'figure-2-strong')
    weak=select('weak');fig,axes=plt.subplots(1,3,figsize=(6.25,2.35),layout='constrained')
    for ax,field,title,label in zip(axes,('median_seconds','weak_efficiency','throughput_speedup'),
                                    ('Loop time','Weak efficiency','Throughput speedup'),('Seconds','T1 / TP','P T1 / TP')):
        line(ax,weak,'p',field,color=colors['v3'],error=field=='median_seconds')
        paxis(ax);ax.set_title(title);ax.set_ylabel(label)
    axes[1].axhline(1,color='#64748b',ls=':',lw=1)
    save(fig,'figure-3-weak')
    fig,axes=plt.subplots(1,2,figsize=(6.25,2.85),layout='constrained')
    comm=select('communication');x=[0,1]
    for j,(strategy,color,label) in enumerate((('allreduce',colors['v1'],'Allreduce'),('reduce-bcast',colors['v2'],'Reduce+Bcast'))):
        data=sorted([r for r in comm if r['communication']==strategy],key=lambda r:r['p'])
        pos=[v+(-.18 if j==0 else .18) for v in x]
        axes[0].bar(pos,[r['median_seconds'] for r in data],width=.32,color=color,label=label)
        axes[0].errorbar(pos,[r['median_seconds'] for r in data],
            yerr=[[r['median_seconds']-r['min_seconds'] for r in data],[r['max_seconds']-r['median_seconds'] for r in data]],
            fmt='none',color='black',capsize=2)
    axes[0].set_xticks(x,['64','256']);axes[0].set_xlabel('MPI ranks P');axes[0].set_ylabel('Ordinary loop (s)')
    axes[0].legend(fontsize=7.5)
    cp=sorted([r for r in profiles if r['suite']=='communication'],key=lambda r:(r['p'],r['communication']))
    bottom=[0.]*4
    for field,label,color in [('accumulate','Accum.',colors['v1']),('thread_merge','Merge',colors['v3']),('mpi_reduce','Reduce',colors['v2']),('centroid_update','Update',colors['v4']),('control_bcast','Bcast','#64748b')]:
        values=[r[field] for r in cp];axes[1].bar(range(4),values,bottom=bottom,label=label,color=color)
        bottom=[a+b for a,b in zip(bottom,values)]
    axes[1].set_xticks(range(4),['64\nAR','64\nRB','256\nAR','256\nRB']);axes[1].set_ylabel('Diagnostic phases (s)')
    axes[1].legend(fontsize=7,ncols=3,loc='upper center',bbox_to_anchor=(.5,1.26),columnspacing=.7,handlelength=1)
    for ax in axes: ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    save(fig,'figure-4-communication')
    hybrid=[r for r in select('hybrid') if r['variant']!='v1'];fig,axes=plt.subplots(1,2,figsize=(6.25,2.65),layout='constrained')
    for j,variant in enumerate(('v2','v3')):
        data=sorted([r for r in hybrid if r['variant']==variant],key=lambda r:r['t'])
        pos=[i+(-.18 if j==0 else .18) for i in range(4)]
        axes[0].bar(pos,[r['median_seconds'] for r in data],width=.32,color=colors[variant],label=variant.upper())
        axes[0].errorbar(pos,[r['median_seconds'] for r in data],
            yerr=[[r['median_seconds']-r['min_seconds'] for r in data],[r['max_seconds']-r['median_seconds'] for r in data]],
            fmt='none',color='black',capsize=2)
        line(axes[1],data,'t','time_change_percent',variant.upper(),colors[variant])
    base=next(r['median_seconds'] for r in select('hybrid') if r['variant']=='v1')
    axes[0].axhline(base,color='#475569',ls='--',label='V1 / 256 ranks',lw=1)
    axes[0].set_xticks(range(4),['256×1','128×2','64×4','32×8']);axes[0].set_xlabel('Ranks × threads')
    axes[0].set_ylabel('Loop time (s)');axes[0].legend(fontsize=7.5)
    axes[1].axhline(0,color='#64748b',ls=':',lw=1);axes[1].set_xticks([1,2,4,8]);axes[1].set_xlabel('Threads per rank T')
    axes[1].set_ylabel('Time change vs. V1 (%)');axes[1].legend()
    save(fig,'figure-5-hybrid')
    gpu=select('gpu');fig,axes=plt.subplots(1,2,figsize=(6.25,2.65),layout='constrained')
    for ax,total in zip(axes,(False,True)):
        field='median_total_seconds' if total else 'median_seconds'
        lo='min_total_seconds' if total else 'min_seconds';hi='max_total_seconds' if total else 'max_seconds'
        for j,(variant,label) in enumerate((('v0','CPU1'),('v3','CPU8'),('v4','GPU1'))):
            data=sorted([r for r in gpu if r['variant']==variant],key=lambda r:r['n']);pos=[i+(j-1)*.24 for i in range(3)]
            ax.bar(pos,[r[field] for r in data],width=.22,label=label,color=colors[variant])
            ax.errorbar(pos,[r[field] for r in data],yerr=[[r[field]-r[lo] for r in data],[r[hi]-r[field] for r in data]],fmt='none',capsize=2,color='black')
        ax.set_yscale('log');ax.set_xticks(range(3),['0.1M','1M','4M']);ax.set_xlabel('Samples N')
        ax.set_ylabel('Seconds (log scale)');ax.set_title('Internal end-to-end' if total else 'Complete timed loop')
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0].legend(fontsize=7.5,ncols=3,columnspacing=.8,handlelength=1)
    save(fig,'figure-6-gpu')
    print('Saved six audited report figures in PNG/PDF/SVG:',a.output)


if __name__=='__main__':
    main()
