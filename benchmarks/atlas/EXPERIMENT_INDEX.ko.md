# 보관된 Atlas 실험

[English](EXPERIMENT_INDEX.md) | [简体中文](EXPERIMENT_INDEX.zh-CN.md) | [한국어](EXPERIMENT_INDEX.ko.md)

다섯 성능 실험을 동일한 폴더 구조로 통합했다. 기존 네 실험은 2026-10-25에 보관했고 고정 P=2 실험은 2026-10-27에 통합했다. 원시 실행 파일과 제출 소스 압축 파일의 바이트는 유지했다. 색인, 매니페스트와 체크섬은 새 구조에 맞춰 갱신했다. 최초 다운로드는 프로젝트 HPC 폴더에 남아 있다.

```text
atlas/
  manifest.json
  checksums.sha256
  runs/
    atlas-validation.1027219.venus01/
    atlas-strong.1027222.venus01/
    atlas-hybrid.1027229.venus01/
    atlas-threads.1027231.venus01/
    atlas-communication.1027272.venus01/
    atlas-thread-scaling.1028185.venus01/
  source-packages/
    project3-atlas-<study>.tar.gz
```

| Study | Job ID | Ordinary observations | Raw measurements |
|---|---|---:|---|
| 강한 확장성 | 1027222.venus01 | 35 | [strong.jsonl](runs/atlas-strong.1027222.venus01/strong.jsonl) |
| 12코어 고정 하이브리드 배치 | 1027229.venus01 | 30 | [hybrid.jsonl](runs/atlas-hybrid.1027229.venus01/hybrid.jsonl) |
| V2/V3 스레드 전략 | 1027231.venus01 | 30 | [raw.jsonl](runs/atlas-threads.1027231.venus01/raw.jsonl) |
| 통신 전략 | 1027272.venus01 | 30 | [raw.jsonl](runs/atlas-communication.1027272.venus01/raw.jsonl) |
| 고정 P=2 스레드 확장 | 1028185.venus01 | 50 | [timing.jsonl](runs/atlas-thread-scaling.1028185.venus01/timing.jsonl) |

일반 성능 측정 175개와 별도 단계 진단 50개를 구분한다. 검증/pilot과 최신 소규모 사전 검사 20회는 성능 합계에서 제외한다.

N=1,000,000; D=32; K=32; seed=42; 20 timed iterations; 2 warmups; 5 repeats/configuration.

하나의 명령으로 다섯 실험을 검증한다. --verify-only는 무결성만 확인한다. 전체 감사는 새 출력 디렉터리에서 분석을 재생성하고 원본을 유지한다. 스레드 확장 전용 진입점은 개별 감사에도 사용할 수 있다.

```sh
python3 -B scripts/reproduce_atlas.py --verify-only
python3 -B scripts/reproduce_atlas.py --output artifacts/atlas-audit-new
# Optional single-study entry point:
python3 -B scripts/reproduce_atlas_thread_scaling.py --output artifacts/thread-scaling-audit-new
```

최신 실험은 일반 시간 timing.jsonl과 별도 진단 profile.jsonl을 사용한다. 각 진단은 같은 표본의 최대 커널 시간 rank에 모든 단계를 귀속한다. 진단은 일반 성능 측정에 합치지 않는다. 누락된 PBS 로그와 다운로드하지 않은 실행 파일의 제한은 매니페스트의 해당 작업 항목에 기록했다.

[통합 보고서 결과](../../analysis/atlas/report_results.ko.md)와 [고정 P=2 결과](../../analysis/atlas/THREAD_SCALING.ko.md)를 참고한다.
