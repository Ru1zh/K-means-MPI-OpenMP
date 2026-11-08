# MPI + OpenMP + CUDA를 이용한 Lloyd K-means

[English](README.md) · [简体中文](README.zh-CN.md) · [한국어](README.ko.md)

Lloyd K-means를 C++17로 직접 구현한 프로젝트입니다. 직렬, MPI, MPI+OpenMP 및 선택적 CUDA 버전을 포함하며 군집화 라이브러리는 사용하지 않습니다. Vanda에서 CPU 256코어와 NVIDIA A40 GPU 1개를 측정했습니다.

## 버전

| 버전 | 구현 |
|---|---|
| V0 | 직렬 기준 구현 |
| V1 | MPI rank 내부의 직렬 계산 |
| V2 | OpenMP 공유 배열의 원자적 누적 |
| V3 | OpenMP 스레드별 전용 버퍼와 병합 |
| V4 | CUDA 할당 및 2단계 통계 병합; P=1, GPU 1개 |

## 빌드

C++17 컴파일러와 Make가 필요합니다. 병렬 CPU 버전에는 MPI/OpenMP, V4에는 호환되는 CUDA toolkit과 nvcc가 필요합니다. 기본 CPU 빌드에는 CUDA가 필요하지 않습니다. HPC에서 호환되는 컴파일러와 MPI 모듈을 먼저 불러오세요.

```sh
git clone https://github.com/Ru1zh/K-means-MPI-OpenMP.git
cd K-means-MPI-OpenMP
make all CXX=g++ MPICXX=mpicxx
# Serial only:
make serial
```

선택적 GPU 빌드: 86은 측정한 A40에 해당합니다. 다른 GPU는 실제 아키텍처를 지정하세요.

```sh
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

Homebrew Open MPI와 libomp를 사용하는 macOS:

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

## 실행

합성 데이터는 메모리에서 생성하므로 다운로드나 examples 폴더가 필요하지 않습니다.

```sh
./build/kmeans_serial --n 10000 --d 8 --k 16 --iterations 20
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 20
./build/kmeans_cuda --variant v4 --n 10000 --d 8 --k 16 --iterations 20
```

순수 MPI는 `--variant v1 --threads 1`, 원자적 누적은 `v2`를 사용합니다. `--comm reduce-bcast`로 통신 방식을 바꿉니다. 전체 옵션은 실행 파일의 `--help`를 참고하세요. 성공한 실행은 stdout에 JSON 객체 하나를 출력합니다.

## 데이터와 정확성

생성기는 확률이 같은 가우시안 그룹 16개 중 하나를 선택합니다. 중심 좌표는 (-10,10)에서 생성하고 표준정규 잡음(sigma=1, Box-Muller)을 더합니다. 난수는 시드, 전역 샘플 인덱스와 좌표로 결정되어 같은 빌드 환경에서는 MPI 분할을 바꾸어도 입력이 같습니다. 초기 중심은 서로 다른 표본 K개이며 생성 그룹 수와 알고리즘 K는 독립적입니다. 정식 실행은 seed=42를 사용하고 `--skew`를 끕니다.

좌표와 합은 FP64, 개수는 64비트 정수입니다. 동률이면 가장 작은 군집 인덱스를 선택하고 빈 군집은 이전 중심을 유지합니다. 최종 레이블, 개수와 SSE는 최종 중심으로 다시 계산합니다. `--warmup` 후 초기 상태를 복원하고 측정합니다. 선택적 텍스트 입력은 첫 줄 `N D` 뒤에 유한 좌표 N×D개가 있어야 합니다.

## 테스트

Python 3.8+ 표준 라이브러리만 필요합니다. CPU/MPI 메서드 11개는 손계산 결과, 동률, 빈 군집, 불균등/빈 분할, 수렴, 워밍업 복원과 단계 타이머를 검사합니다. 선택적 GPU 메서드 3개는 CPU/GPU 수치 일치와 장치가 없을 때의 실패를 확인합니다. MPI/GPU 테스트는 적절한 자원 할당에서 실행하세요. GPU 테스트를 건너뛰는 것은 GPU 검증 통과가 아닙니다.

```sh
make test
make test-mpi
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

## HPC 실험

실행기는 Linux + PBS + Open MPI와 노드 간 공유 프로젝트 저장소를 전제로 합니다. 큐, 모듈, 제한 시간과 물리 코어 할당을 확인하세요. 사이트별 모듈 명령은 외부 환경 스크립트에 두고 GPU 작업에는 `CUDA_HOME`, `CUDA_ARCH`도 설정합니다. 아래 명령은 PBS 파일 6개를 생성합니다. 검토한 뒤 제출하세요.

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue CPU_QUEUE --gpu-queue GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
for suite in serial strong weak hybrid communication gpu; do
  qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh "artifacts/rubric-jobs/$suite.pbs"
