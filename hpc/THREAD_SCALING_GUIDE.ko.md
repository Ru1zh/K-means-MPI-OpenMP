# 고정 P=2 스레드 확장과 별도 단계 시간 측정

[English](THREAD_SCALING_GUIDE.md) | [简体中文](THREAD_SCALING_GUIDE.zh-CN.md) | [한국어](THREAD_SCALING_GUIDE.ko.md)

**CPU 작업 하나를 새로 실행**한다. 기존 네 실험의 125개 기록은 유효하며 다시 실행할 필요가 없다. GPU나 데이터 다운로드도 필요 없다. 작업 `1028185.venus01`을 완료했으며 일반 측정 50개, 별도 진단 50개 및 소규모 사전 검사 20회를 로컬에서 재검증했다. 다시 제출할 필요가 없다. [결과](../analysis/atlas/THREAD_SCALING.ko.md)와 [원본 목록](../benchmarks/atlas/manifest.json)을 참고한다. 아래 제출 절차는 향후 재현용이며 다운로드한 기록은 `python3 -B scripts/reproduce_atlas_thread_scaling.py`로 검증한다.

## 실험 설계

- P=2를 고정하고 T=1,2,3,4,6에서 V2/V3를 비교한다. 통신은 Allreduce이며 N=1,000,000, D=32, K=32, seed=42, 측정 20회, 워밍업 2회를 유지한다.
- 작업 전체에 12코어를 요청한다. 각 rank는 같은 소켓 내의 동일한 6코어를 계속 예약하고 T에 따라 중첩된 OpenMP 활성 코어 집합만 바꾼다. 실제 활성 코어 수는 2T이며 항상 12가 아니다. 소켓을 넘지 않는 6코어 그룹 두 개를 만들 수 없으면 측정 전에 실패한다.
- 구성별 5회 반복으로 **일반 시간 50개**(`timing.jsonl`)와 **별도 진단 시간 50개**(`profile.jsonl`)를 얻는다. 각 반복에서 구성 순서를 무작위로 정하고 `study-plan.json`에 저장한다. 일반 측정을 모두 마친 후 별도 진단 블록을 실행한다.
- 전체 크기의 V0 수치 참조를 새로 생성하고 두 모드, 두 구현, 모든 스레드 수에 대해 작은 데이터 검증 20회를 수행한다. V0는 반복 측정한 성능 기준이 아니다. 데이터 지문, 초기 표본, 군집 개수와 SSE를 검사하며 작은 데이터에서는 레이블과 중심도 검사한다.

스레드 확장의 기준은 같은 구현의 P=2,T=1 중앙값이다. 가속비 = median(T=1)/median(T), 효율 = 가속비/T이다. V2/V3 비교는 새 작업 안에서 수행한다. 기존 T=6 결과는 배경 자료이며 이번 할당에서 얻은 대응 측정값이 아니다.

## 새 작업만 준비하고 제출하기

로컬 저장소 루트에서 실행한다.

```sh
python3 hpc/atlas-thread-scaling.py --dry-run
python3 hpc/build-atlas-strategy-packages.py --studies thread-scaling \
  --output artifacts/atlas-thread-scaling-package
```

`artifacts/atlas-thread-scaling-package/project3-atlas-thread-scaling.tar.gz`를 Atlas로 전송한다. Atlas의 새 작업 디렉터리에서 실행한다.

```sh
tar -xzf project3-atlas-thread-scaling.tar.gz
cd project3-atlas-thread-scaling
sha256sum -c source-manifest.sha256
qsub atlas-thread-scaling.pbs
```

PBS 스크립트는 기존 실험의 모듈을 불러오고 현재 소스를 컴파일하며 환경과 CPU 토폴로지를 저장한다. 실행마다 CPU 배치를 검사한 후 실험과 통계 분석을 수행하고 영어·중국어·한국어 분석을 만든다. 자원은 `parallel` 큐, 노드 1개, 12코어, 8 GB, 30분이다. 별도 압축 해제 디렉터리를 사용하고 저장소의 `hpc/`에서 직접 제출하거나 실행 중인 다른 작업과 빌드 디렉터리를 공유하지 않는다. 실패하면 새 제출과 새 결과 디렉터리를 사용한다.

## 결과 가져오기와 분석

`results/atlas-thread-scaling.<PBS_JOBID>/` **전체**, PBS 출력/오류 파일(`p3_tscale.o*`), 실행에 사용한 정확한 소스 아카이브를 내려받는다. 조회 가능할 때 스케줄러 정보도 저장한다.

```sh
qstat -xf JOBID > results/atlas-thread-scaling.JOBID/pbs-job.txt
```

두 `JOBID`를 모두 전체 작업 ID로 바꾼다. 성공한 작업은 `status.txt`에 `exit_status=0`이 있고 `analysis.audit.json`의 수치·구성·배치 검증이 모두 통과해야 한다. 실패 로그도 진단용으로 보관하며 미완료 결과를 기존 125개 기록에 섞지 않는다.

다운로드 후 Python 3.8+ 표준 라이브러리만으로 다시 분석할 수 있다.

```sh
python3 hpc/analyze-atlas-thread-scaling.py /path/to/atlas-thread-scaling.JOBID
```

출력은 `thread-scaling-summary.csv`, `phase-summary.csv`, `analysis.audit.json`, `analysis.md` / `analysis.zh-CN.md` / `analysis.ko.md`이다. 원본 입력은 변경하지 않으며 파생 파일만 다시 생성한다.

## 단계별 기여 해석

`--profile`은 `profile_ranks`(rank별 커널 및 다섯 단계 시간)와 `profile_critical_rank`를 추가한다. 각 진단 표본은 **커널 시간이 가장 큰 rank의 모든 단계**를 사용하며 동률이면 작은 rank를 선택한다. residual은 그 rank의 커널 시간에서 단계 합을 뺀 값이다. 호환성을 위해 유지한 최상위 `phase_seconds`는 단계별 독립 최대값이므로 합산하면 안 된다.

`accumulate`에는 버퍼 초기화, 거리 계산, 갱신과 OpenMP 배리어가 포함된다. V3의 `thread_merge`는 이후 병합을 따로 측정한다. `mpi_reduce`, `centroid_update`, `control_bcast`는 나머지 단계이다(Allreduce에서는 보통 제어 브로드캐스트가 없다). 누적이나 병합이 지배적인지는 확인할 수 있지만 **순수 atomic 대기 시간**을 분리하거나 뺄셈만으로 인과관계를 증명할 수는 없다. 진단 단계 시간을 일반 커널 시간과 합치지 않는다. 각 단계 중앙값의 합은 커널 중앙값과 다를 수 있으며 최소–최대 범위는 신뢰 구간이 아니다. 기존 보고서와 그림은 자동으로 변경하지 않는다.
