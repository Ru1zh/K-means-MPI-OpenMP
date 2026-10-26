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
    'zh-CN': {
        'title': '报告所用 Atlas 实验结果',
        'intro': '所有图均使用已记录的合成工作负载：N=1,000,000、D=32、K=32、seed=42；2 轮预热后计时 20 轮，每配置重复 5 次。图中指标为 `kernel_seconds`，不含数据准备、初始化、预热/重置、最终评估及外部启动/绑核探针开销。所有比较均限于同一作业。须线和色带表示实测范围，不是置信区间。',
        'results': '结果与解释',
        'strong': 'V0 串行中位耗时为 {serial:.6f} s，V3 在 12 个 MPI 进程时为 {parallel:.6f} s。相对 V0 的加速比为 {speedup:.3f} 倍、效率为 {efficiency:.2f}%；相对另一条明确标注的 V3 P=1 基线，则为 {alternate:.3f} 倍和 {alternate_efficiency:.2f}%。部分点略高于理想线性参考，但只有五次重复，且实现不同、P=12 使用第二个 socket，不能据此认定普遍存在超线性扩展。',
        'hybrid': '固定 12 核配比的中位耗时为 {hybrid_min:.6f}–{hybrid_max:.6f} s。实测范围重叠，不能认定稳定最优配比。',
        'threads': '在全部所测配比中 V3 均快于 V2，中位耗时下降 {thread_min:.2f}%–{thread_max:.2f}%。每个匹配配比的全部 V3 观测都低于全部 V2 观测。这支持在本工作负载中使用私有缓冲；缺少阶段 profile，不能定量归因为原子等待或内存带宽成本。',
        'communication': 'Reduce+Bcast 相对 Allreduce 的中位耗时变化为 {comm_min:+.2f}%–{comm_max:+.2f}%。每种配比的实测范围均重叠，变化方向也不一致，没有稳定的通信策略胜者。',
        'captions_heading': '图注', 'tables_heading': '统计表',
        'titles': ['强扩展：内核耗时', '强扩展：加速比与效率', '固定 12 核 MPI/OpenMP 配比', '线程累加：V2 与 V3', '全局更新：Allreduce 与 Reduce+Bcast'],
        'studies': ['强扩展', '混合配比', '线程策略', '通信策略'],
        'table_header': '| 版本 | P | T | 集合通信 | 中位耗时 (s) | 实测最小–最大 (s) |',
        'serial_collective': '无（串行）',
        'captions': [
            'V3 每个 MPI 进程使用一个 OpenMP 线程。散点为各进程数下的五次 V3 观测；标记和须线表示中位数及实测最小/最大值。V0 单核中位数为水平参考，其实测范围以阴影表示。P=1–6 使用一个 socket，P=12 使用两个 socket。理想虚线为 V0 中位耗时 / P。',
            '上图：完整量程的加速比。下图：效率轴放大至 90–106%，便于观察与理想扩展的偏差及两种参考基线的区别；仅效率图省略零点。加速比使用 V0 串行中位数或明确标注的 V3 P=1 中位数，效率为加速比 / P。色带使用实测并行耗时范围，并固定参考中位数，不是置信区间。P=12 的 socket 布局发生变化。',
            '六种 V3 配比使用同一 socket 上分配的 12 核。箱体覆盖第一至第三四分位数，黑线为中位数，须线为实测最小/最大值，散点保留全部五次观测。纵向耗时轴明确放大并省略零点。标签给出中位耗时及相对 12x1 中位数（水平虚线）的百分比变化。范围重叠，箱体和须线均不是置信区间。这是固定资源比较，不是强扩展效率。',
            'V2 共享原子累加与 V3 线程私有缓冲在同一作业中使用匹配配比。散点为每配置五次观测，须线为实测范围；各组上方标签为 V2/V3 中位耗时比。作业跨两个 socket，但每个所测进程均限制在单个 socket 内。未进行阶段 profile。',
            'V3 的 Allreduce 与 Reduce+Bcast 在一个 socket 上使用匹配配比。横向耗时轴明确放大并省略零点；每种策略均保留全部五次观测及完整实测最小/最大范围，圆点/菱形表示中位数。右栏列出两者中位数，以及 Reduce+Bcast 减 Allreduce 的百分比和毫秒变化。所有配比范围均重叠，微小中位数差异不能证明稳定胜者。测量是完整内核耗时，不是单独的集合通信成本。',
        ],
    },
    'ko': {
        'title': '보고서용 Atlas 실험 결과',
        'intro': '모든 그림은 기록된 합성 작업 부하 N=1,000,000, D=32, K=32, seed=42를 사용합니다. 준비 반복 2회 후 20회를 측정하며, 구성마다 5회 반복 실행합니다. 표시 지표는 `kernel_seconds`로, 데이터 준비, 초기화, 준비 반복/초기 상태 복원, 최종 평가 및 외부 실행/바인딩 탐침의 비용은 제외합니다. 모든 비교는 동일 작업 내에서만 수행합니다. 수염과 음영은 관측 범위이며 신뢰구간이 아닙니다.',
        'results': '결과와 해석',
        'strong': 'V0 직렬 실행의 중앙값은 {serial:.6f} s이며, MPI 프로세스 12개를 사용한 V3는 {parallel:.6f} s입니다. V0 대비 속도 향상은 {speedup:.3f}배, 효율은 {efficiency:.2f}%입니다. 별도로 표시한 V3 P=1 기준에서는 {alternate:.3f}배와 {alternate_efficiency:.2f}%입니다. 일부 점이 이상적인 선형 기준을 약간 넘지만, 반복이 5회뿐이고 구현이 다르며 P=12에서는 두 번째 소켓을 사용하므로 일반적인 초선형 확장성을 입증하지 않습니다.',
        'hybrid': '12코어 고정 배치의 중앙 실행 시간은 {hybrid_min:.6f}–{hybrid_max:.6f} s입니다. 관측 범위가 겹치므로 일관되게 가장 좋은 배치를 확정할 수 없습니다.',
        'threads': '측정한 모든 배치에서 V3가 V2보다 빨랐으며 중앙 실행 시간은 {thread_min:.2f}%–{thread_max:.2f}% 감소했습니다. 동일 배치에서 모든 V3 관측값이 모든 V2 관측값보다 작았습니다. 이는 이 작업 부하에서 전용 버퍼 설계를 뒷받침하지만, 단계별 프로파일 없이 원자 연산 대기나 메모리 대역폭 비용을 정량화할 수는 없습니다.',
        'communication': 'Allreduce 대비 Reduce+Bcast의 중앙 실행 시간 변화는 {comm_min:+.2f}%–{comm_max:+.2f}%입니다. 모든 배치에서 관측 범위가 겹치고 변화 방향도 다르므로 일관되게 우수한 통신 전략을 확정할 수 없습니다.',
        'captions_heading': '그림 설명', 'tables_heading': '통계표',
        'titles': ['강한 확장성: 커널 실행 시간', '강한 확장성: 속도 향상과 효율', '12코어 고정 MPI/OpenMP 배치', '스레드 누적: V2와 V3', '전역 갱신: Allreduce와 Reduce+Bcast'],
        'studies': ['강한 확장성', '하이브리드 배치', '스레드 전략', '통신 전략'],
        'table_header': '| 버전 | P | T | 집단 통신 | 중앙값 (s) | 관측 최솟값–최댓값 (s) |',
        'serial_collective': '없음(직렬)',
        'captions': [
            'MPI 프로세스마다 OpenMP 스레드 1개를 사용하는 V3 실행 시간입니다. 점은 각 프로세스 수에서의 V3 관측 5개이며, 표식과 수염은 중앙값 및 관측 최솟값/최댓값입니다. V0 단일 코어 중앙값은 수평 기준선이고 그 관측 범위는 음영으로 표시합니다. P=1–6은 소켓 1개, P=12는 소켓 2개를 사용합니다. 이상적인 점선은 V0 중앙 실행 시간 / P입니다.',
            '위: 전체 범위의 속도 향상. 아래: 이상적인 확장성과의 차이 및 두 기준의 차이를 볼 수 있도록 효율 축을 90–106%로 확대합니다. 영점은 효율 패널에서만 생략합니다. 속도 향상은 V0 직렬 중앙값 또는 명시한 V3 P=1 중앙값을 사용하며 효율은 속도 향상 / P입니다. 음영은 기준 중앙값을 고정한 관측 병렬 범위로, 신뢰구간이 아닙니다. P=12에서 소켓 배치가 바뀝니다.',
            'V3 배치 6개는 동일 소켓에 할당된 12코어를 사용합니다. 상자는 제1사분위수부터 제3사분위수까지, 검은 선은 중앙값, 수염은 관측 최솟값/최댓값이며 점은 관측 5개를 모두 표시합니다. 세로 시간 축은 명시적으로 확대되어 영점을 생략합니다. 레이블은 중앙 실행 시간과 12x1 중앙값(수평 점선) 대비 변화율입니다. 범위가 겹치며 상자와 수염은 신뢰구간이 아닙니다. 이는 자원 고정 비교로, 강한 확장성 효율이 아닙니다.',
            'V2 공유 원자적 누적과 V3 스레드 전용 버퍼는 같은 작업에서 동일한 배치를 사용합니다. 점은 구성별 관측 5개, 수염은 관측 범위입니다. 각 쌍 위의 레이블은 V2/V3 중앙 실행 시간 비율입니다. 작업은 소켓 2개에 걸치지만 측정한 각 프로세스는 소켓 1개 안에 머뭅니다. 단계별 프로파일은 수행하지 않았습니다.',
            'V3 Allreduce와 Reduce+Bcast는 소켓 1개에서 동일한 배치를 사용합니다. 가로 시간 축은 명시적으로 확대되어 영점을 생략합니다. 각 전략의 관측 5개와 전체 최솟값/최댓값 범위를 유지하며 원/마름모는 중앙값입니다. 오른쪽에는 두 중앙값 및 Reduce+Bcast에서 Allreduce를 뺀 백분율/밀리초 변화가 표시됩니다. 모든 배치의 범위가 겹치므로 작은 중앙값 차이로 일관된 우열을 확정할 수 없습니다. 개별 집단 통신 비용이 아닌 전체 커널 실행 시간입니다.',
        ],
    },
}


