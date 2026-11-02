"""Render English, Chinese and Korean reports from the same validated statistics."""


COPY = {
    'en': {
        'title': 'Atlas results for the report',
        'intro': 'All figures use the recorded synthetic workload: N=1,000,000, D=32, K=32, seed=42; 20 measured iterations after 2 warmup iterations, 5 repeats per configuration. The plotted metric is `kernel_seconds`, excluding data preparation, initialization, warmup/reset, final evaluation and external launch/probe overhead. Each comparison stays within its own job. Whiskers and bands describe observed ranges, not confidence intervals.',
        'results': 'Results and interpretation',
        'strong': 'The V0 serial median was {serial:.6f} s, compared with {parallel:.6f} s for V3 at 12 MPI ranks. This gives {speedup:.3f}x speedup and {efficiency:.2f}% efficiency relative to V0; the alternate V3 P=1 baseline gives {alternate:.3f}x and {alternate_efficiency:.2f}%. Some points exceed the ideal linear reference slightly. These observations do not establish general superlinear scaling: there are only five repeats, the implementations differ, and P=12 uses a second socket.',
        'hybrid': 'Fixed 12-core layout medians ranged from {hybrid_min:.6f} to {hybrid_max:.6f} s. The observed ranges overlap, so no stable best layout is established.',
        'threads': 'V3 was faster than V2 at every tested layout: median runtime reductions ranged from {thread_min:.2f}% to {thread_max:.2f}%. All observed V3 times were below all observed V2 times within each matched layout. This supports the private-buffer design for this workload; it does not quantify atomic-wait or memory-bandwidth costs without profiling.',
        'communication': 'Reduce+Bcast median time changes relative to Allreduce ranged from {comm_min:+.2f}% to {comm_max:+.2f}%. Observed ranges overlap for every layout, and the direction varies. No stable communication-strategy winner is established.',
        'captions_heading': 'Figure captions', 'tables_heading': 'Tables',
        'titles': ['Strong scaling: kernel runtime', 'Strong scaling: speedup and efficiency', 'Fixed 12-core MPI/OpenMP layouts', 'Thread accumulation: V2 versus V3', 'Global update: Allreduce versus Reduce+Bcast'],
        'studies': ['Strong scaling', 'Hybrid layouts', 'Thread strategies', 'Communication strategies'],
        'table_header': '| Variant | P | T | Collective | Median (s) | Observed min–max (s) |',
        'serial_collective': 'none (serial)',
        'captions': [
            'V3 runtime with one OpenMP thread per MPI rank. Dots show five V3 observations at each process count; markers and whiskers show their median and observed minimum/maximum. The V0 single-core median is the horizontal reference, with its observed range shaded. P=1–6 uses one socket; P=12 uses two sockets. The dashed ideal curve is V0 median / P.',
            'Top: speedup on its full scale. Bottom: efficiency zoomed to 90–106% so departures from ideal scaling and the two reference choices are visible. Zero is omitted only in the efficiency panel. Speedup uses either the V0 serial median or the explicitly labelled V3 P=1 median; efficiency is speedup / P. Shaded bands use observed parallel ranges with reference medians fixed, not confidence intervals. Socket placement changes at P=12.',
            'Six V3 layouts use the same allocated 12 cores on one socket. Boxes span the first to third quartile; black lines mark medians, whiskers span the observed minimum/maximum, and dots retain all five observations. The vertical time axis is explicitly zoomed and omits zero. Labels give median runtimes and percentage changes relative to the 12x1 median (horizontal dashed line). Ranges overlap; boxes and whiskers are not confidence intervals. This is a fixed-resource comparison, not strong-scaling efficiency.',
            'V2 shared atomic accumulation and V3 thread-private buffers use matched layouts within the same job. Dots show five observations per configuration; whiskers show their observed range. Labels above pairs give the ratio of V2 and V3 medians. The job spans two sockets, but each tested rank stays within one socket. No phase profiling was performed.',
            'V3 Allreduce and Reduce+Bcast use matched layouts on one socket. The horizontal time axis is explicitly zoomed and omits zero. Each strategy retains all five observations and its complete observed min/max range; circles/diamonds mark medians. The right column prints both medians and Reduce+Bcast minus Allreduce changes in percent and milliseconds. Ranges overlap at every layout, so the small median differences do not establish a stable winner. These are whole-kernel timings, not isolated collective costs.',
        ],
    },
}


