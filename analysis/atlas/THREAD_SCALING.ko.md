# 고정 P=2 스레드 확장 검증 결과

작업 `1028185.venus01`이 완료되었다. 일반 시간 측정 50개, 별도 단계 진단 50개, 소규모 사전 검사 20회를 로컬에서 재검증했다. 기존 네 실험과 합쳐 일반 성능 측정은 175개이며 진단은 별도 집계한다.

[전체 한국어 분석](thread-scaling-results.ko.md), [영문 보고서 추가 원고](../../../Report/Thread_Scaling_Addendum_20261027.md), [로컬 검증 요약](thread-scaling-local-review.json), [원본 목록](../../benchmarks/atlas/manifest.json)을 참고한다.

Code에서 `python3 -B scripts/reproduce_atlas_thread_scaling.py`를 실행하면 보관된 제출 패키지의 분석기로 새 복사본을 검증한다. CSV 두 개와 세 언어 분석은 바이트 단위로 일치한다. 감사 입력 목록에는 최초 분석 이후 종료 스크립트가 생성한 status.txt만 추가된다. PBS 스케줄러 상태와 외부 stdout 로그는 다운로드에서 찾지 못했다. 종료 0은 작업 내부 상태 파일 기준이다. 실행 파일은 다운로드하지 않아 기록된 해시와 측정의 연결만 확인했다.

기존 PDF와 10월 25일 배포 패키지는 변경하지 않았으며 이 추가 실험을 포함하지 않는다.
