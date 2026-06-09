### Added

- Skeleton shape에 1급 `bbox = [xtl, ytl, xbr, ybr]` 필드 추가. annotator가
  그린 회색 박스가 객체 경계로 영속 저장됨. 저장된 값이 있으면 wrapping rect는
  매 렌더마다 재계산하지 않고 그대로 사용하고, 없으면(기존 skeleton) keypoint
  min/max + margin으로 도출하는 폴백을 유지.
  (`docs/plans/2026-05-19-001-feat-skeleton-bbox-persistence-plan.md`)
- COCO Keypoints import가 `annotations[i].bbox` (xywh)를 skeleton bbox로
  보존. 이전에는 `RemoveBboxAnnotations` transformer가 강제로 폐기했음.
- COCO Keypoints export 시 skeleton bbox에서 person bbox annotation을 동반
  emit해 표준 COCO Keypoints round-trip 무손실.

### Changed

- skeleton 생성/수정 REST 요청 (POST/PATCH `/api/jobs/<id>/annotations`)의
  `bbox` 필드는 **선택**. 생략하거나 빈 배열이면 "아직 미영속" 상태로 저장되고
  캔버스/export가 keypoint에서 박스를 도출. 기존 SDK/자동화 클라이언트는 수정
  없이 호환 (read-only·write 모두, breaking 아님). 값을 보내면 아래 Normal 또는
  `[0,0,0,0]`만 허용.
- skeleton 유효 bbox 상태는 셋 중 하나로 정의:
  - **Normal** — `[xtl, ytl, xbr, ybr]` with `xtl<xbr and ytl<ybr` (annotator
    가 그린 객체 경계)
  - **Degenerate** — 정확히 `[0, 0, 0, 0]` (모든 element가 `outside=true`이거나
    정규화 대기 중인 draft; 첫 정상 편집 시 자동 회복)
  - **Empty** — `[]` (bbox 미영속. bbox 필드 도입 전 생성된 기존 skeleton 및
    bbox를 안 보낸 write 요청. 캔버스/export가 keypoint extent로 폴백하고, 첫
    편집 시 soft-snap으로 영속화)
  - 그 외 입력 (zero-area non-degenerate, 역전된 좌표, len≠4)은 모두 400.
- skeleton 회전 의미 변경: 기존엔 `Shape.rotation`을 항상 0으로 강제하고
  child keypoint 좌표를 직접 회전시켰음. 이제 `Shape.rotation`이 의미 있는
  스칼라로 보존되고, child keypoint는 변형되지 않으며, 캔버스가 SVG
  transform으로 시각적 회전을 처리. 데이터셋 export (CVAT XML, COCO,
  Datumaro)도 skeleton rotation을 보존.
- skeleton 빨간 박스 corner/edge 핸들 드래그가 **bbox만** 변경하도록 의미
  재정의. 이전엔 모든 keypoint를 박스 변화에 비례해 스케일했음. line 드래그
  (테두리 잡기)는 기존 동작 유지 — bbox + keypoints가 함께 평행이동.
- skeleton keypoint를 박스 밖으로 이동시키면 bbox가 그 keypoint 좌표까지
  자동 확장 (soft-snap, 0px margin). bbox 리사이즈로 keypoint를 못 담게
  되면 outermost visible/occluded keypoint까지로 자동 clamp. `outside=true`
  keypoint는 두 검증 모두에서 제외.
- skeleton track의 frame 간 bbox는 선형 보간되어 표시. 보간 frame에서
  사용자가 bbox를 수정하면 그 frame이 자동으로 새 keyframe으로 격상됨
  (implicit keyframe — keypoint 수정과 동일한 패턴).
- Migration `0098_add_skeleton_bbox`: LabeledShape/TrackedShape에 `bbox`
  컬럼만 추가하는 순수 additive 스키마 변경 (**backfill 없음**). 기존 row
  data는 읽지도 쓰지도 않으므로 좌표 손실 위험이 없고 maintenance window도
  불필요 — 일반 배포로 적용 가능. 기존 skeleton은 bbox가 빈 채로 남아
  캔버스/export가 keypoint extent에서 wrapping rect를 도출하고, 첫 편집 시
  soft-snap이 값을 영속화.

### Fixed

- Datumaro IR을 통한 skeleton transport에서 reserved-prefix attribute
  `__cvat_bbox` 사용. `quality_control` 의 `ignored_attrs` 와
  `consensus` merge 경로에서 이 attribute를 자동 제외해 transport metadata
  가 `MISMATCHING_ATTRIBUTES` conflict를 만들지 않음.

### Removed

- `cvat/apps/dataset_manager/formats/coco.py` 의 `RemoveBboxAnnotations`
  transformer 폐기. 대체 `LinkBboxToSkeleton`이 person bbox를 그룹 키
  (또는 image당 단일 skeleton 폴백)로 매칭해 skeleton attribute에 흡수.
