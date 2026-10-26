# Atlas 보고서 그림과 표

[English](FIGURE_GUIDE.md) | [简体中文](FIGURE_GUIDE.zh-CN.md) | [한국어](FIGURE_GUIDE.ko.md)

[그림 개요](../overview.png) 또는
[한국어 결과·캡션·표](../report_results.ko.md)를 여세요.

그림 다섯 개는 300 dpi PNG, 벡터 PDF, 텍스트를 편집할 수 있는 SVG로 제공됩니다.

| 그림 | PNG | 벡터 PDF | 벡터 SVG |
| --- | --- | --- | --- |
| 강한 확장성 실행 시간 | [PNG](01_strong_runtime.png) | [PDF](01_strong_runtime.pdf) | [SVG](01_strong_runtime.svg) |
| 속도 향상과 효율 | [PNG](02_strong_scaling.png) | [PDF](02_strong_scaling.pdf) | [SVG](02_strong_scaling.svg) |
| 고정 12코어 배치 | [PNG](03_hybrid_layouts.png) | [PDF](03_hybrid_layouts.pdf) | [SVG](03_hybrid_layouts.svg) |
| V2/V3 누적 | [PNG](04_thread_strategies.png) | [PDF](04_thread_strategies.pdf) | [SVG](04_thread_strategies.svg) |
| 통신 전략 | [PNG](05_communication.png) | [PDF](05_communication.pdf) | [SVG](05_communication.svg) |

개별 그림 파일은 이 안내서와 같은 `analysis/atlas/Figure/`(대문자 F)에 저장됩니다. 모아보기 미리보기는 `analysis/atlas/overview.png`에 있습니다. 재생성된 출력도 같은 구조를 사용합니다.

그림 2는 위쪽에 전체 척도의 속도 향상 패널, 아래쪽에 확대된 효율 패널(90–106%)을 배치합니다. 끝점 레이블은 연결선이 달린 흰색 설명 상자에 표시됩니다.
그림 3은 세로 상자그림에 관측값 다섯 개를 모두 겹쳐 표시합니다. 상자는 제1사분위수부터 제3사분위수까지이며, 검은 선은 중앙값, 수염은 관측된 최솟값부터 최댓값까지입니다.
그림 5는 가로 시간 그래프를 사용합니다. 두 시간 그래프 모두 0이 아닌 축 한계를 명시하고 전체 관측 범위를 유지합니다.
표시된 중앙값과 백분율 변화는 작은 차이를 읽기 쉽게 하며, 통계적 유의성을 뜻하지 않습니다.

## 재현

그림 렌더링에는 Python 3.9+와 선택 의존성인 Matplotlib이 필요합니다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

이 명령들은 저장소 루트에서 실행하세요. 체크인된 `analysis/atlas/`가 이미 있으므로 재생성할 때는 새 출력 디렉터리를 사용하세요.
기존 출력과 보관된 증거는 덮어쓰지 않습니다. 표와 텍스트만 생성하려면 Python 3.8+와 표준 라이브러리로 충분합니다.

```sh
python3 scripts/plot_atlas.py --tables-only --output artifacts/atlas-tables-new
```

스크립트는 보관된 SHA-256 목록을 검증하고 작업 부하, 구성 범위, 반복 실행, 데이터 동일성, 수치 일관성을 검사합니다.
배치/소스 증거에 대한 별도의 전체 감사를 실행하려면 다음 명령을 사용합니다.

```sh
python3 scripts/reproduce_atlas.py --output artifacts/atlas-full-audit-new
```

## 데이터와 정의

- 출처: `benchmarks/atlas/manifest.json`의 공식 작업 네 개. 구성 25개에서 각각 다섯 번 반복한 측정값 125개입니다. 검증/예비 실행의 시간 측정은 제외합니다.
- 지표: `kernel_seconds`. 전체 작업 시간이나 외부 실행 시작 시간이 아닙니다.
- 점: 개별 반복 실행. 마름모가 사용된 경우 중앙값을 나타내며, 그림 3은 검은 중앙값 선을 사용합니다.
  그림 3의 상자는 관측값의 가운데 50%를 나타냅니다. 수염/띠는 관측된 최솟값/최댓값이며 **신뢰구간이 아닙니다**.
  유의성 검정이나 확장 모델 적합은 사용하지 않습니다.
- 강한 확장성의 속도 향상: V0 중앙값 / V3 중앙값. 효율: 속도 향상 / (P × T).
  추가 기준은 V3 P=1로 명시합니다. 비율 띠는 기준 중앙값을 고정하며 기준의 불확실성은 포함하지 않습니다.
- 고정 자원 배치 및 전략 비교는 각 작업 자체의 측정값만 사용합니다. 상대 시간 변화는 강한 확장성 효율이 아닙니다.
- 강한 확장성의 P=12만 CPU 소켓 두 개를 사용합니다. 하이브리드와 통신 실험은 소켓 한 개 안에서 실행합니다.
  스레드 전략 작업은 소켓 두 개에 걸치지만, 테스트한 각 MPI rank는 소켓 한 개 안에 머뭅니다. 보고서에도 이 조건을 유지하세요.

`configuration_summary.csv`는 측정 시간 다섯 개 전체와 정확한 구성별 통계를 보존합니다.
`comparison_summary.csv`는 각 기준을 명시하고 속도 향상, 시간 변화, 적용 가능한 효율을 기록합니다. 고정 자원 비교의 효율 셀은 비어 있습니다.
`statistics.json`에는 전체 수치가 있습니다. `provenance.json`은 Python, Matplotlib 및 소스 스크립트/입력 해시를 기록합니다.
체크인된 파일은 Matplotlib 3.9.4로 렌더링했습니다. 다른 플랫폼이나 글꼴 조합에서는 PNG 배치가 약간 달라질 수 있습니다.

## 고정 P=2 추가 그림

추가 그림 두 개를 기존 다섯 그림과 같은 Figure 폴더에 저장했다. 일반 측정은 175개이며 진단 50개는 별도이다. overview.png는 기존 다섯 그림의 모음이다.

- [Fixed-P timing and speedup](thread-scaling-performance.png) · [SVG](thread-scaling-performance.svg)
- [Independent phase diagnosis](thread-scaling-phases.png) · [SVG](thread-scaling-phases.svg)
- [Details](../THREAD_SCALING.ko.md)
