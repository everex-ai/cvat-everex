-- 가공/검수 소요 시간 측정 쿼리 세트
--
-- 대상: ClickHouse `cvat.events` (프로덕션). 로컬 덤프로 돌릴 때는 `cvat.` -> `prod_dump.` 치환.
-- 실행:
--   docker exec cvat_clickhouse_everex clickhouse-client --user user --password user \
--     --param_proj=147 --query "<쿼리>"
--
-- 실험의 task 1/2/3 = CVAT project 3개. 각 project를 {proj}로 넣어 3회 실행 후 비교한다.
--
-- 두 가지 시간을 구분한다:
--   effort   = 실작업 시간. send:working_time 합계. 자리비움/야간/대기 제외.
--   leadtime = 벽시계 시간. 착수 -> 최종 승인. 검수 대기와 야간을 포함.
-- 검증 데이터(project 147, 118 job)에서 effort/leadtime = 9~18%. 둘을 섞으면 안 된다.


-- ============================================================
-- 0. 셋업 - job 단위 집계 뷰 (다른 모든 쿼리가 이걸 쓴다)
-- ============================================================
-- 검수자는 자동 판별한다: stage -> acceptance 전이를 수행한 사람.
-- 작업자는 job별로 실작업 시간이 가장 많은 비검수자.

DROP VIEW IF EXISTS cvat.job_metrics;
CREATE VIEW cvat.job_metrics AS
WITH
    reviewers AS (
        SELECT DISTINCT user_id FROM cvat.events
        WHERE project_id = {proj:UInt64}
          AND scope = 'update:job' AND obj_name = 'stage' AND obj_val = 'acceptance'
    ),
    wt AS (
        SELECT job_id, user_id, any(user_name) AS user_name, sum(duration) AS ms
        FROM cvat.events
        WHERE project_id = {proj:UInt64} AND scope = 'send:working_time' AND job_id IS NOT NULL
        GROUP BY job_id, user_id
    )
SELECT
    l.job_id                              AS job_id,
    w.worker                              AS worker,
    w.worker_ms                           AS worker_ms,
    ifNull(r.reviewer_ms, 0)              AS reviewer_ms,
    w.worker_ms + ifNull(r.reviewer_ms, 0) AS effort_ms,
    l.rejections                          AS rejections,
    l.started_at                          AS started_at,
    l.first_submit_at                     AS first_submit_at,
    l.accepted_at                         AS accepted_at,
    dateDiff('second', l.started_at, l.accepted_at) AS leadtime_s
FROM (
    -- job 생애주기. 워크플로: new -> in progress -> completed -> (rejected -> completed)* -> stage=acceptance
    SELECT job_id,
           min(if(obj_name = 'state' AND obj_val = 'in progress', timestamp, NULL)) AS started_at,
           min(if(obj_name = 'state' AND obj_val = 'completed',   timestamp, NULL)) AS first_submit_at,
           min(if(obj_name = 'stage' AND obj_val = 'acceptance',  timestamp, NULL)) AS accepted_at,
           countIf(obj_name = 'state' AND obj_val = 'rejected')                     AS rejections
    FROM cvat.events
    WHERE project_id = {proj:UInt64} AND scope = 'update:job' AND job_id IS NOT NULL
    GROUP BY job_id
) l
LEFT JOIN (
    SELECT job_id, argMax(user_name, ms) AS worker, sum(ms) AS worker_ms
    FROM wt WHERE user_id NOT IN (SELECT user_id FROM reviewers) GROUP BY job_id
) w ON w.job_id = l.job_id
LEFT JOIN (
    SELECT job_id, sum(ms) AS reviewer_ms
    FROM wt WHERE user_id IN (SELECT user_id FROM reviewers) GROUP BY job_id
) r ON r.job_id = l.job_id
WHERE l.accepted_at IS NOT NULL;   -- 미승인 job 제외


-- ============================================================
-- 1. 목표 테이블 1 - task 단위 요약
-- ============================================================
-- project별로 1회씩 실행해 task 1/2/3 행을 채운다.
-- "task 1 대비 단축율"은 세 결과를 받아 (T1 - Tx) / T1 로 계산.

