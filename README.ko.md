# MPI + OpenMP를 이용한 Lloyd K-means

[English](README.md) | [简体中文](README.zh-CN.md) | [한국어](README.ko.md)

프로세스 병렬화와 스레드 병렬화 방식을 비교하기 위한 C++17 기반 Lloyd K-means 구현입니다. 직렬 기준 구현, MPI/OpenMP 병렬 버전, 수치 검증 테스트와 벤치마크 스크립트를 제공합니다. 군집화 라이브러리를 사용하지 않고 알고리즘을 직접 구현했습니다.

| 버전 | 프로세스 내부 누적 방식 | 용도 |
| --- | --- | --- |
| V0 | 직렬 처리 | 수치 검증 및 단일 코어 성능 기준 |
| V1 | 각 MPI 프로세스 내부에서 직렬 처리 | 순수 MPI 기준 구현 |
| V2 | OpenMP 공유 배열에 원자적 갱신 | 스레드 간 경합 측정 |
| V3 | OpenMP 스레드별 전용 버퍼에 누적한 뒤 병합 | 샘플 처리 루프 내부의 동기화 감소 |

병렬 실행 파일은 전역 중심점 갱신을 위해 Allreduce와 Reduce + Bcast를 모두 지원합니다.

## 빌드

C++17 컴파일러와 Make가 필요합니다. 병렬 실행 파일에는 MPI-3+와 OpenMP가 필요하며, 테스트와 스크립트에는 Python 3.8+가 필요합니다. 테스트, 벤치마크와 오프라인 검증은 Python 표준 라이브러리만 사용합니다. 선택적인 보고서 그래프 생성에는 Python 3.9+와 Matplotlib이 필요하며, 의존성은 `requirements.txt`에 있습니다.

Linux/HPC에서는 서로 호환되는 컴파일러와 MPI 모듈을 불러온 뒤 실행합니다.

```sh
make all CXX=g++ MPICXX=mpicxx
```

직렬 실행 파일만 빌드하려면 `make serial`을 사용합니다. macOS에서 Apple Clang, Homebrew Open MPI와 libomp를 사용하는 경우:

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

기본 컴파일 옵션은 `-O3 -std=c++17 -Wall -Wextra -Wpedantic`입니다. 직렬 및 병렬 실행 파일에는 동일한 기반 컴파일러와 부동소수점 옵션을 사용하세요. 컴파일러나 옵션을 바꿀 때는 `-B`를 추가하여 강제로 다시 빌드합니다.

## 빠른 시작

손으로 결과를 확인할 수 있는 예제를 실행합니다.

```sh
./build/kmeans_serial --input examples/tiny.txt --k 2 \
  --init-indices 0,2 --iterations 1 --dump --trace
```

예상 최종 중심점은 행 우선으로 나열했을 때 `[0, 1, 10, 11]`, 군집별 샘플 수는 `[2, 2]`, 레이블은 `[0, 0, 1, 1]`, SSE는 `4`입니다.

MPI 프로세스 2개와 프로세스당 스레드 2개로 합성 데이터를 처리합니다.

```sh
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 50
```

순수 MPI는 `--variant v1 --threads 1`, 원자적 누적은 `--variant v2`를 사용합니다. 통신 방식을 바꾸려면 `--comm reduce-bcast`를 지정합니다. 실행이 성공하면 stdout에 JSON 객체 하나를 출력하고, 오류는 stderr에 출력합니다.

## 데이터와 옵션

합성 데이터는 시드와 전역 샘플 인덱스로 결정되므로, 동일한 빌드 환경에서는 프로세스 수를 바꾸어도 같은 데이터가 생성됩니다. 별도의 다운로드는 필요하지 않습니다. 생성기는 알고리즘의 군집 수 `K`와 독립적으로 16개의 가우시안 그룹을 사용합니다. `--skew`를 지정하면 전체 생성 확률의 90%를 하나의 그룹에 배정합니다.

