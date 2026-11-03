# 11월 그림 안내

[English](FIGURE_GUIDE.md) · [中文](FIGURE_GUIDE.zh-CN.md)

그림은 **실제 측정 대기 중**입니다. 구현은 `scripts/plot_rubric.py`이며 그리기 전에 전체 보관 자료를 검증합니다. 저장소 루트에서 실행합니다.

```sh
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
```

새 출력 디렉터리는 아래 이름마다 `.png`, `.pdf`, `.svg`를 생성합니다. SVG도 항상 포함합니다.

| 그림 | 파일명 앞부분 | 내용 |
|---|---|---|
| 1 | `figure-1-serial` | N/D/K 독립 변화와 O(INKD) 정규화 시간 |
| 2 | `figure-2-strong` | 실행 시간, 두 기준 가속비/효율, 단일 노드 경계 |
| 3 | `figure-3-weak` | 시간, T1/TP 효율, P×T1/TP 처리량 가속비 |
| 4 | `figure-4-communication` | 일반 시간과 독립 critical-rank 단계 누적 |
| 5 | `figure-5-hybrid` | 고정 256코어 배치와 순수 MPI 대비 시간 변화 |
| 6 | `figure-6-gpu` | 동일 작업 CPU1/CPU8/GPU1 루프 및 전체 시간 |

정확한 표는 `statistics.csv`, `profiles.csv`, suite별 CSV이며 영어 설명은 `captions.txt`입니다. 실제 파일 생성 전에는 결과 링크를 만들지 않습니다. 실제 출력을 검토한 뒤 세 형식을 보관하고 존재하는 파일 링크를 추가합니다. SVG는 편집 벡터, PDF는 출판/내보내기, 고해상도 PNG는 Word/Google Docs 삽입에 적합합니다.

일반 오차 범위는 5회 관측 최솟값–최댓값이며 신뢰구간이 아닙니다. 진단 누적은 실제 중간 커널 표본에서 동일한 critical rank의 전체 단계 벡터를 사용합니다. MPI 시간에는 대기가 포함됩니다. CUDA events는 독립 진단이며 동기화된 전체 루프/전체 시간을 대체하지 않습니다. [전체 방법과 보고서 구성](../../RUBRIC_GUIDE.ko.md)을 참고합니다.