SELECT
    count()                          AS jobs,
    uniqExact(worker)                AS workers,
    round(dateDiff('second', min(started_at), max(accepted_at)) / 86400, 1) AS project_days,
    round(sum(effort_ms) / 3600000, 1)  AS project_effort_h,
    round(avg(worker_ms)   / 60000, 1)  AS work_per_job_min,
    round(avg(reviewer_ms) / 60000, 1)  AS review_per_job_min,   -- 단일 검수 완료 시간
    round(avg(rejections), 2)           AS rejects_per_job
FROM cvat.job_metrics(proj = {proj:UInt64});


-- ============================================================
-- 2. 목표 테이블 2 - 작업자별 최초/전체 job
-- ============================================================
-- first_*  : 최초로 승인된 job 하나 (검수 포함)
-- all_*    : 담당한 모든 job
-- active_pct: effort / leadtime. 벽시계 중 실제로 손을 움직인 비율.

SELECT
    worker,
    count()                                                    AS jobs,
    argMin(round(effort_ms / 60000, 1), accepted_at)           AS first_effort_min,
    argMin(round(leadtime_s / 3600, 1), accepted_at)           AS first_leadtime_h,
    round(sum(effort_ms) / 3600000, 1)                         AS all_effort_h,
    round(dateDiff('second', min(started_at), max(accepted_at)) / 3600, 1) AS all_leadtime_h,
    round(sum(effort_ms) / 3600000
          / (dateDiff('second', min(started_at), max(accepted_at)) / 3600) * 100, 1) AS active_pct
FROM cvat.job_metrics(proj = {proj:UInt64})
GROUP BY worker
ORDER BY all_effort_h DESC;


-- ============================================================
-- 3. job별 원본 - 이상치 확인용
-- ============================================================

SELECT job_id, worker,
       round(worker_ms   / 60000, 1) AS work_min,
       round(reviewer_ms / 60000, 1) AS review_min,
       rejections, started_at, accepted_at,
       round(leadtime_s / 3600, 1)   AS leadtime_h
FROM cvat.job_metrics(proj = {proj:UInt64})
ORDER BY accepted_at;


-- ============================================================
-- 3b. job 하나 드릴다운 - 라운드별 가공/검수/재가공/재검수
-- ============================================================
-- job_id 하나만 넣으면 라운드별로 쪼개진다.
-- 구간은 update:job 전이로 자르고, 그 구간에 떨어지는 send:working_time 을
-- 작업자/검수자로 나눠 합산한다. 검수자는 반려 또는 승인을 수행한 사람.
--
-- 라운드 경계:
--   -> in progress   가공 구간 시작       -> completed   가공 끝 / 검수 시작
--   -> rejected      검수 끝 / 재가공 시작  stage -> acceptance   종료
--
-- worker_min / reviewer_min 이 자기 구간이 아닌 쪽에도 소량 찍힐 수 있다.
-- 90초 배치가 구간 경계를 걸치거나, 실제로 상대가 job 을 열어본 경우다.

