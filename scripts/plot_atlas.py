#!/usr/bin/env python3
"""Create report figures and tables from the preserved Atlas measurements."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from atlas_results import (FIGURES, build_results, compare, describe_times,
                           summarize_study, write_tables)
from atlas_report_text import write_report_results


ROOT = Path(__file__).resolve().parent.parent
BLUE, ORANGE, PURPLE, GREY = '#0072B2', '#D55E00', '#7B4A9E', '#6B7280'


def distribution(ax, positions, groups, color, label=None, bars=False):
    """Plot every repeat plus a median and an observed min/max whisker."""
    for index, (x, group) in enumerate(zip(positions, groups)):
        values = group['times']
        stats = describe_times(values)
        median, minimum, maximum = stats['median_seconds'],stats['min_seconds'],stats['max_seconds']
        if bars:
            ax.bar(x, median, width=.28, color=color, alpha=.16, edgecolor=color, zorder=2)
        ax.scatter([x+(i-2)*.025 for i in range(5)], values, s=17, color=color,
                   alpha=.55, linewidths=0, zorder=4)
        ax.errorbar([x], [median], yerr=[[max(0,median-minimum)], [max(0,maximum-median)]],
                    fmt='D', markersize=5, color=color, capsize=4, elinewidth=1.4,
                    label=label if index==0 else None, zorder=5)


def decorate(fig, title, subtitle, footer):
    fig.suptitle(title, x=.08, y=.97, ha='left', fontsize=14, fontweight='bold')
    fig.text(.08, .89, subtitle, ha='left', fontsize=9, color=GREY)
    fig.text(.08, .025, footer, ha='left', fontsize=8, color=GREY)


def categorical(ax, groups):
    ax.set_xticks(range(len(groups)), ['%d × %d'%(r['p'],r['t']) for r in groups])
    ax.set_xlabel('MPI processes P × OpenMP threads T')


def horizontal_distribution(ax, positions, groups, color, label=None, marker='D'):
    """Show complete observed ranges on a labelled, zoomed time axis; no bars."""
    for index,(y,group) in enumerate(zip(positions,groups)):
        ax.scatter(group['times'],[y+(i-2)*.035 for i in range(5)],s=25,color=color,
                   alpha=.58,linewidths=0,zorder=4)
        median = group['median_seconds']
        ax.errorbar([median],[y],xerr=[[median-group['min_seconds']],
                                      [group['max_seconds']-median]],
                    fmt=marker,markersize=7,color=color,capsize=5,elinewidth=1.6,
                    label=label if index==0 else None,zorder=5)


def draw_strong_runtime(plt, groups):
    serial = next(r for r in groups if r['variant']=='v0')
    parallel = sorted((r for r in groups if r['variant']=='v3'), key=lambda r:r['p'])
    xs = [r['p'] for r in parallel]
    fig,ax = plt.subplots(figsize=(7.4,4.8))
    fig.subplots_adjust(left=.11, right=.97, top=.81, bottom=.18)
    ax.axhspan(serial['min_seconds'],serial['max_seconds'],color=GREY,alpha=.12)
    ax.axhline(serial['median_seconds'],color=GREY,linewidth=1.3,label='V0 serial median (%.3f s)'%serial['median_seconds'])
    ax.plot(xs,[serial['median_seconds']/p for p in xs],color=GREY,linestyle='--',linewidth=1.1,label='Ideal: serial median / P')
    distribution(ax,xs,parallel,BLUE,'V3: median and observed range')
    ax.plot(xs,[r['median_seconds'] for r in parallel],color=BLUE,linewidth=1)
    ax.set(xticks=xs,xlabel='MPI processes P (T = 1)',ylabel='Kernel runtime (s)',ylim=(0,13),xlim=(.5,12.6))
    ax.legend(loc='upper right',fontsize=8,frameon=True,facecolor='white',framealpha=.95)
    ax.annotate('12 ranks: %.3f s'%parallel[-1]['median_seconds'],
                xy=(12,parallel[-1]['median_seconds']),xytext=(7.3,3.0),fontsize=9,
                arrowprops=dict(arrowstyle='-',color=BLUE),color=BLUE)
    decorate(fig,'Strong scaling: kernel runtime','Job 1027222 · V3, one thread/rank · N = 1,000,000; D = K = 32',
             'Five observations/configuration. P = 1–6: one socket; P = 12: two sockets.')
    return fig


def draw_strong_scaling(plt, groups):
    serial = next(r for r in groups if r['variant']=='v0')['median_seconds']
    parallel = sorted((r for r in groups if r['variant']=='v3'),key=lambda r:r['p'])
    single = parallel[0]['median_seconds']; xs = [r['p'] for r in parallel]
    fig,axes = plt.subplots(2,1,figsize=(7.8,6.5))
    fig.subplots_adjust(left=.14,right=.96,top=.81,bottom=.20,hspace=.47)
    for baseline,color,label in [(serial,BLUE,'V0 serial baseline'),(single,ORANGE,'V3 P=1 baseline')]:
        stats = [compare(baseline,r,cores=r['p']) for r in parallel]
        for ax,efficiency in zip(axes,[False,True]):
            factor = [100/p if efficiency else 1 for p in xs]
            ax.plot(xs,[s['speedup']*f for s,f in zip(stats,factor)],
                    'o-' if color==BLUE else '^--',color=color,markersize=5,
                    linewidth=1.5,label=label)
            ax.fill_between(xs,[s['speedup_min']*f for s,f in zip(stats,factor)],
                            [s['speedup_max']*f for s,f in zip(stats,factor)],color=color,alpha=.13,linewidth=0)
            ax.set(xticks=xs,xlim=(.7,12.7))
    axes[0].plot(xs,xs,'--',color=GREY,linewidth=1,label='Ideal linear reference')
    axes[0].set(ylabel='Speedup (×)',ylim=(0,13),title='Speedup: full scale')
    axes[1].axhline(100,color=GREY,linestyle='--',linewidth=1)
    axes[1].set(ylabel='Parallel efficiency (%)',ylim=(90,106),yticks=[90,94,98,100,102,106],
                title='Efficiency: zoomed to 90–106%',xlabel='MPI processes P (T = 1)')
    # Put labels in empty plot regions, with opaque backgrounds so grid lines
    # cannot pass through the text; leaders identify the two nearby endpoints.
    for baseline,color,speed_position,eff_position in [
            (serial,BLUE,(.55,.86),(.70,.89)),
            (single,ORANGE,(.70,.43),(.70,.17))]:
        endpoint=baseline/parallel[-1]['median_seconds']
        for ax,value,label,position in [
                (axes[0],endpoint,'%.3f×'%endpoint,speed_position),
                (axes[1],100*endpoint/12,'%.2f%%'%(100*endpoint/12),eff_position)]:
            ax.annotate(label,(12,value),xytext=position,textcoords='axes fraction',
                        fontsize=9,color=color,ha='center',va='center',zorder=8,
                        bbox=dict(boxstyle='round,pad=.25',facecolor='white',edgecolor='none',alpha=1),
                        arrowprops=dict(arrowstyle='-',color=color,linewidth=.8,
                                        shrinkA=4,shrinkB=5))
    handles,labels = axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.53,.095),ncol=3,fontsize=8,frameon=False)
    decorate(fig,'Strong scaling: speedup and efficiency','Job 1027222 · Fixed work · Two explicitly labelled single-core references',
             'Bands: observed ranges, not confidence intervals; reference medians fixed.\nEfficiency axis omits zero. P = 12 uses two sockets.')
    return fig


def draw_hybrid(plt, groups):
    groups = sorted(groups,key=lambda r:r['p'])
    baseline = next(r['median_seconds'] for r in groups if r['p']==12)
    fig,ax = plt.subplots(figsize=(8.2,5.6))
    fig.subplots_adjust(left=.13,right=.97,top=.74,bottom=.20)
    # With only five repeats, retain every observation. Whiskers deliberately
    # span the full observed range rather than the boxplot default of 1.5 IQR.
    boxes = ax.boxplot([r['times'] for r in groups],positions=range(len(groups)),
                       widths=.48,whis=(0,100),patch_artist=True,showfliers=False,
                       medianprops=dict(color='black',linewidth=1.8),
                       whiskerprops=dict(color=GREY,linewidth=1.1),
                       capprops=dict(color=GREY,linewidth=1.1),zorder=3)
    for i,r in enumerate(groups):
        color = PURPLE if r['p']==12 else BLUE
        boxes['boxes'][i].set(facecolor=color,edgecolor=color,alpha=.20)
        ax.scatter([i+(j-2)*.055 for j in range(len(r['times']))],r['times'],
                   s=28,color=color,alpha=.85,linewidths=.4,edgecolors='white',zorder=5)
        ax.text(i,1.043,'%.4f s\n%+.2f%%'%(
            r['median_seconds'],100*(r['median_seconds']/baseline-1)),
            ha='center',va='center',fontsize=9,linespacing=1.5,
            bbox=dict(facecolor='white',edgecolor='none',pad=2),zorder=8)
    ax.axhline(baseline,color=PURPLE,linestyle='--',linewidth=1.1,
               label='12 × 1 median: %.4f s'%baseline,zorder=2)
    categorical(ax,groups)
    ax.set(xlim=(-.6,5.6),ylim=(.88,1.065),yticks=[.90,.92,.94,.96,.98,1.00,1.02],
           ylabel='Kernel runtime (s; zoomed axis)')
    ax.xaxis.grid(False)
    ax.legend(loc='upper left',bbox_to_anchor=(-.01,1.16),fontsize=9,frameon=False)
    ax.text(.99,1.10,'Labels: median / change vs 12 × 1',transform=ax.transAxes,
            ha='right',fontsize=8,color=GREY)
    decorate(fig,'Fixed 12-core MPI/OpenMP layouts','Job 1027229 · V3 + Allreduce · All layouts use the same single socket',
             'Boxes: middle 50%; black lines: medians; whiskers: min–max; dots: all five observations.\nTime axis omits zero. Ranges overlap; boxes and whiskers are not confidence intervals.')
    return fig


def draw_threads(plt, groups):
    first = sorted((r for r in groups if r['variant']=='v2'),key=lambda r:r['p'])
    second = sorted((r for r in groups if r['variant']=='v3'),key=lambda r:r['p'])
    fig,ax = plt.subplots(figsize=(7.4,4.8))
    fig.subplots_adjust(left=.11,right=.97,top=.81,bottom=.18)
    distribution(ax,[i-.18 for i in range(3)],first,ORANGE,'V2: shared atomics',bars=True)
    distribution(ax,[i+.18 for i in range(3)],second,BLUE,'V3: private buffers',bars=True)
    for i,(a,b) in enumerate(zip(first,second)):
        ax.text(i,max(a['max_seconds'],b['max_seconds'])+.06,'%.3f×'%(
            a['median_seconds']/b['median_seconds']),ha='center',fontsize=10,fontweight='bold')
    categorical(ax,first)
    ax.set(ylabel='Kernel runtime (s)',ylim=(0,1.95),xlim=(-.6,2.6))
    ax.legend(loc='upper right',fontsize=8,frameon=False,ncol=2)
    decorate(fig,'Thread accumulation: V2 versus V3','Job 1027231 · Matched layouts · Labels: V2 median / V3 median',
             'Five dots/configuration; whiskers: observed min–max. Each tested rank stays within one socket.')
    return fig


def draw_communication(plt, groups):
    first = sorted((r for r in groups if r['communication']=='allreduce'),key=lambda r:r['p'])
    second = sorted((r for r in groups if r['communication']=='reduce-bcast'),key=lambda r:r['p'])
    fig,ax = plt.subplots(figsize=(8.6,5.6))
    fig.subplots_adjust(left=.12,right=.66,top=.77,bottom=.20)
    horizontal_distribution(ax,[i-.14 for i in range(3)],first,BLUE,'Allreduce',marker='o')
    horizontal_distribution(ax,[i+.14 for i in range(3)],second,ORANGE,'Reduce+Bcast')
    ax.set(xlim=(.875,.96),ylim=(2.5,-.6),xticks=[.88,.90,.92,.94,.96],
           yticks=range(3),yticklabels=['%d × %d'%(r['p'],r['t']) for r in first],
           xlabel='Kernel runtime (s; zoomed axis)',ylabel='MPI processes P × threads T')
    ax.legend(loc='upper left',bbox_to_anchor=(-.01,1.16),ncol=2,fontsize=9,frameon=False)
    ax.text(1.04,1.04,'Medians / Reduce+Bcast change',transform=ax.transAxes,fontsize=9,color=GREY)
    for i,(a,b) in enumerate(zip(first,second)):
        ax.text(1.04,i-.17,'AR  %.4f s'%a['median_seconds'],
                transform=ax.get_yaxis_transform(),va='center',fontsize=10,color=BLUE)
        ax.text(1.04,i+.04,'RB  %.4f s'%b['median_seconds'],
                transform=ax.get_yaxis_transform(),va='center',fontsize=10,color=ORANGE)
        ax.text(1.04,i+.28,'Δ %+.2f%% (%+.2f ms)'%(
            100*(b['median_seconds']/a['median_seconds']-1),
            1000*(b['median_seconds']-a['median_seconds'])),
            transform=ax.get_yaxis_transform(),va='center',fontsize=9)
    decorate(fig,'Global update: Allreduce versus Reduce+Bcast','Job 1027272 · V3 · Matched layouts on a single socket',
             'Time axis omits zero. Dots: five observations; whiskers: observed min–max, not confidence intervals.\nAll ranges overlap. Small median changes do not establish a stable winner.')
    return fig


def render_figures(output, results):
    figure_directory = output/'Figure'
    figure_directory.mkdir()
    # Keep the font cache in the ignored project artifacts directory.
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.grid':True,'axes.axisbelow':True,
                         'grid.color':'#E5E7EB','grid.linewidth':.6,'axes.titlesize':11,
                         'svg.fonttype':'none','svg.hashsalt':'dsa5208-atlas-v1',
                         'pdf.fonttype':42,'savefig.facecolor':'white'})
    functions = [draw_strong_runtime,draw_strong_scaling,draw_hybrid,draw_threads,draw_communication]
    kinds = ['strong','strong','hybrid','threads','communication']
    for (name,title),draw,kind in zip(FIGURES,functions,kinds):
        figure = draw(plt,[r for r in results['groups'] if r['study']==kind])
        for extension in ('png','pdf','svg'):
            metadata = {'Title':title}
            if extension=='svg': metadata['Date'] = None
            if extension=='pdf': metadata['CreationDate'] = None
            figure.savefig(figure_directory/(name+'.'+extension),dpi=300,metadata=metadata)
        plt.close(figure)
    make_overview(output)
    return matplotlib.__version__


def make_overview(output):
    from PIL import Image, ImageDraw, ImageFont
    from matplotlib import font_manager
    overview = Image.new('RGB',(2000,1530),'#F1F4F7')
    draw = ImageDraw.Draw(overview)
    font = ImageFont.truetype(font_manager.findfont('DejaVu Sans'),22)
    for index,(name,_) in enumerate(FIGURES):
        with Image.open(output/'Figure'/(name+'.png')) as source:
            source = source.convert('RGB')
            source.thumbnail((960,470))
            x = 20+(index%2)*1000+(960-source.width)//2
            y = 20+(index//2)*500+(470-source.height)//2
            overview.paste(source,(x,y))
    draw.multiline_text((1040,1080),'Atlas experiment figures\n\n125 formal observations · 5 repeats/configuration\nMedian + observed minimum/maximum\nRanges are not confidence intervals.\nEach comparison stays within one job.\n\nUse individual PDF/SVG files for the report.',font=font,fill='#374151',spacing=12)
    overview.save(output/'overview.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=ROOT/'benchmarks/atlas')
    parser.add_argument('--output',type=Path,default=ROOT/'analysis/atlas',help='New output directory; never overwritten')
    parser.add_argument('--tables-only',action='store_true',help='Write statistics and text with only the Python standard library')
    args = parser.parse_args()
    try:
        output = args.output.resolve(); bundle = args.bundle.resolve()
        if output.exists(): raise ValueError('Output already exists; choose a new directory: '+str(output))
        if bundle==output or bundle in output.parents or output in bundle.parents:
            raise ValueError('Output must be outside the archived evidence bundle')
        results = build_results(bundle)
        if not args.tables_only:
            os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/matplotlib-cache'))
            try:
                import matplotlib  # noqa: F401
            except ImportError:
                raise ValueError('Install optional plotting dependencies: python -m pip install -r requirements.txt')
        output.mkdir(parents=True,exist_ok=False)
        write_tables(output,results)
        write_report_results(output,results,FIGURES)
        version = render_figures(output,results) if not args.tables_only else None
        provenance = dict(python=sys.version,matplotlib=version,formal_records=results['formal_records'],
                          input_manifest_sha256=results['input_manifest_sha256'],
                          scripts_sha256={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                                          for name in ('atlas_results.py','atlas_report_text.py','plot_atlas.py','reproduce_atlas.py')})
        (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
        print('Verified %d evidence files; summarized %d records in %d configurations.'%(
            results['verified_files'],results['formal_records'],len(results['groups'])))
        print('Wrote %s to %s'%('tables and report results' if args.tables_only else '5 figures (PNG/PDF/SVG), tables and report results',output))
    except (OSError,ValueError,KeyError) as error:
        parser.exit(1,'Error: %s\n'%error)


if __name__ == '__main__':
    main()