외부 데이터는 첫 줄에 `N D`가 있고, 그 뒤에 정확히 `N * D`개의 유한한 좌표 값이 있는 공백 구분 텍스트 파일로 준비합니다. ID와 레이블을 제거하고, 필요한 스케일링은 실행 전에 일관되게 적용하세요. 파일에 기록된 차원이 `--n`, `--d`보다 우선합니다. Rank 0이 파일을 읽고 Scatterv로 분배하며, 전체 좌표 값의 개수는 `INT_MAX`를 넘을 수 없습니다.

| 옵션 | 기본값 및 의미 |
| --- | --- |
| `--n`, `--d`, `--k` | `10000`, `8`, `16`; `N,D > 0`, `1 <= K <= N`이어야 함 |
| `--seed` | `42`; 데이터 생성 및 초기 샘플 선택에 사용 |
| `--input FILE` | 준비된 텍스트 데이터셋 |
| `--init-indices 0,2,...` | 서로 다른 전역 샘플 인덱스 `K`개 |
| `--variant` | 직렬: `v0`; 병렬: `v1`, `v2` 또는 기본값 `v3` |
| `--comm` | 기본값 `allreduce` 또는 `reduce-bcast` |
| `--threads` | `1`; V0와 V1은 스레드 1개만 사용 가능 |
| `--mode` | 기본값 `fixed` 또는 `converge` |
| `--iterations` | 고정 반복 모드는 기본 50회, 수렴 모드는 기본 최대 300회 |
| `--tol` | `1e-6`; 중심점의 상대 최대 이동량에 대한 허용오차 |
| `--warmup` | `0`; 지정한 횟수만큼 워밍업한 후 초기 상태로 복원 |
| `--skew` | 편향된 합성 데이터 분포 사용 |
| `--dump` | 초기 및 최종 중심점과 최종 레이블 출력 |
| `--trace` | 반복별 SSE, 군집별 샘플 수, 갱신된 중심점 기록 |
| `--profile` | 누적, 병합, 리덕션, 갱신, 브로드캐스트의 단계별 시간 기록 |

각 실행 파일에 `--help`를 지정하면 옵션 요약을 볼 수 있습니다. `--dump`와 `--trace`를 사용할 때는 `N`과 `K * D`가 모두 `100000` 이하여야 합니다.

거리와 좌표 합에는 `double`, 샘플 수에는 64비트 정수를 사용합니다. 거리가 정확히 같으면 가장 작은 군집 인덱스를 선택하며, 빈 군집은 이전 중심점을 유지합니다. 최종 레이블, 군집별 샘플 수와 SSE는 최종 중심점을 기준으로 다시 계산합니다. 부동소수점 결과는 허용오차를 두고 비교하세요. 수학 라이브러리가 다르면 가우시안 생성 결과의 마지막 비트가 달라질 수 있으므로, `data_fingerprint`로 입력을 확인합니다.

## 테스트

```sh
make test
make test-mpi
```

`make test`는 직렬 구현과 실험 도구를 테스트하며 MPI 통합 테스트는 건너뜁니다. `make test-mpi`는 실제 MPI/OpenMP 비교도 수행합니다. 여기에는 균등하게 나누어지지 않는 분할, 샘플이 없는 프로세스, 두 통신 방식, 분산 실행 중 오류 처리가 포함됩니다.

실행기를 직접 지정하려면 다음과 같이 실행합니다.

```sh
TEST_MPI=1 MPIEXEC=mpiexec MPIEXEC_FLAGS='--bind-to none' \
  python3 -m unittest discover -s tests -v
```

HPC에서는 스케줄러를 통해 충분한 코어를 할당받은 환경에서 병렬 테스트와 벤치마크를 실행하세요. `--threads`로 스레드 수를 지정합니다. 프로그램은 동적 스레드 수 조정을 비활성화하고 실제 스레드 수를 확인합니다.

## 벤치마크

실행 구성을 먼저 확인한 다음 강한 확장성 실험을 수행하고 결과를 요약합니다.

