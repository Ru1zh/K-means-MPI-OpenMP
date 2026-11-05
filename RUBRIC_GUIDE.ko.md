# 11월 평가 기준 실험 안내

[English](RUBRIC_GUIDE.md) · [中文](RUBRIC_GUIDE.zh-CN.md)

Vanda 실험 여섯 개가 완료되어 2026년 11월 5일 로컬 검증을 통과했습니다. **일반 측정 275개와 독립 진단 75개**로 순차 N/D/K 분석, 256코어 순수 MPI 강/약 확장, 고정 자원 MPI+OpenMP, 통신 및 단일 GPU CUDA 비교를 다룹니다. [검증된 결과](analysis/rubric-202611/RESULTS.ko.md)를 참고하세요.

실제 호스트는 Intel Xeon Platinum 8452Y이며 CPU 72개, 소켓 2개, 소켓당 36코어, 코어당 스레드 1개, NUMA 노드 2개를 노출합니다. CPU 실험은 노드당 실제 64코어와 최대 4노드를 사용합니다. PBS는 CPU 메모리를 노드당 444 GB로, GPU 할당을 CPU 36개/240 GB/A40 1개로 정규화했습니다. GPU 비교의 실제 사용 자원은 CPU1, CPU8 또는 GPU1입니다. GCC 11.3.0, Open MPI 4.1.8, CUDA 12.4.131(sm_86)을 사용했습니다. 아래 계획 예시보다 실제 기록을 우선합니다.

## 알고리즘과 평가 항목

Lloyd의 각 반복은 최근접 중심 할당, 군집별 좌표 합/개수 누적, 전역 충분통계량 축약, 중심 갱신 순서로 실행됩니다. 거리가 같으면 가장 작은 군집 번호를 선택하고 빈 군집의 중심은 유지합니다. 고정 I회 거리 계산은 O(INKD), rank별 전역 통계량 크기는 O(KD)입니다. 전역 표본 번호로 데이터를 나누므로 불균등 분할과 빈 rank를 지원하며 생성기는 rank 수와 무관합니다.

V0는 순차 기준, V1은 rank 내부 순차 계산과 MPI, V2는 OpenMP atomic, V3는 패딩을 둔 스레드별 통계 버퍼와 로컬 병합입니다. 새 V4는 표본을 GPU 메모리에 유지하고 첫 CUDA 커널에서 거리와 block별 독립 통계량을 계산한 뒤 두 번째 커널에서 병합합니다. FP64 통계량을 호스트로 복사하여 기존 MPI 축약/중심 갱신을 사용하고 매 반복 새 중심을 GPU로 보냅니다. V4는 현재 **P=1, 호스트 스레드 1개만** 허용합니다. 다중 노드 MPI+OpenMP 연구와 별도로 단일 GPU를 검증하며 다중 GPU 확장으로 주장하지 않습니다.

| 평가 | 필요한 증거 |
|---|---|
| 알고리즘, 5점 | Lloyd 단계, 복잡도, 데이터 소유, 동기화 의존성 |
| 순차 확장, 5점 | V0의 N/D/K 독립 변화와 seconds/(INKD) |
| MPI, 10점 | 실제 256코어까지 V1, 강/약 확장, 가속비, 효율, 통신 |
| MPI+X, 10점 | 총 256코어 V2/V3 및 최소 GPU 1개에서 실제 CUDA 실행 |
| 토론, 5점 | 측정된 병목, 병렬화 선택, 호스트/장치 전송, 한계 |

합성 데이터로 충분하며 Kaggle 다운로드는 필요하지 않습니다. 생성 군집은 항상 16개로 solver K와 독립적입니다. K 변경은 계산량과 모델 용량을 바꾸며 생성 과정을 바꾸지 않습니다.

## 정확한 실험 행렬

FP64, seed=42, 측정 반복 20회, 준비 반복 2회, 설정별 재측정 5회를 사용합니다. 준비 반복 후 초기 중심을 복원합니다. 정확성 검증/단계 진단은 일반 시간 측정과 분리합니다.

