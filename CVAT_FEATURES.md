# CVAT-Everex 기능 분류표

이 문서는 CVAT-Everex 코드베이스의 모든 기능을 분류하고 필수 여부를 정리한 문서입니다.

---

## 목차

1. [인프라 서비스](#1-인프라-서비스)
2. [애플리케이션 서비스](#2-애플리케이션-서비스)
3. [백그라운드 워커](#3-백그라운드-워커)
4. [프론트엔드 패키지](#4-프론트엔드-패키지)
5. [Django 앱](#5-django-앱-cvatapps)
6. [SDK & CLI](#6-sdk--cli)
7. [유틸리티 & 외부 연동](#7-유틸리티--외부-연동)
8. [테스트 & CI](#8-테스트--ci)
9. [지원 포맷](#9-지원-포맷-importexport)
10. [요약](#10-요약)

---

## 범례

| 기호 | 의미 |
|------|------|
| ✅ 필수 | 시스템 운영에 반드시 필요한 핵심 기능 |
| ❌ 선택 | 필요 시 활성화하는 선택적 기능 |
| ⚠️ 조건부 | 특정 조건에서만 필요한 기능 |

---

## 1. 인프라 서비스

시스템 운영을 위한 기반 인프라 서비스입니다.

| 서비스 | 설명 | 필수 여부 | 포트 | Docker 이미지 |
|--------|------|----------|------|---------------|
| **PostgreSQL** (cvat_db_everex) | 메인 관계형 데이터베이스 | ✅ 필수 | 5432 | postgres:15-alpine |
| **Redis In-Memory** (cvat_redis_inmem_everex) | 캐시 및 RQ 작업 큐 | ✅ 필수 | 6379 | redis:7.2.11-alpine |
| **Redis On-Disk** (cvat_redis_ondisk_everex) | 영구 데이터 저장소 (Kvrocks) | ✅ 필수 | 6666 | apache/kvrocks:2.12.1 |
| **ClickHouse** (cvat_clickhouse_everex) | 분석용 시계열 데이터베이스 | ✅ 필수 | 8123 | clickhouse/clickhouse-server:23.11-alpine |
| **Traefik** (traefik_everex) | 리버스 프록시 및 로드 밸런서 | ✅ 필수 | 8080, 8090 | traefik:v3.6 |
| **OPA** (cvat_opa_everex) | Open Policy Agent 권한 엔진 | ✅ 필수 | 8181 | openpolicyagent/opa:0.63.0 |
| **Vector** (cvat_vector_everex) | 로그 수집 및 ClickHouse 전달 | ✅ 필수 | - | timberio/vector:0.26.0-alpine |
| **Grafana** (cvat_grafana_everex) | 분석 대시보드 및 시각화 | ✅ 필수 | 3000 | grafana/grafana-oss:10.1.2 |

### 인프라 의존성 관계

```
PostgreSQL ─────────────────────────────┐
Redis In-Memory ────────────────────────┼──▶ CVAT Server & Workers
Redis On-Disk ──────────────────────────┤
OPA ────────────────────────────────────┘

ClickHouse ◀── Vector ◀── CVAT Server (이벤트 로깅)
     │
     └──▶ Grafana (시각화)

Traefik ──▶ CVAT Server, CVAT UI (라우팅)
```

---

## 2. 애플리케이션 서비스

메인 애플리케이션 서버입니다.

| 서비스 | 설명 | 필수 여부 | 포트 | 디버그 포트 |
|--------|------|----------|------|------------|
| **cvat_server_everex** | Django REST API 서버 | ✅ 필수 | 8080 | 9090 |
| **cvat_ui_everex** | React SPA 프론트엔드 | ✅ 필수 | 3000 | - |

### 서버 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `NUMPROCS` | WSGI 프로세스 수 | 2 |
| `ALLOWED_HOSTS` | 허용 호스트 | * |
| `CVAT_ANALYTICS` | 분석 기능 활성화 | 1 |
| `CVAT_DEBUG_ENABLED` | 디버그 모드 | no |

---

## 3. 백그라운드 워커

RQ(Redis Queue) 기반 백그라운드 작업 처리 워커입니다.

| 워커 | 큐 | 설명 | 필수 여부 | 타임아웃 | 디버그 포트 |
|------|-----|------|----------|---------|------------|
| **cvat_worker_import** | import | 데이터 가져오기 (COCO, YOLO 등) | ✅ 필수 | 4시간 | 9093 |
| **cvat_worker_export** | export | 데이터 내보내기 | ✅ 필수 | 4시간 | 9092 |
| **cvat_worker_annotation** | annotation | 자동 어노테이션 (AI 모델) | ✅ 필수 | 24시간 | 9091 |
| **cvat_worker_chunks** | chunks | 비디오 프레임 추출 및 청킹 | ✅ 필수 | 5분 | - |
| **cvat_worker_webhooks** | webhooks | 외부 웹훅 전송 | ✅ 필수 | 1시간 | - |
| **cvat_worker_quality_reports** | quality_reports | 품질 보고서 생성 | ✅ 필수 | 1시간 | 9094 |
| **cvat_worker_consensus** | consensus | 다중 어노테이터 합의 병합 | ✅ 필수 | 1시간 | 9096 |
| **cvat_worker_utils** | notifications, cleaning | 알림 및 정리 작업 | ✅ 필수 | 1~2시간 | - |

### Utils 워커 주기적 작업

| 작업 | 스케줄 | 설명 |
|------|--------|------|
| `clean_up_sessions` | 매일 00:00 | 세션 정리 |
| `cleanup_export_cache` | 매일 00:00, 12:00 | 내보내기 캐시 정리 |
| `cleanup_tmp_directory` | 매일 18:00 | 임시 디렉토리 정리 |
| `clear_unusable_access_tokens` | 매주 일요일 00:00 | 만료된 토큰 정리 |

---

## 4. 프론트엔드 패키지

Yarn Workspaces로 관리되는 프론트엔드 패키지입니다.

| 패키지 | 버전 | 설명 | 필수 여부 | 핵심 기술 |
|--------|------|------|----------|----------|
| **cvat-data** | 2.1.0 | 프레임 디코딩 라이브러리 | ✅ 필수 | jszip, Web Workers, Broadway.js (H.264) |
| **cvat-core** | 15.3.1 | API 클라이언트 및 비즈니스 로직 | ✅ 필수 | axios, tus-js-client, Plugin System |
| **cvat-canvas** | 2.20.10 | 2D SVG 기반 어노테이션 캔버스 | ✅ 필수 | svg.js, MVC 패턴 |
| **cvat-canvas3d** | 0.0.10 | 3D 포인트 클라우드 캔버스 | ✅ 필수 | Three.js, 4-뷰포트 시스템 |
| **cvat-ui** | 2.52.0 | React SPA 메인 UI | ✅ 필수 | React 18, Redux, Ant Design 5 |

### 패키지 의존성 흐름

```
cvat-data (기반)
    │
    ▼
cvat-core (API 클라이언트)
    │
    ├──▶ cvat-canvas (2D)
    │
    └──▶ cvat-canvas3d (3D)
            │
            ▼
        cvat-ui (통합 UI)
```

### cvat-ui 주요 기능

| 카테고리 | 기능 |
|----------|------|
| **어노테이션** | 2D/3D 캔버스, 도형 그리기, 트래킹, 태깅, 속성 편집 |
| **AI 도구** | SAM 플러그인, ONNX Runtime 추론, 모델 관리 |
| **품질 관리** | 품질 보고서, 합의 관리, 리뷰 워크플로우 |
| **데이터 관리** | 가져오기/내보내기, 클라우드 스토리지, 백업/복원 |
| **조직 관리** | 멀티테넌시, 멤버십, 초대, 웹훅 |
| **사용자 관리** | 인증, 프로필, API 토큰 |

---

## 5. Django 앱 (cvat/apps/)

백엔드 Django 애플리케이션입니다.

### 5.1 핵심 앱 (Core Apps)

시스템 운영에 필수적인 핵심 앱입니다.

| 앱 | 설명 | 필수 여부 | 주요 모델 | API 엔드포인트 |
|----|------|----------|----------|---------------|
| **engine** | 핵심 어노테이션 엔진 | ✅ 필수 | Project, Task, Job, Segment, Label, Shape, CloudStorage | /api/projects, /api/tasks, /api/jobs |
| **iam** | 인증 및 권한 관리 | ✅ 필수 | (Django User 사용) | /api/auth/* |
| **organizations** | 멀티테넌트 조직 지원 | ✅ 필수 | Organization, Membership, Invitation | /api/organizations |
| **dataset_manager** | 데이터셋 포맷 변환 (25+ 포맷) | ✅ 필수 | - | (engine에 통합) |
| **redis_handler** | Redis 캐싱 및 작업 상태 관리 | ✅ 필수 | - | /api/requests |
| **health** | 시스템 헬스체크 | ✅ 필수 | - | /api/health |
| **events** | 이벤트 로깅 (ClickHouse) | ✅ 필수 | Event | /api/events |

### 5.2 기능 앱 (Feature Apps)

선택적으로 사용 가능한 기능 앱입니다.

| 앱 | 설명 | 필수 여부 | 주요 모델 | API 엔드포인트 |
|----|------|----------|----------|---------------|
| **quality_control** | 어노테이션 품질 평가 | ❌ 선택 | QualityReport, QualitySettings, AnnotationConflict | /api/quality/* |
| **consensus** | 다중 어노테이터 합의 병합 | ❌ 선택 | ConsensusSettings | /api/consensus/* |
| **webhooks** | 외부 이벤트 알림 | ❌ 선택 | Webhook, WebhookDelivery | /api/webhooks |
| **lambda_manager** | 서버리스 함수 관리 (Nuclio) | ❌ 선택 | FunctionKind (enum) | /api/lambda/* |
| **access_tokens** | 개인 API 액세스 토큰 | ❌ 선택 | AccessToken | /api/auth/access_tokens |
| **log_viewer** | Grafana 로그 시각화 | ❌ 선택 | - | /api/logs |
| **dataset_repo** | Git 동기화 (레거시) | ❌ 제거 예정 | - | - |

### 5.3 Engine 모델 상세

| 모델 | 설명 | 주요 필드 |
|------|------|----------|
| **Project** | 프로젝트 컨테이너 | name, organization, labels |
| **Task** | 어노테이션 작업 단위 | name, project, data, labels, segment_size |
| **Segment** | 작업 분할 단위 | task, start_frame, stop_frame |
| **Job** | 작업자 할당 단위 | segment, assignee, stage, state, type |
| **Label** | 레이블 정의 | name, color, type, attributes |
| **Shape** | 도형 어노테이션 | label, type, points, frame, attributes |
| **CloudStorage** | 클라우드 스토리지 설정 | provider, resource, credentials |

### 5.4 Job 타입 및 상태

**Job Type:**
| 타입 | 설명 |
|------|------|
| `ANNOTATION` | 일반 어노테이션 작업 |
| `GROUND_TRUTH` | 정답 데이터 작업 |
| `CONSENSUS_REPLICA` | 합의용 복제 작업 |

**Job Stage:**
| 단계 | 설명 |
|------|------|
| `ANNOTATION` | 어노테이션 진행 중 |
| `VALIDATION` | 검증 단계 |
| `ACCEPTANCE` | 승인 단계 |

**Job State:**
| 상태 | 설명 |
|------|------|
| `NEW` | 새 작업 |
| `IN_PROGRESS` | 진행 중 |
| `COMPLETED` | 완료 |
| `REJECTED` | 반려 |

---

## 6. SDK & CLI

외부에서 CVAT를 프로그래밍 방식으로 사용하기 위한 도구입니다.

### 6.1 CVAT SDK (cvat-sdk/)

| 모듈 | 설명 | 필수 여부 | 주요 기능 |
|------|------|----------|----------|
| **cvat_sdk.api_client** | 저수준 API 클라이언트 | ❌ 선택 | OpenAPI 자동 생성 래퍼 |
| **cvat_sdk.core** | 고수준 프록시 클래스 | ❌ 선택 | TasksRepo, ProjectsRepo, JobsRepo |
| **cvat_sdk.auto_annotation** | 자동 어노테이션 프레임워크 | ❌ 선택 | DetectionFunction, TrackingFunction |
| **cvat_sdk.pytorch** | PyTorch 데이터셋 어댑터 | ❌ 선택 | TaskVisionDataset, ProjectVisionDataset |
| **cvat_sdk.datasets** | 데이터셋 캐싱/로딩 | ❌ 선택 | TaskDataset, CacheManager |

**SDK 의존성:**
```
기본: attrs, packaging, Pillow, platformdirs, tqdm, typing_extensions
masks: numpy >= 2.0
pytorch: torch, torchvision, scikit-image
```

### 6.2 CVAT CLI (cvat-cli/)

| 리소스 | 명령어 | 설명 | 필수 여부 |
|--------|--------|------|----------|
| **project** | ls, create, delete | 프로젝트 관리 | ❌ 선택 |
| **task** | ls, create, delete, frames, export-dataset, import-dataset, backup, auto-annotate | 태스크 관리 | ❌ 선택 |
| **function** | create-native, delete, run-agent | 서버리스 함수 (Enterprise) | ❌ 선택 |

**CLI 사용 예시:**
```bash
# 태스크 목록 조회
cvat-cli --server-host cvat.example.com task ls

# 태스크 생성
cvat-cli --auth user:password task create "my_task" local image1.jpg image2.jpg \
  --labels '[{"name": "car"}, {"name": "person"}]'

# 데이터셋 내보내기
cvat-cli task export-dataset 123 --format "COCO 1.0" --output ./export/
```

---

## 7. 유틸리티 & 외부 연동

### 7.1 유틸리티 도구

| 도구 | 위치 | 설명 | 필수 여부 |
|------|------|------|----------|
| **Dataset Manifest** | utils/dataset_manifest/ | 데이터셋 매니페스트 생성 | ❌ 선택 |
| **DICOM Converter** | utils/dicom_converter/ | 의료 영상(DICOM) 변환 | ❌ 선택 |
| **FFmpeg Compatibility** | utils/ffmpeg_compatibility/ | FFmpeg 버전 호환성 도구 | ❌ 선택 |

### 7.2 외부 연동 (Docker Compose 확장)

| 기능 | 설정 파일 | 설명 | 필수 여부 |
|------|----------|------|----------|
| **Nuclio** | components/serverless/docker-compose.serverless.yml | 서버리스 AI 함수 플랫폼 | ❌ 선택 |
| **외부 PostgreSQL** | docker-compose.external_db.yml | 외부 DB 연결 | ❌ 선택 |
| **HTTPS/Let's Encrypt** | docker-compose.https.yml | TLS/SSL 인증서 | ❌ 선택 |
| **MinIO/S3** | tests/docker-compose.minio.yml | S3 호환 오브젝트 스토리지 | ❌ 선택 |
| **이메일 서비스** | cvat/settings/email_settings.py | 알림, 비밀번호 재설정 | ❌ 선택 |
| **파일 공유/NFS** | tests/docker-compose.file_share.yml | 네트워크 파일 공유 | ❌ 선택 |

### 7.3 플러그인 시스템

| 플러그인 | 위치 | 설명 | 필수 여부 |
|----------|------|------|----------|
| **SAM Plugin** | cvat-ui/plugins/sam/ | Segment Anything Model 통합 | ❌ 선택 (기본 포함) |

**플러그인 등록 경로:**
- `annotationPage.player.slider`
- `annotationPage.menuActions.items`
- `modelsPage.*`
- `projectActions.items`, `taskActions.items`, `jobActions.items`
- `settings.player`
- `about.links.items`
- `aiTools.interactors.extras`

---

## 8. 테스트 & CI

| 기능 | 설명 | 필수 여부 | 설정 파일 |
|------|------|----------|----------|
| **cvat_ci** | CI 테스트 러너 컨테이너 | ❌ 선택 | docker-compose.ci.yml |
| **webhook_receiver** | 웹훅 테스트 서버 | ❌ 선택 | tests/docker-compose.test_servers.yml |
| **Cypress E2E** | E2E 테스트 프레임워크 | ❌ 선택 | tests/cypress.config.js |
| **Python Tests** | REST API, SDK, CLI 테스트 | ❌ 선택 | tests/python/ |
| **OPA Tests** | 권한 규칙 테스트 | ❌ 선택 | cvat/apps/*/rules/tests/ |

---

## 9. 지원 포맷 (Import/Export)

### 9.1 어노테이션 포맷

| 카테고리 | 포맷 |
|----------|------|
| **객체 탐지** | COCO, YOLO, KITTI, OpenImages, Pascal VOC |
| **인스턴스 세그멘테이션** | COCO, Mask, MOTS, Cityscapes |
| **시맨틱 세그멘테이션** | Cityscapes, CamVid |
| **트래킹** | MOT, MOTS |
| **얼굴 인식** | VGGFace2, WideFace, LFW |
| **문서 분석** | ICDAR |
| **3D 포인트 클라우드** | PointCloud, VeloPoint |
| **범용** | CVAT 1.1 (네이티브), Datumaro, LabelMe, ImageNet, Market1501 |

### 9.2 도형 타입

| 타입 | 설명 | 2D | 3D |
|------|------|----|----|
| Rectangle | 사각형 바운딩 박스 | ✅ | - |
| Polygon | 다각형 | ✅ | - |
| Polyline | 폴리라인 | ✅ | - |
| Points | 포인트 집합 | ✅ | - |
| Ellipse | 타원 | ✅ | - |
| Mask | 마스크 (브러시/지우개) | ✅ | - |
| Skeleton | 스켈레톤 (키포인트) | ✅ | - |
| Cuboid | 3D 큐보이드 | ✅ | ✅ |
| Tag | 이미지/프레임 태그 | ✅ | ✅ |

---

## 10. 요약

### 10.1 필수 vs 선택 요약표

| 구분 | 필수 (Core) | 선택 (Optional) |
|------|------------|----------------|
| **인프라** | 8개 | - |
| **애플리케이션** | 2개 | - |
| **워커** | 8개 | - |
| **프론트엔드 패키지** | 5개 | - |
| **Django 앱** | 7개 | 6개 |
| **SDK/CLI** | - | 5개 |
| **유틸리티/외부 연동** | - | 10개+ |
| **테스트** | - | 5개 |

### 10.2 최소 배포 구성

```yaml
# 필수 서비스 (18개)
인프라:
  - PostgreSQL
  - Redis In-Memory
  - Redis On-Disk (Kvrocks)
  - ClickHouse
  - Traefik
  - OPA
  - Vector
  - Grafana

애플리케이션:
  - CVAT Server
  - CVAT UI

워커:
  - Import Worker
  - Export Worker
  - Annotation Worker
  - Chunks Worker
  - Webhooks Worker
  - Quality Reports Worker
  - Consensus Worker
  - Utils Worker
```

### 10.3 선택적 확장

```yaml
# 선택 서비스
AI/ML 확장:
  - Nuclio (서버리스 함수)
  - SAM Plugin

외부 연동:
  - 외부 PostgreSQL
  - HTTPS/Let's Encrypt
  - MinIO/S3
  - 이메일 서비스
  - NFS 파일 공유

개발/자동화:
  - CVAT SDK
  - CVAT CLI
  - Dataset Manifest 도구
  - DICOM Converter
```

---

## 참고

> **Note**: 이 저장소(cvat-everex)는 원본 CVAT와 달리 Analytics 기능(ClickHouse, Vector, Grafana)이 기본으로 활성화되어 있습니다. 모든 서비스 이름에 `_everex` 접미사가 붙어있습니다.

### 관련 문서

- [CLAUDE.md](./CLAUDE.md) - 개발 가이드
- [docker-compose.yml](./docker-compose.yml) - 기본 Docker 구성
- [docker-compose.dev.yml](./docker-compose.dev.yml) - 개발 환경 구성