```sh
python3 scripts/benchmark.py --suite smoke --processes 1,2 --threads 2 \
  --n 10000 --d 8 --k 16 --iterations 5 --dry-run

python3 scripts/benchmark.py --suite strong --processes 1,2,4 --threads 1 \
  --n 100000 --d 32 --k 32 --repeats 5 --output results/strong.jsonl
python3 scripts/summarize.py results/strong.jsonl --output results/strong.csv
```

| 실험 모음 | 비교 내용 |
| --- | --- |
| `serial` | V0만 실행 |
| `smoke` | V0–V3 및 V3의 두 통신 방식 |
| `strong` | 문제 크기를 고정하고 프로세스 수를 변경하며 V0 기준값 포함 |
| `weak` | 프로세스당 샘플 수 고정; 전체 `N = --n * P` |
| `hybrid` | `--total-cores`를 고정하고 유효한 프로세스 수에 대해 `T = total_cores / P` 설정 |
| `threads` | 동일한 프로세스 및 스레드 구성에서 V2와 V3 비교 |
| `communication` | V3에서 Allreduce와 Reduce + Bcast 비교 |
| `sensitivity` | N, D, K 중 하나씩 변경 |

기본값은 측정 반복 50회, 워밍업 반복 2회, 구성별 실행 5회입니다. 각 실행 차수마다 구성 순서를 무작위로 섞습니다. `--launcher`에는 `{p}`와 `{t}` 자리표시자를 포함한 명령을 지정할 수 있습니다. 명령은 토큰으로 나누어 실행하며 셸을 사용하지 않습니다.

`--serial-launcher`는 V0 실행 명령 앞에 붙일 선택적 명령을 지정합니다. Linux에서는 `taskset --cpu-list 40` 등을 사용할 수 있습니다. CPU 번호는 스케줄러가 할당한 범위에서 선택하고, 측정 전에 CPU 어피니티를 확인하세요. 두 실행기 설정 모두 원시 결과에 기록되며 CSV 그룹화에도 사용됩니다. 직렬 실행기 필드가 없는 이전 결과도 읽을 수 있습니다.

Open MPI에서 필요한 코어를 할당받은 경우 다음과 같이 바인딩할 수 있습니다.

```sh
export OMP_PLACES=cores
export OMP_PROC_BIND=close
python3 scripts/benchmark.py --suite communication --processes 1,2 --threads 2 \
  --launcher 'mpiexec -n {p} --map-by slot:PE={t} --bind-to core --report-bindings' \
  --output results/communication.jsonl
```

실행기의 바인딩 보고서를 확인하고 자원 할당 내역을 기록하세요. 환경변수 설정만으로 실제 CPU 어피니티가 적용되었다고 판단할 수는 없습니다. 성능 측정에서는 할당된 코어 수보다 많은 실행 스레드를 사용하는 오버서브스크립션을 피하세요. 스케줄러와 모듈 설정은 클러스터마다 다릅니다.

원시 JSONL과 stderr 로그는 별도로 저장됩니다. CSV 요약에는 커널 실행 시간의 중앙값, 최솟값, 최댓값, 반복 실행 횟수와 SSE 범위가 포함됩니다. 기존 출력 파일은 덮어쓰지 않으며, 중복된 측정 기록은 거부합니다.

## 시간 측정과 재현성

- `kernel_seconds`는 워밍업, 초기 상태 복원과 시작 배리어 이후의 Lloyd 반복을 측정하며, 프로세스별 경과 시간의 최댓값을 사용합니다.
- 데이터 준비, 초기화, 워밍업, 최종 평가에는 별도 타이머가 있습니다. `total_seconds`는 MPI 초기화 후부터 최종 평가 종료까지, `launch_seconds`는 외부 명령의 실행 시간을 측정합니다.
- `--trace`와 `--profile`은 진단 작업을 추가하므로 벤치마크 요약에서 제외됩니다. 각 단계의 최대 시간을 더해 전체 시간을 재구성할 수는 없습니다.
- 강한 확장성의 속도 향상은 `t_serial / t_parallel`, 효율은 `speedup / (P * T)`입니다. 약한 확장성의 효율은 프로세스당 샘플 수와 스레드 수를 고정한 상태에서 `P=1`과 `P>1`을 비교합니다. 작업량과 환경이 일치하는 실행끼리 비교하세요.

