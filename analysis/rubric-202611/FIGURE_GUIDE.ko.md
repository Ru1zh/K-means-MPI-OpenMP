# Vanda 보고서 그림 안내

[English](FIGURE_GUIDE.md) · [中文](FIGURE_GUIDE.zh-CN.md) · [한국어](FIGURE_GUIDE.ko.md)

모든 그림은 검증된 실제 Vanda 측정을 사용합니다. 아래 링크는 보고서 폭에 맞게 글자를 키운 버전입니다. 원본 크기 그림과 정확한 표는 `verified-20261105/`에 보관합니다.

| Figure | Content | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | 순차 N/D/K 확장 | [PNG](paper-figures/figure-1-serial.png) | [PDF](paper-figures/figure-1-serial.pdf) | [SVG](paper-figures/figure-1-serial.svg) |
| 2 | 순수 MPI 강 확장 | [PNG](paper-figures/figure-2-strong.png) | [PDF](paper-figures/figure-2-strong.pdf) | [SVG](paper-figures/figure-2-strong.svg) |
| 3 | 순수 MPI 약 확장 | [PNG](paper-figures/figure-3-weak.png) | [PDF](paper-figures/figure-3-weak.pdf) | [SVG](paper-figures/figure-3-weak.svg) |
| 4 | 통신 및 단계 시간 | [PNG](paper-figures/figure-4-communication.png) | [PDF](paper-figures/figure-4-communication.pdf) | [SVG](paper-figures/figure-4-communication.svg) |
| 5 | 고정 256코어 MPI+OpenMP | [PNG](paper-figures/figure-5-hybrid.png) | [PDF](paper-figures/figure-5-hybrid.pdf) | [SVG](paper-figures/figure-5-hybrid.svg) |
| 6 | 동일 작업 CPU/GPU 비교 | [PNG](paper-figures/figure-6-gpu.png) | [PDF](paper-figures/figure-6-gpu.pdf) | [SVG](paper-figures/figure-6-gpu.svg) |

[Exact statistics](verified-20261105/statistics.csv) · [Independent phases](verified-20261105/profiles.csv) · [Captions](verified-20261105/captions.txt)

```sh
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py --output artifacts/paper-figures-new
```

일반 오차 막대는 5회 관측 최솟값–최댓값이며 신뢰구간이 아닙니다. 진단 누적은 한 실제 critical rank의 전체 단계를 사용하고 rank별 독립 최댓값을 합치지 않습니다. MPI는 대기를 포함합니다. 보고서 형식 변경으로 새로운 측정이나 값 변경은 발생하지 않습니다.