DROP VIEW IF EXISTS cvat.job_rounds;
CREATE VIEW cvat.job_rounds AS
WITH
    reviewers AS (
        SELECT DISTINCT user_name FROM cvat.events
        WHERE job_id = {job:UInt64} AND scope = 'update:job'
          AND ((obj_name = 'stage' AND obj_val = 'acceptance')
            OR (obj_name = 'state' AND obj_val = 'rejected'))
    ),
    wt AS (
        SELECT timestamp AS ts, duration AS ms, user_name
        FROM cvat.events
        WHERE job_id = {job:UInt64} AND scope = 'send:working_time'
    ),
    marks AS (
        -- 착수 이전 작업까지 포함하도록 첫 활동 시각을 여는 마크로 둔다
        SELECT least((SELECT min(ts) FROM wt), (SELECT min(timestamp) FROM cvat.events
                     WHERE job_id = {job:UInt64} AND scope = 'update:job')) AS ts, 'work' AS kind
        UNION ALL
        SELECT ts, kind FROM (
            SELECT timestamp AS ts,
                   multiIf(obj_name = 'state' AND obj_val = 'in progress', 'work',
                           obj_name = 'state' AND obj_val = 'completed',   'review',
                           obj_name = 'state' AND obj_val = 'rejected',    'rework',
                           obj_name = 'stage' AND obj_val = 'acceptance',  'done',
                           '') AS kind
            FROM cvat.events
            WHERE job_id = {job:UInt64} AND scope = 'update:job'
        ) WHERE kind != ''
    ),
    dedup AS (
        -- 같은 시각에 여는 마크가 겹치면 하나만 남긴다
        SELECT ts, argMin(kind, kind) AS kind FROM marks GROUP BY ts
    ),
    phases AS (
        SELECT
            row_number() OVER (ORDER BY ts) AS seq, kind, ts AS p_start,
            leadInFrame(ts) OVER (ORDER BY ts ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING) AS p_end_raw,
            sum(kind = 'review') OVER (ORDER BY ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_rev
        FROM dedup
    ),
    bounded AS (
        SELECT seq, kind, p_start,
               if(p_end_raw <= p_start, NULL, p_end_raw) AS p_end,
               cum_rev + (kind IN ('work', 'rework')) AS round
        FROM phases WHERE kind != 'done'
    ),
    agg AS (
        SELECT b.seq AS seq,
               sumIf(w.ms, w.user_name NOT IN (SELECT user_name FROM reviewers)) AS worker_ms,
               sumIf(w.ms, w.user_name     IN (SELECT user_name FROM reviewers)) AS reviewer_ms
        FROM bounded b CROSS JOIN wt w
        WHERE w.ts >= b.p_start AND (b.p_end IS NULL OR w.ts < b.p_end)
        GROUP BY b.seq
    )
SELECT
    round,
    if(is_work, if(round = 1, '가공', '재가공'), if(round = 1, '검수', '재검수')) AS phase,
    round(sum(worker_ms)   / 60000, 1) AS worker_min,
    round(sum(reviewer_ms) / 60000, 1) AS reviewer_min,
    round(dateDiff('second', min(p_start), max(p_end)) / 60, 1) AS elapsed_min,
    min(p_start) AS started,
    max(p_end)   AS ended
FROM (
    SELECT b.round AS round, b.kind IN ('work', 'rework') AS is_work,
           b.p_start AS p_start, b.p_end AS p_end,
           ifNull(a.worker_ms, 0) AS worker_ms, ifNull(a.reviewer_ms, 0) AS reviewer_ms
    FROM bounded b LEFT JOIN agg a ON a.seq = b.seq
)
GROUP BY round, is_work
ORDER BY round, is_work DESC;


-- 라운드별 상세
SELECT * FROM cvat.job_rounds(job = {job:UInt64});


-- 한 줄 요약
SELECT
    max(round)                                                    AS rounds,
    max(round) - 1                                                AS sent_back,        -- 반려/되돌림 횟수
    round(sumIf(worker_min,   phase = '가공'),   1)               AS first_work_min,   -- 최초 가공
    round(sumIf(reviewer_min, phase = '검수'),   1)               AS first_review_min, -- 최초 검수
    round(sumIf(worker_min,   phase = '재가공'), 1)               AS rework_min,       -- 재가공 합계
    round(sumIf(reviewer_min, phase = '재검수'), 1)               AS rereview_min,     -- 재검수 합계
    round(sum(worker_min),    1)                                  AS total_work_min,
    round(sum(reviewer_min),  1)                                  AS total_review_min,
    round(dateDiff('second', min(started), max(ended)) / 3600, 1) AS total_elapsed_h
FROM cvat.job_rounds(job = {job:UInt64});


-- ============================================================
-- 4. job 진입 시점의 state/stage
-- ============================================================
-- load:job 이벤트에는 state/stage가 없으므로 전이 이력에서 as-of 조회로 복원한다.
-- 초기값은 create:job 시점의 state=new, stage=annotation.
-- 소급 적용되므로 과거 데이터에도 그대로 쓸 수 있다.

WITH
stage_tr AS (
    SELECT job_id, timestamp AS ts, obj_val AS v FROM cvat.events
    WHERE scope = 'update:job' AND obj_name = 'stage' AND job_id IS NOT NULL
    UNION ALL
    SELECT job_id, timestamp, 'annotation' FROM cvat.events
    WHERE scope = 'create:job' AND job_id IS NOT NULL
),
state_tr AS (
    SELECT job_id, timestamp AS ts, obj_val AS v FROM cvat.events
    WHERE scope = 'update:job' AND obj_name = 'state' AND job_id IS NOT NULL
    UNION ALL
    SELECT job_id, timestamp, 'new' FROM cvat.events
    WHERE scope = 'create:job' AND job_id IS NOT NULL
),
entries AS (
    SELECT job_id, timestamp AS ts, user_name FROM cvat.events
    WHERE scope = 'load:job' AND job_id IS NOT NULL
)
SELECT e.ts AS entered_at, e.job_id, e.user_name,
       st.v AS stage_at_entry, sa.v AS state_at_entry
FROM entries e
ASOF LEFT JOIN stage_tr st ON e.job_id = st.job_id AND e.ts >= st.ts
ASOF LEFT JOIN state_tr sa ON e.job_id = sa.job_id AND e.ts >= sa.ts
ORDER BY entered_at;


-- ============================================================
-- 5. 로그인 세션 대조 - 컴플라이언스
-- ============================================================
-- login:user / logout:user 이벤트가 배포된 뒤부터 유효하다.
-- login 이 나올 때마다 세션 번호를 올리고, 뒤따르는 logout 을 그 세션에 귀속시킨다.
-- 토큰 인증이라 로그아웃 버튼을 눌러야만 logout 이 남는다.
-- 짝이 없는 login 은 logout_at 이 NULL -> 그 자체가 미준수 신호다.

SELECT
    user_name,
    session_no,
    min(timestamp)                                        AS login_at,
    max(if(scope = 'logout:user', timestamp, NULL))       AS logout_at,
    round(dateDiff('second', login_at, logout_at) / 3600, 2) AS session_h
FROM (
    SELECT user_name, timestamp, scope,
           countIf(scope = 'login:user') OVER (
               PARTITION BY user_name ORDER BY timestamp
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS session_no
    FROM cvat.events
    WHERE scope IN ('login:user', 'logout:user')
)
GROUP BY user_name, session_no
ORDER BY user_name, session_no;


-- 5b. 세션 대비 실작업 비율 - 자리비움 정량화
-- session_h 는 있는데 work_h 가 현저히 낮으면 로그인만 해두고 비운 시간이다.

SELECT
    s.user_name,
    toDate(s.login_at)                    AS day,
    round(sum(s.session_h), 1)            AS session_h,
    round(any(w.work_h), 1)               AS work_h,
    round(any(w.work_h) / sum(s.session_h) * 100, 1) AS active_pct
FROM (
    SELECT user_name, session_no,
           min(timestamp) AS login_at,
           dateDiff('second', min(timestamp),
                    max(if(scope = 'logout:user', timestamp, NULL))) / 3600.0 AS session_h
    FROM (
        SELECT user_name, timestamp, scope,
               countIf(scope = 'login:user') OVER (
                   PARTITION BY user_name ORDER BY timestamp
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS session_no
        FROM cvat.events WHERE scope IN ('login:user', 'logout:user')
    ) GROUP BY user_name, session_no
) s
LEFT JOIN (
    SELECT user_name, toDate(timestamp) AS day, sum(duration) / 3600000.0 AS work_h
    FROM cvat.events WHERE scope = 'send:working_time'
    GROUP BY user_name, day
) w ON w.user_name = s.user_name AND w.day = toDate(s.login_at)
GROUP BY s.user_name, day
ORDER BY day, s.user_name;


-- ============================================================
-- 6. 파이프라인 헬스체크 - 실험 시작 전 필수
-- ============================================================
-- send:working_time 의 last_seen 이 최근이 아니면 vector -> ClickHouse 구간이 죽은 것이다.

SELECT scope, count() AS c, uniqExact(user_id) AS users,
       min(timestamp) AS first_seen, max(timestamp) AS last_seen
FROM cvat.events
WHERE scope IN ('send:working_time', 'load:job', 'save:job', 'update:job',
                'create:issue', 'login:user', 'logout:user')
  AND timestamp > now() - INTERVAL 30 DAY
GROUP BY scope
ORDER BY last_seen DESC;