done
```

큐 자리표시자와 환경 파일의 절대 경로를 바꾸세요. C는 {8,16,32,64} 중 사용 가능한 최댓값이며 다중 노드 작업은 서로 다른 노드 256/C개를 요청합니다. 각 작업은 소스 스냅샷, 빌드, 수치/실제 바인딩 검사를 거친 뒤 무작위 순서로 5회 측정합니다. CPU 중복, 자원 부족, GPU 오류 시 중단하며 CPU로 자동 전환하지 않습니다. 새 결과는 독립적인 `artifacts/rubric-202611/<suite>.<job-id>/`에 저장됩니다.

## 정식 실험 구성

FP64, seed=42, 측정 반복 20회, 워밍업 2회 후 초기 상태 복원, 구성별 5회를 사용합니다. 크기 변경 외에는 D=K=32입니다. 일반 기록 275개와 독립 진단 75개입니다.

| 연구 | 구성 | 일반 / 진단 기록 |
|---|---|---:|
| 직렬 | V0: N={100k,200k,500k,1M,2M,4M}; D,K={8,16,32,64,128}, 한 변수씩 변경; 기준 N=1M,D=K=32 | 70 / 0 |
| 강한 확장 | V0 기준 + V1/P={1,2,4,8,16,32,64,128,256}; N=4M | 50 / 15 |
| 약한 확장 | V1, 같은 P; N=100k×P | 45 / 15 |
| 혼합 | V2/V3, P×T={256×1,128×2,64×4,32×8}, V1/256 기준 포함 | 45 / 10 |
| 통신 | V1/P={C,256}, Allreduce와 Reduce+Bcast 비교 | 20 / 20 |
| GPU | N={100k,1M,4M}; 같은 작업에서 V0/CPU1, V3/CPU8, V4/GPU1 | 45 / 15 |

## 시간 측정과 해석

`kernel_seconds`는 가장 느린 rank의 전체 반복 루프 시간입니다. `total_seconds`는 데이터 준비, 초기화, GPU 설정/업로드, 워밍업과 최종 평가를 포함하고 MPI 초기화 및 외부 실행 시작은 제외합니다. `--profile`은 독립 진단에만 사용합니다. CPU 단계 분석은 실제 critical rank 하나의 전체 벡터를 사용하며 GPU 구간은 CUDA events로 측정합니다. MPI 시간에는 대기도 포함됩니다.

강한 확장 가속비는 같은 작업의 V0 또는 V1/P=1 기준이며 효율은 S/P입니다. 약한 확장 효율은 T1/TP, 처리량 가속비는 P×T1/TP입니다. 혼합 비교는 P×T=256을 고정합니다. 대응되는 작업 안에서만 비교하고 오차 범위는 5회 관측 최솟값–최댓값이며 신뢰구간이 아닙니다.

<!-- LOCAL_ARCHIVE_START -->

## 로컬 결과와 그림

GitHub 저장소에는 코드, 집계표와 보고서 그림을 포함합니다. 원시 작업 로그와 과거 소스 스냅샷은 현재 Git 추적에서 제외하고 로컬에 보관하며 원시 증거 감사 명령에는 해당 로컬 보관본이 필요합니다. 여섯 Vanda 작업은 2026년 11월 5일 검증되었습니다. Intel Xeon Platinum 8452Y, 노드당 실제 물리 코어 C=64, 최대 4노드 및 A40 1개; GCC 11.3.0, Open MPI 4.1.8, CUDA 12.4.131입니다.

256코어 강한 확장은 V0 대비 가속비 130.75배, 효율 51.07%이며 약한 확장 효율은 57.37%입니다. V3는 V2의 누적 비용을 줄였지만 순수 MPI 대비 1.04%의 루프 차이는 관측 범위가 겹칩니다. GPU 루프는 CPU1 대비 11.05–13.00배 빠르지만 전체 실행 이득은 더 작습니다.

| 그림 | 내용 | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | 직렬 N/D/K 확장 | [PNG](analysis/rubric-202611/paper-figures/figure-1-serial.png) | [PDF](analysis/rubric-202611/paper-figures/figure-1-serial.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-1-serial.svg) |
| 2 | MPI 강한 확장 | [PNG](analysis/rubric-202611/paper-figures/figure-2-strong.png) | [PDF](analysis/rubric-202611/paper-figures/figure-2-strong.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-2-strong.svg) |
| 3 | MPI 약한 확장 | [PNG](analysis/rubric-202611/paper-figures/figure-3-weak.png) | [PDF](analysis/rubric-202611/paper-figures/figure-3-weak.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-3-weak.svg) |
| 4 | 통신 및 단계 비율 | [PNG](analysis/rubric-202611/paper-figures/figure-4-communication.png) | [PDF](analysis/rubric-202611/paper-figures/figure-4-communication.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-4-communication.svg) |
| 5 | 고정 256코어 MPI+OpenMP | [PNG](analysis/rubric-202611/paper-figures/figure-5-hybrid.png) | [PDF](analysis/rubric-202611/paper-figures/figure-5-hybrid.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-5-hybrid.svg) |
| 6 | 같은 작업의 CPU/GPU 비교 | [PNG](analysis/rubric-202611/paper-figures/figure-6-gpu.png) | [PDF](analysis/rubric-202611/paper-figures/figure-6-gpu.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-6-gpu.svg) |

[정확한 통계](analysis/rubric-202611/verified-20261105/statistics.csv) · [독립 단계 요약](analysis/rubric-202611/verified-20261105/profiles.csv)

```sh
python3 scripts/reproduce_rubric.py --verify-only
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py \
  --from-tables analysis/rubric-202611/verified-20261105 \
  --output artifacts/report-figures-new
```

`--verify-only`에는 봉인된 전체 로컬 원시 보관본이 필요합니다. 다시 봉인하거나 실측 스냅샷을 수정하지 마세요. 집계 CSV 기반 그림 재생성은 로컬 표가 필요하며 원시 증거 감사가 아닙니다. 시간, 문제 크기와 수치형 CPU 개수 축은 로그 눈금이며 단계 비율과 효율은 선형입니다. 자세한 논의는 보고서에 있습니다. OpenAI Codex가 구현과 문서 작성을 도왔습니다.

<!-- LOCAL_ARCHIVE_END -->