| 실험 | 일반 설정 | 독립 진단 설정 | 일반/진단 기록 |
|---|---|---|---:|
| serial | V0: N={10만,20만,50만,100만,200만,400만}; D={8,16,32,64,128}; K={8,16,32,64,128}; 기준 N=100만,D=K=32; 중복 제거 | 없음 | 70 / 0 |
| strong | V0 및 V1/P={1,2,4,8,16,32,64,128,256}; N=400만,D=K=32 | V1/P={1,C,256} | 50 / 15 |
| weak | 동일 P 목록의 V1; N=10만×P,D=K=32 | P={1,C,256} | 45 / 15 |
| hybrid | V2/V3, P×T={256×1,128×2,64×4,32×8}, 추가 V1/256×1; N=400만 | V2/V3의 32×8 | 45 / 10 |
| communication | V1/P={C,256}, Allreduce와 Reduce+Bcast; N=400만 | 네 설정 모두 | 20 / 20 |
| gpu | N={10만,100만,400만},D=K=32; 같은 GPU 작업에서 V0/CPU1, V3/CPU8, V4/GPU1 | 세 V4 크기 | 45 / 15 |
| 합계 | 55개 설정 | 15개 설정 | **275 / 75** |

C는 {8,16,32,64} 중 검증된 2의 거듭제곱입니다. 노드의 실제 물리 코어와 큐 제한을 넘지 않는 최대값을 선택하며 상한은 64입니다. 다중 노드 연구는 서로 다른 노드 256/C개를 요청합니다. KVM이 보여 주는 전체 토폴로지를 할당 코어로 취급하지 않습니다. 순차/GPU 작업은 노드 1개, GPU 작업은 CPU 코어 8개와 GPU 1개를 요청합니다. `--dry-run`은 다섯 번의 반복을 펼치지 않고 고유 설정을 한 번씩 보여 줍니다.

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 scripts/benchmark.py --suite sensitivity --variant v0 --processes 1 --threads 1 --dry-run
```

## 클러스터 준비

먼저 할당받은 CPU/GPU pilot에서 큐 시간/노드 제한, `qstat -Qf`, `lscpu`, `mpiexec --version`, `mpicxx --showme`, `nvcc --version`, `nvidia-smi -q`를 확인합니다. 새 실행기는 **PBS + Open MPI + Linux**용이며 모든 노드에서 공유 프로젝트 디렉터리와 동일한 Python 경로가 필요합니다. `PBS_NODEFILE`에는 노드별 C개 이상의 slot이 있어야 합니다. 다른 MPI/nodefile 규칙이라면 실행기를 수정하고 배치 사전 검증을 다시 수행해야 합니다.

저장소 밖에 `/absolute/path/kmeans-env.sh` 같은 환경 스크립트를 만들어 확인한 컴파일러/MPI/CUDA 모듈을 로드합니다. GPU 작업에는 `CUDA_HOME`, `CUDA_ARCH`도 설정합니다. 예를 들어 80은 실제 장치의 계산 능력이 8.0일 때만 적절합니다. V4는 계산 능력 >=6.0과 호환되는 nvcc/호스트 컴파일러가 필요합니다. CUDA 13은 이전 아키텍처를 지원하지 않을 수 있으므로 도구가 지원하는 target을 확인합니다. CPU에는 C++17/OpenMP와 Open MPI가 필요합니다. 전체 실험은 몇 시간이 걸릴 수 있습니다. 큐 한도를 먼저 확인하며 각 전체 suite에 필요한 시간을 확보합니다.

```sh
make all CXX=g++ MPICXX=mpicxx
# CUDA 환경에서만:
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
# pilot에서 확인한 실제 큐 이름으로 바꿉니다.
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue ACTUAL_CPU_QUEUE --gpu-queue ACTUAL_GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
```

생성기는 검토 가능한 PBS 파일 6개만 만들고 제출하지 않습니다. 검토한 뒤 저장소 루트에서 실험별로 제출합니다.

```sh
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/serial.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/strong.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/weak.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/hybrid.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/communication.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/gpu.pbs
```

`place=scatter:excl`로 독점적인 서로 다른 노드를 요청합니다. 작업은 스케줄러/물리 코어/도구 정보를 저장하고 빌드, 수치/배치 검증을 통과한 뒤 섞인 순서로 5회 측정합니다. Open MPI 자체 바인딩을 끄고 래퍼가 rank마다 겹치지 않는 물리 코어 집합과 단일 코어 `OMP_PLACES`를 설정합니다. 프로그램은 실제 작업 스레드의 CPU와 affinity mask를 기록합니다. 사전 검증과 모든 측정은 rank 누락, 잘못된 스레드 수, SMT 중복, 코어 겹침, 잘못된 노드 배치를 거부합니다. 256코어 사전 검증은 단일 스레드 rank 256개와 모든 혼합 배치를 실제로 실행합니다. GPU 없음/실행 실패/메모리 부족은 종료 오류이며 CPU로 전환하지 않습니다. PBS 파일과 스케줄러 `.o*` 출력도 보관합니다.

결과는 `artifacts/rubric-202611/<suite>.<job-id>/probe/` 및 `measurements/`에 저장됩니다. probe는 스케줄러/도구 로그, 토폴로지, 할당, 수치 결과, 검증된 바이너리/소스 해시, 해당 GPU 정보를 포함합니다. measurements는 일반 `raw.jsonl`, 독립 `profiles.jsonl`, 소스 목록, 할당과 각 명령 stdout/stderr를 포함합니다. 기존 디렉터리를 덮어쓰지 않습니다. 실패/불완전 작업은 진단용으로 남기고 정식 비교에 포함하지 않으며 새 작업 디렉터리에서 전체 suite를 다시 실행합니다. 소스/바이너리 변경 시 사전 검증이 무효가 되고, 채택한 여섯 작업은 같은 소스 스냅샷을 사용해야 합니다.

## 검증과 시간 정의

```sh
make test
make test-mpi
# GPU 할당에서만; 노트북에서 skipped는 GPU 검증 통과가 아닙니다.
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
```

CPU 테스트/사전 검증은 동률, 빈 군집, 불균등 분할, 빈 rank, 두 collective, 노드 간 실행을 다룹니다. GPU는 작은 데이터의 레이블/개수/중심을 V0와 비교하며 중심 허용 오차는 rtol=1e-8, atol=1e-10입니다. 세 전체 크기에서는 fingerprint, 초기 인덱스, 개수, 최종 SSE를 비교합니다. GPU SSE 상대 오차 한도는 1e-8, 같은 CPU 작업량 비교는 1e-10입니다. 독립 진단에서만 CUDA events로 할당, tile 병합, 전송 시간을 측정합니다. CPU 시간 경계에서 장치를 동기화합니다. [NVIDIA 시간 측정 안내](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#timing)를 참고합니다.

`kernel_seconds`는 가장 느린 rank의 전체 측정 루프로 계산, 전송, 통신, 호스트 중심 갱신을 포함합니다. `total_seconds`는 생성, 초기화, GPU 할당/업로드, 준비 반복, 측정 루프, 최종 평가를 포함하지만 MPI 초기화/프로세스 시작/종료는 제외합니다. `launch_seconds`는 외부 프로세스 실행 대기 시간을 별도로 기록합니다. 최초 업로드는 CPU 벽시계 시간, 매 반복 H2D/D2H 진단은 CUDA event 구간입니다. 진단 오버헤드는 일반 통계에 섞지 않습니다. CPU 단계 그림은 한 실제 표본의 동일한 critical rank 전체 단계 벡터를 사용합니다. MPI 시간은 대기를 포함하며 순수 네트워크 지연이 아닙니다.

강 확장은 같은 작업의 V0와 V1/P=1 두 기준으로 E=S/P를 계산합니다. 약 확장은 E=T1/TP, 처리량 가속비 P×T1/TP를 사용합니다. 작은 P=1 문제를 최대 N의 순차 기준으로 부르지 않습니다. 혼합 비교는 256개 코어를 고정하고 같은 작업의 V1/256을 기준으로 합니다. 오차 범위는 5회 관측 최솟값–최댓값입니다.

## 보관, 재현, 제출

각 PBS 작업은 빌드 전에 `<job>/source/`에 소스/검증 테스트의 독립 스냅샷을 만들어 동시 빌드 충돌을 피합니다. 각 측정 전후 소스와 실행 파일 해시를 확인합니다. 사전 검증/측정 완료 목록은 모든 실행 및 자원 로그를 요구하고, 오프라인 감사는 보존된 스냅샷과 제출 소스도 비교합니다. `source/`, `job.pbs`, `job.stdout`, `probe/`, `measurements/`를 함께 보관하세요.

여섯 **완전한 작업 디렉터리**를 `benchmarks/rubric-202611/runs/`에 복사하고 각각 `probe/`, `measurements/`, PBS, 스케줄러 출력을 유지합니다. 정식 보관에는 suite별 완전한 작업 하나만 선택하고 실패/대안 작업은 밖에 둡니다.

```sh
python3 scripts/reproduce_rubric.py --status
python3 scripts/reproduce_rubric.py --seal --verify-only
python3 scripts/reproduce_rubric.py --verify-only
python3 scripts/reproduce_rubric.py --tables-only --output artifacts/rubric-tables
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
python3 scripts/package_rubric.py --output artifacts/kmeans-rubric-source.zip
python3 scripts/package_rubric.py --verify artifacts/kmeans-rubric-source.zip
```

`--seal`은 350개 기록을 모두 검증한 뒤 덮어쓸 수 없는 체크섬 목록을 생성합니다. 이후 검증은 누락/수정/추가 증거를 거부합니다. 소스 ZIP에도 파일별 해시가 있습니다. 압축을 푼 뒤 빌드하고 같은 오프라인 검증/생성 명령을 실행합니다. Matplotlib은 그림에만 필요하고 수치/감사는 표준 라이브러리를 사용합니다. 새 그림은 지정한 새 디렉터리에 생성됩니다. 실제 측정 후 검토한 PNG/PDF/SVG, 정확한 CSV, 설명을 `analysis/rubric-202611/`에 보관합니다. [그림 안내](analysis/rubric-202611/FIGURE_GUIDE.ko.md)를 참고합니다.

## 보고서 구성과 보호 내용

결과 순서는 순차 크기 → MPI 강 확장 → MPI 약 확장 → 통신 → MPI+OpenMP → GPU입니다. 데이터 배치, 충분통계 통신(축약당 double KD개와 64비트 개수 K개, 프로토콜 오버헤드 제외), atomic 경쟁과 전용 버퍼 메모리/병합 비용, 노드 경계, 호스트/장치 비용을 설명합니다. 합성 데이터로 실제 외부 데이터셋의 결론을 주장하지 않습니다. 새 로그 감사 전에는 가속비나 256코어/GPU 완료를 주장하지 않습니다.

새 CPU/GPU 환경은 새 probe를 근거로 별도 문단에 작성합니다. 현재 수동 페이지 나눔, 세 선 표, References 별도 페이지를 유지합니다. AI 선언은 수정하지 않고 마지막 별도 페이지에 둡니다.

> We used [GPT-6.1 sol] to [help code, create tables and beautify assignment]. We are responsible for the content and quality of the submitted work.

보고서의 성능 표와 결론은 검증된 Vanda 결과를 반영했습니다. 온라인 문서와 최종 PDF를 함께 갱신합니다.

여섯 정식 실험과 로컬 검증이 완료되어 보고서에 Vanda 결과를 반영했습니다. 남은 제출 단계는 검토와 패키징입니다. 마감은 2026년 11월 13일입니다. 다중 GPU 확장과 추가 GPU 최적화 버전은 포함하지 않습니다.
