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
- skeleton 회전: 회전은 child keypoint 좌표에 즉시 베이크되고
  (`Shape.rotation`은 skeleton에서 항상 0), **bbox는 회전하지 않고 항상
  axis-aligned 직사각형을 유지**. 회전 피벗은 저장된 bbox 중심(없으면
  keypoint extent 중심). 회전된 keypoint가 기존 bbox를 벗어나면 bbox가
  자동 확장되며(soft-snap), 절대 회전/축소되지 않음. 회전 제스처 중에는
  keypoint와 edge만 시각적으로 회전하고 wrapping rect는 upright 유지.
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

- skeleton track 보간에서 keyframe의 bbox가 degenerate `[0,0,0,0]`(미영속)
  이면, 그 0값을 그대로 선형보간해 이미지 원점에서 자라나는 작은 박스가
  keypoint를 벗어나던 문제 수정. 예: 첫 keyframe은 bbox 미설정 상태로 두고
  뒤쪽 keyframe에서만 bbox를 그리면 그 사이 프레임 전체의 박스가 좌상단으로
  어긋남. 이제 `getPosition`이 보간 전에 degenerate bbox를 해당 keyframe의
  keypoint extent(+margin)로 해석해, 모든 프레임에서 박스가 keypoint를 감쌈.
- skeleton track에서 keypoint가 bbox 밖으로 나가도 박스가 따라가지 않던
  문제 수정. single-keyframe keypoint는 전 프레임에 공유되는데 parent bbox
  keyframe은 독립적이라, 한 프레임에서 그 keypoint를 옮기면 그 프레임의
  bbox만 soft-snap되고 다른 keyframe(및 그로부터 보간된 모든 프레임)의
  bbox는 stale하게 남아 keypoint가 박스 밖으로 삐져나옴. 어떤 단일 편집
  훅으로도 모든 keyframe을 일관되게 유지할 수 없으므로, bbox가 도출되는
  단일 지점인 `getPosition`에서 표시 bbox가 항상 그 프레임의 visible
  keypoint를 감싸도록(확장-only) 보장. export(`toJSON`)도 각 keyframe의
  bbox를 그 keypoint를 감싸도록 확장해 재import 후 보간 정합성 유지.
- skeleton 편집(전체 이동/리사이즈/keypoint 이동) 1회가 히스토리 엔트리
  2~3개로 쪼개져 undo를 여러 번 눌러야 하고, 중간 단계에서 bbox만 따로
  복원되어 객체에서 벗어나 보이던 문제 수정. keypoint와 bbox 변경이 단일
  히스토리 엔트리로 통합되어 undo/redo 1회로 함께 복원됨. element 편집은
  부모 skeleton 1회 저장으로 합쳐져(이중 저장 제거) keypoint 이동 시
  soft-snap bbox 확장도 정상 동작.
- skeleton element 일괄 갱신(updateElements)이 부분집합을 위치 인덱스로
  매칭해 잘못된 element를 갱신할 수 있던 잠재 버그 수정 (clientID 매칭).
- label의 skeleton SVG 구조와 sublabel이 불일치할 때(`data-label-id` 누락
  등) 캔버스 전체가 TypeError로 죽던 문제 수정 — 해당 keypoint만 건너뛰고
  콘솔 경고를 남김.

- skeleton rotation이 마우스를 놓는 순간 사라지던 문제 수정: 회전이 어떤
  영속 상태에도 반영되지 않았음. 이제 마우스업 시 cvat-core가 회전을
  keypoint 좌표에 베이크하고 필요 시 bbox를 확장. 제스처 중 wrapping
  rect가 마름모꼴로 기울던 표시도 제거(항상 upright).
- skeleton track의 per-frame bbox가 implicit keyframe 생성(`copyShape`)과
  서버 reload(`convertTrackedShape`) 경로에서 유실되던 문제 수정. 보간
  frame에서 회전/편집해도 keyframe bbox가 보존되고, 새로고침 후에도 저장된
  bbox가 유지됨.
- Datumaro IR을 통한 skeleton transport에서 reserved-prefix attribute
  `__cvat_bbox` 사용. `quality_control` 의 `ignored_attrs` 와
  `consensus` merge 경로에서 이 attribute를 자동 제외해 transport metadata
  가 `MISMATCHING_ATTRIBUTES` conflict를 만들지 않음.

### Removed

- `cvat/apps/dataset_manager/formats/coco.py` 의 `RemoveBboxAnnotations`
  transformer 폐기. 대체 `LinkBboxToSkeleton`이 person bbox를 그룹 키
  (또는 image당 단일 skeleton 폴백)로 매칭해 skeleton attribute에 흡수.