벤치마크 기록에는 호스트 이름, 실행 파일 경로, 실행 명령과 작업 ID가 포함됩니다. 새 실행 결과, 외부 데이터셋, 로컬 메모, 인증 정보, 캐시와 빌드 산출물은 `.gitignore`로 제외됩니다. `benchmarks/atlas/`의 보관 기록은 명시적으로 포함됩니다.

## 완료된 Atlas 실험과 재현

저장소에는 Atlas CPU 실험 네 종류의 **정식 측정 기록 125개**와 검증 및 파일럿 기록이 포함되어 있습니다. 정식 실험은 N=1,000,000, D=32, K=32, seed=42, **측정 반복 20회**, 워밍업 2회, 구성별 실행 5회를 사용합니다. 위의 일반 기본값과 구분하세요.

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
python3 hpc/build-atlas-strategy-packages.py
```

앞의 두 명령은 MPI나 HPC 로그인 없이 파일 무결성을 확인하고 통계, 수치 결과, 기록된 CPU 배치를 다시 검증합니다. 결과는 `artifacts/atlas-audit/`에 저장하며 보관된 기록은 변경하지 않습니다. 세 번째 명령은 현재 코드로 독립 실행용 작업 패키지를 만듭니다. HPC에서 압축을 풀고 해당 디렉터리로 이동한 뒤 PBS 작업을 제출하세요. 저장소에서 `hpc/`의 PBS 파일을 직접 제출하면 안 됩니다.

자세한 내용은 [HPC 실행 안내](hpc/ATLAS_RUN_GUIDE.ko.md)와 [실험 기록 색인](benchmarks/atlas/EXPERIMENT_INDEX.ko.md)을 참고하세요. 원본 소스 패키지는 당시 버전을 보존하고 새 패키지는 현재 코드를 사용합니다. 실험 기록의 사용자명, 호스트명과 경로는 익명화하지 않고 그대로 보존했습니다.

## 보고서 그래프와 통계표

보고서용 영문 그래프 다섯 개를 PNG, PDF, SVG로 제공합니다. 정확한 CSV 통계와 영어·중국어·한국어 그림 설명도 포함됩니다. [그래프 색인](analysis/atlas/Figure/FIGURE_GUIDE.ko.md), [전체 미리보기](analysis/atlas/overview.png), [결과와 그림 설명](analysis/atlas/report_results.ko.md)을 참고하세요. 선택적 의존성을 설치한 뒤 새 디렉터리에 다시 생성할 수 있습니다.

```sh
python3 -m pip install -r requirements.txt
python3 scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

Matplotlib은 그래프 생성에만 필요합니다. `--tables-only`는 표준 라이브러리만으로 통계와 영어·중국어·한국어 그림 설명를 생성합니다. 오차 막대는 관측 최솟값과 최댓값이며 신뢰구간이 아닙니다. 비교는 같은 작업 안에서 수행하고 기준 실행을 명시합니다.

## 디렉터리 구조

```text
src/          C++ 알고리즘, 데이터 생성, MPI 런타임, JSON 출력
scripts/      벤치마크 실행 및 CSV 요약
tests/        수치 검증 및 실험 도구 테스트
examples/     손으로 예상 결과를 확인할 수 있는 작은 입력
hpc/          PBS 스크립트, CPU 배치 도구 및 독립 패키지 생성기
benchmarks/   Atlas 원본 결과, 소스 스냅샷 및 검증 자료
analysis/     보고서 그래프, 정확한 통계표, 그림 설명 및 재현 안내
Makefile      직렬 및 병렬 빌드와 테스트
```

구현, 테스트와 문서 작성에 OpenAI Codex의 도움을 받았습니다. Atlas 측정 결과와 원본 증거를 함께 제공합니다. 새로운 성능 주장은 대상 시스템에서 직접 측정해야 합니다.
