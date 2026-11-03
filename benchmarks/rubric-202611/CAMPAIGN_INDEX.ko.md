# 새 평가 실험 증거 색인

[English](CAMPAIGN_INDEX.md) · [中文](CAMPAIGN_INDEX.zh-CN.md)

상태: **새 HPC 측정 대기 중**. 새 실행 시간이나 그림이 있다고 주장하지 않습니다.

`runs/`에 serial, strong, weak, hybrid, communication, gpu의 완전한 작업 디렉터리 6개를 둡니다. 각각 `probe/`, `measurements/`, PBS, 스케줄러 출력을 보관하며 일반/진단 파일을 분리합니다. 목표는 일반 275개와 독립 진단 75개입니다.

실행/검증/보관/패키징은 [실험 안내](../../RUBRIC_GUIDE.ko.md)를 참고합니다. 저장소 루트에서 `python3 scripts/reproduce_rubric.py --status`를 실행합니다. 여섯 작업의 전체 감사 통과 후에만 `--seal --verify-only`로 `evidence-sha256.json`을 만듭니다. 이후 검증은 모든 증거 파일을 확인합니다. 소스 ZIP에는 별도 `PACKAGE-SHA256.json`이 있습니다.

`campaign.json`은 계획 행렬과 대기 상태이며 완료된 측정 목록이 아닙니다. 실제 HPC 검증 전에는 완료로 표시하지 않습니다.
