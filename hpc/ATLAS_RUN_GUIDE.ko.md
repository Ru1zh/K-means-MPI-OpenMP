# Atlas 실험

[English](ATLAS_RUN_GUIDE.md) | [简体中文](ATLAS_RUN_GUIDE.zh-CN.md) | [한국어](ATLAS_RUN_GUIDE.ko.md)

이 디렉터리에는 PBS 작업 진입점, CPU affinity 도구, 실행 패키지 준비 도구가 있습니다.
보관된 측정값과 원본 소스 스냅샷은
[benchmarks/atlas](../benchmarks/atlas/EXPERIMENT_INDEX.ko.md)에 있습니다.

## 기록된 실험을 로컬에서 재검증하기

저장소 루트에서 Python 3.8+ 및 표준 라이브러리를 사용합니다.

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
```

두 번째 명령은 공식 측정 기록 125개 전체를 감사하고, 통계를 다시 계산하며,
수치 결과와 기록된 프로세스 배치 증거를 검사합니다. 복사본과 재생성된 보고서는
`artifacts/atlas-audit/`에 저장하며, 보관된 입력은 변경하지 않습니다.
다시 실행할 때는 `--output artifacts/atlas-audit-2`로 다른 출력 디렉터리를 선택할 수 있습니다.
검증/예비 실행 작업은 무결성 검사에 포함되지만, 공식 기록 125개에는 포함되지 않으며
공식 감사 스크립트 네 개가 다시 실행하는 대상도 아닙니다.
이 오프라인 분석에는 MPI 설치나 클러스터 로그인이 필요하지 않습니다.

## 현재 체크아웃에서 새 HPC 실행 준비하기

```sh
python3 hpc/build-atlas-strategy-packages.py
```

이 명령은 `artifacts/atlas-packages/` 아래에 독립적인 아카이브 여섯 개를 만들며,
각 아카이브에 포함된 모든 소스 파일의 SHA-256 매니페스트를 생성합니다.
출력 디렉터리가 이미 있으면 실행을 거부합니다. 일부 실험만 준비하거나 다른 출력 디렉터리를 사용하려면 다음과 같이 실행합니다.

```sh
python3 hpc/build-atlas-strategy-packages.py --studies threads communication \
  --output artifacts/atlas-packages-new
```

이 새 패키지에는 **현재 체크아웃**이 포함됩니다. 기록된 작업에서 사용한 정확한 소스가 필요하면
`benchmarks/atlas/source-packages/`를 사용하세요. 보관된 패키지를 새로 생성한 패키지로 교체하지 마세요.

평소 사용하는 파일 전송 방식으로 필요한 아카이브를 Atlas에 전송합니다.
Atlas에서 압축을 풀고 해당 디렉터리로 이동한 다음, 그 디렉터리에서 작업을 제출합니다.

```sh
tar -xzf project3-atlas-strong.tar.gz
cd project3-atlas-strong
sha256sum -c source-manifest.sha256
qsub atlas-strong.pbs
```

진입점 여섯 개는 `atlas-smoke.pbs`, `atlas-validation.pbs`,
`atlas-strong.pbs`, `atlas-hybrid.pbs`, `atlas-threads.pbs`,
`atlas-communication.pbs`입니다. 과거 스냅샷에 모두 소스 매니페스트가 있는 것은 아닙니다.
매니페스트가 없는 이전 패키지를 사용할 때는 체크섬 명령을 건너뛰세요.

**체크아웃에서 `qsub hpc/atlas-strong.pbs`를 직접 제출하지 마세요.** PBS 스크립트는
소스와 보조 도구가 `PBS_O_WORKDIR`에 함께 있다고 가정합니다. 패키지 빌더가 이 평면 작업 디렉터리 구조를 만듭니다.
작업은 동일한 작업 디렉터리 안의 빌드 출력을 공유하므로, 각 실험은 별도로 압축을 푼 디렉터리를 사용해야 합니다.
하나의 체크아웃 또는 압축 해제 작업 디렉터리에서 여러 실험 작업을 실행하지 마세요.

## 기록된 환경과 작업 부하

- CPU 구현: C++17, MPI + OpenMP. GPU는 사용하지 않습니다.
- 기록된 모듈: `miniconda/4.12`, `openmpi/4.1.2`, `gcc/9.2.0`.
- PBS 설정: `parallel` 큐, 노드 한 개, CPU 12개, 메모리 8 GB, 경과 시간 한도 30분.
  새로 실행하기 전에 해당 모듈과 자원을 사용할 수 있는지 확인하세요.
- 공식 작업 부하: N=1,000,000, D=32, K=32, seed=42, 측정 반복 고정 20회,
  워밍업 반복 2회, 구성별 반복 실행 5회. 입력은 메모리에서 생성합니다.
- 강한 확장성: V0 기준과 P=1,2,3,4,6,12, T=1의 V3(기록 35개).
- 하이브리드: P/T=1/12,2/6,3/4,4/3,6/2,12/1의 V3(기록 30개).
- 스레드 전략: P/T=2/6,4/3,6/2의 V2/V3(기록 30개).
- 통신: 동일한 배치에서 V3 Allreduce/Reduce+Bcast(기록 30개).

새 작업은 `results/atlas-<study>.<PBS_JOBID>/`에 결과를 씁니다. 간단한 smoke 작업은 예외로 PBS 출력에 씁니다.
결과 디렉터리와 PBS 출력을 내려받고, 가능하면 `qstat -xf JOBID`로 완료된 작업의 스케줄러 메타데이터를 저장하세요.
전체 과거 감사에는 프로그램 출력뿐 아니라 `pbs-job.txt`도 사용합니다.
실행 시간은 할당된 CPU, 토폴로지, 부하에 따라 달라집니다. 동일한 작업 내에서 대응하는 구성을 비교하세요.
같은 절차를 따르더라도 경과 시간이 완전히 같아지는 것은 아닙니다.

## 테스트

```sh
python3 -m unittest discover -s hpc -v
make test
```

HPC 단위 테스트는 기록되거나 구성된 배치를 사용하며 실제 PBS 작업을 제출하지 않습니다.
실제 MPI 통합 테스트를 하려면 적절한 시스템에서 `make test-mpi`를 사용하거나 검증 패키지를 제출하세요.
과거 실행 지침은 `benchmarks/atlas/source-packages/`의 원본 소스 스냅샷에 있습니다.
현재 명령은 이 가이드에 통합되어 있습니다.
새 패키지는 보조 도구를 평면 구조로 배치하고 실행 의존성만 포함합니다.
저장소의 오프라인 감사는 전체 체크아웃에서 실행하세요.