def navigation(base, explicit_english=False):
    english = base + ('.en.md' if explicit_english else '.md')
    return '[English](%s) | [简体中文](%s.zh-CN.md) | [한국어](%s.ko.md)\n\n' % (english, base, base)


def write_report_results(output, results, figures):
    """Use common numeric values/table rows so translations cannot drift numerically."""
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
    for language, words in COPY.items():
        report = '# '+words['title']+'\n\n'+navigation('report_results',True)
        report += '**%d ordinary measurements; %d separate diagnostic profiles.**\n\n' % (
            results['formal_records'], results.get('diagnostic_records', 0))
        report += words['intro']+'\n\n## '+words['results']+'\n\n'
        for kind in ('strong','hybrid','threads','communication'):
            report += words[kind].format(**values)+'\n\n'
        scaling = [row for row in comparisons if row['study'] == 'thread-scaling']
        if scaling:
            v2 = next(row for row in scaling if row['variant'] == 'v2' and row['t'] == 6)
            v3 = next(row for row in scaling if row['variant'] == 'v3' and row['t'] == 6)
            heading, explanation, guide = {
                'en': ('Fixed P=2 thread scaling',
                       'At T=6, V2/V3 thread speedups are %.3f/%.3f, with efficiencies %.2f%%/%.2f%%. '
                       'Each baseline is the same variant at P=2,T=1; efficiency divides by T, not 2T. '
                       'Fifty ordinary timings and fifty independent profiles are kept separate. '
                       'Profiles use every phase of the same maximum-kernel rank; accumulation includes distances and barriers, '
                       'so this is not pure atomic waiting.', 'THREAD_SCALING.md'),
                'zh-CN': ('固定 P=2 线程扩展',
                          'T=6 时 V2/V3 的线程加速比为 %.3f/%.3f，效率为 %.2f%%/%.2f%%。'
                          '各自基线为同一实现的 P=2、T=1；线程效率除以 T，不是 2T。'
                          '50 条普通计时与 50 条独立诊断分别保存。诊断使用同次测量内核最慢 rank 的全部阶段，'
                          'accumulate 含距离计算与屏障，不能直接解释为纯 atomic 等待。', 'THREAD_SCALING.zh-CN.md'),
                'ko': ('고정 P=2 스레드 확장',
                       'T=6에서 V2/V3 스레드 가속비는 %.3f/%.3f이고 효율은 %.2f%%/%.2f%%이다. '
                       '각 기준은 같은 구현의 P=2,T=1이며 효율은 2T가 아닌 T로 나눈다. '
                       '일반 측정 50개와 별도 진단 50개를 구분한다. 진단은 같은 최대 커널 시간 rank의 모든 단계를 사용한다. '
                       'accumulate에는 거리 계산과 장벽이 포함되어 순수 atomic 대기로 해석할 수 없다.', 'THREAD_SCALING.ko.md')
            }[language]
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
        (output/('report_results.'+language+'.md')).write_text(report,encoding='utf-8')