def write_report_results(output, results, figures):
    """Derive the English report from the same validated statistics and table rows."""
    groups, comparisons = results['groups'], results['comparisons']
    strong = next(c for c in comparisons if c['study']=='strong' and c['p']==12)
    serial = next(r for r in groups if r['study']=='strong' and r['variant']=='v0')
    parallel = next(r for r in groups if r['study']=='strong' and r['p']==12)
    hybrid = [r for r in groups if r['study']=='hybrid']
    threads = [c for c in comparisons if c['study']=='threads']
    comm = [c for c in comparisons if c['study']=='communication']
    values = dict(serial=serial['median_seconds'],parallel=parallel['median_seconds'],
                  speedup=strong['speedup'],efficiency=100*strong['efficiency'],
                  alternate=strong['speedup_vs_v3_p1'],alternate_efficiency=100*strong['efficiency_vs_v3_p1'],
                  hybrid_min=min(r['median_seconds'] for r in hybrid),hybrid_max=max(r['median_seconds'] for r in hybrid),
                  thread_min=min(-c['time_change_pct'] for c in threads),thread_max=max(-c['time_change_pct'] for c in threads),
                  comm_min=min(c['time_change_pct'] for c in comm),comm_max=max(c['time_change_pct'] for c in comm))
    for words in COPY.values():
        report = '# '+words['title']+'\n\n'
        report += '**%d ordinary measurements; %d separate diagnostic profiles.**\n\n' % (
            results['formal_records'], results.get('diagnostic_records', 0))
        report += words['intro']+'\n\n## '+words['results']+'\n\n'
        for kind in ('strong','hybrid','threads','communication'):
            report += words[kind].format(**values)+'\n\n'
        scaling = [row for row in comparisons if row['study'] == 'thread-scaling']
        if scaling:
            v2 = next(row for row in scaling if row['variant'] == 'v2' and row['t'] == 6)
            v3 = next(row for row in scaling if row['variant'] == 'v3' and row['t'] == 6)
            heading, explanation, guide = (
                'Fixed P=2 thread scaling',
                'At T=6, V2/V3 thread speedups are %.3f/%.3f, with efficiencies %.2f%%/%.2f%%. '
                'Each baseline is the same variant at P=2,T=1; efficiency divides by T, not 2T. '
                'Fifty ordinary timings and fifty independent profiles are kept separate. '
                'Profiles use every phase of the same maximum-kernel rank; accumulation includes distances and barriers, '
                'so this is not pure atomic waiting.', 'THREAD_SCALING.md')
            report += '### '+heading+'\n\n'+(explanation % (
                v2['speedup'], v3['speedup'], 100*v2['efficiency'], 100*v3['efficiency']))+'\n\n'
            report += '[Details](%s) · [Timing CSV](thread-scaling-summary.csv) · [Phase CSV](thread-scaling-phase-summary.csv)\n\n'%guide
            for name in ('thread-scaling-performance', 'thread-scaling-phases'):
                report += '!['+heading+'](Figure/'+name+'.png)\n\n'
        report += '## '+words['captions_heading']+'\n\n'
        for (name,_),title,caption in zip(figures,words['titles'],words['captions']):
            report += '### '+title+'\n\n!['+title+'](Figure/'+name+'.png)\n\n'+caption+'\n\n'
        report += '## '+words['tables_heading']+'\n\n'
        study_titles = list(zip(('strong','hybrid','threads','communication'),words['studies']))
        if scaling:
            study_titles.append(('thread-scaling', heading))
        for kind,title in study_titles:
            report += '### '+title+'\n\n'+words['table_header']+'\n|---|---:|---:|---|---:|---:|\n'
            for row in groups:
                if row['study']==kind:
                    collective = row['communication'] if row['variant']!='v0' else words['serial_collective']
                    report += '| %s | %d | %d | %s | %.6f | %.6f–%.6f |\n' % (
                        row['variant'],row['p'],row['t'],collective,row['median_seconds'],row['min_seconds'],row['max_seconds'])
            report += '\n'
        (output/'report_results.md').write_text(report,encoding='utf-8')
