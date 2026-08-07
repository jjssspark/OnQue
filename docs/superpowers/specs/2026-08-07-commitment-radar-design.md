# 약속 레이더와 실시간 대시보드 설계

**날짜:** 2026-08-07
**대상:** `onque-frontend/components/SmartDashboardPanel.tsx`, `onque-frontend/components/WorkspaceContext.tsx`

## 배경

우측 패널이 "Smart Dashboard / 실시간 업무 현황"이라는 이름으로 할 일과 일정만 보여준다. 두 가지 문제가 있다.

**1. 실시간이 아니다.** `WorkspaceContext.tsx:82-84`가 마운트할 때와 그룹을 바꿀 때 한 번씩 조회하는 게 전부다. 폴링도 SSE도 없다. 다른 사람이 할 일을 추가해도 내 화면은 새로고침 전까지 모른다. **화면에 쓰인 "실시간"이 거짓이다.**

**2. 우측 패널에서는 약속이 보이지 않는다.** `Commitment`는 통화·문서·채팅에서 자동으로 추출한 클라이언트 약속이다. 모델 주석이 스스로 말한다 — "클라이언트에게 한 약속. 내부 작업인 Todo와 구분된다 — 상대(`client_id`)와 근거(`evidence`)를 갖고, 놓치면 신뢰와 돈이 걸린다." 우측 패널은 `AuthGuard`를 통해 **모든 화면에 떠 있는데** 거기엔 사용자가 손으로 타이핑한 할 일·일정만 뜬다. 채팅이나 문서 화면에 있는 동안에는 기한이 닥친 약속이 보이지 않는다.

먼저 ①을 고치고 ②를 고친다.

> **2026-08-07 정정.** 이 문서의 초판은 "이 앱의 핵심 자산이 **대시보드에 없다**"고 썼는데 **틀렸다.** `SmartDashboardPanel`만 보고 판단했으나, 약속 UI는 대시보드 *페이지*에 이미 있다 — 아래 "기존 자산" 참조. 문제는 "약속 UI가 없다"가 아니라 "**우측 패널에** 없다"였다. 그에 맞춰 범위를 좁혔다.

## 기존 자산

**약속 UI가 이미 있다. 다시 만들지 않는다.**

`onque-frontend/components/CommitmentPanel.tsx`(216줄)가 `app/dashboard/page.tsx:161`에 마운트돼 있고 다음을 한다.

| 하는 일 | 근거 |
|---|---|
| `확인 필요`(proposed) 목록 + 선택 후 **일괄 확정·기각** | `CommitmentPanel.tsx:94`, `:82` `bulkUpdateCommitments` |
| `기한 주의`(confirmed 중 `is_overdue`/`is_due_soon`) | `:119`, `:127` |
| `MAX_LIMIT = 100`으로 조회하고 `meta`로 배지를 채운다 | `:19-21` — 주석: "서버 기본 limit(20)에 걸리면 확인 필요 목록이 조용히 잘린다" |

**따라서 확정·기각 조작은 이 설계의 범위가 아니다.** 우측 패널은 **읽기 전용 요약**만 맡고, 조작은 계속 `CommitmentPanel`이 담당한다. 같은 기능을 두 곳에 구현하면 전이 규칙·에러 처리·낙관적 갱신이 두 벌로 갈라진다.

백엔드 API도 이미 충분하다. **새 엔드포인트가 필요 없다.**

| 있는 것 | 위치 |
|---|---|
| `GET /commitments?group_id=&status=&limit=` (봉투 + `meta`) | `routers/commitments.py:186` |
| 응답 항목에 `is_overdue`·`is_due_soon` 서버 계산 포함 | `_serialize_commitment`, `commitment_service.due_flags` |
| 상태 변경 + 전이 규칙 검증 | `POST /commitments/bulk-status`, `commitment_service.can_transition` |
| 프론트 API 함수 | `lib/api.ts`의 `getCommitments`, `getCommitmentsPage`, `bulkUpdateCommitments` |
| 상태 값 | `proposed` → `confirmed` → `fulfilled` / `dismissed` |
| 출처 | `call` / `document` / `chat` |

## 결정

**약속 레이더를 패널 맨 위에 두고, 30초 폴링으로 "실시간"을 참으로 만든다.**

SSE와 WebSocket은 쓰지 않는다. 팀 도구에 30초면 충분하고, Render 무료 티어에서 장기 연결 유지는 검증되지 않은 변수다. 폴링으로 부족한 것이 실제로 확인되면 그때 SSE를 본다.

## 패널 구성

```
[ 약속 레이더 ]   ← 표시할 항목이 0건이면 구역 자체가 렌더되지 않는다
[ 할 일 ]
[ 일정 ]
```

평소에는 지금과 동일한 화면이다. **AI가 무언가 건져 올렸을 때만 맨 위에 나타난다.** 그래야 레이더이고, 320px 폭을 상시 점유하지 않는다.

레이더가 표시하는 것 — **읽기 전용이다:**

- `proposed` **건수**와 상위 몇 건 — "확인 필요 N건". 누르면 `/dashboard`의 `CommitmentPanel`로 보낸다
- `confirmed` 중 `is_overdue` 또는 `is_due_soon`인 것 — "곧 마감"

각 항목: `content`, 클라이언트 이름, 마감 카운트다운. `evidence`(원문 근거)는 320px 폭에 안 들어가므로 넣지 않는다 — 필요하면 대시보드에서 본다.

**확정·기각 버튼을 두지 않는다.** `CommitmentPanel`이 이미 선택·일괄 처리·전이 규칙 오류 표시를 갖추고 있다. 좁은 패널에 축소판 조작을 또 만들면 두 벌이 갈라진다.

## 데이터 조회

`WorkspaceContext`의 `refresh()`가 이미 `Promise.all`로 두 개를 부른다. 여기에 두 개를 더 얹는다 — `status=proposed`와 `status=confirmed`. `status` 파라미터가 단일값이라 두 번 부르는 것이 백엔드를 건드리지 않는 길이다.

`lib/api.ts`의 `getCommitmentsPage(groupId, status, limit)`를 그대로 쓴다. `proposed`는 `meta.total`이 있어야 "확인 필요 N건"이 실제 전체 개수가 된다 — `CommitmentPanel.tsx:19-21`이 같은 이유로 그렇게 한다.

### 백엔드 변경은 하지 않는다

초판은 `GET /commitments`에 `sort=due_date`를 추가하자고 했다. `list_commitments`가 `created_at.desc()`로만 정렬해서(`routers/commitments.py:218`) `confirmed`가 기본 `limit=20`을 넘으면 마감 임박이 아니라 최신 20건이 온다는 이유였다.

**철회한다.** `CommitmentPanel`이 이미 `MAX_LIMIT = 100`으로 조회해 이 문제를 우회하고 있고, 우측 패널도 같은 방식을 쓰면 된다. 100건을 받아 클라이언트에서 마감순으로 정렬해 상위 몇 건만 그린다 — 팀당 미완료 약속이 100건을 넘는 상황은 지금 규모에서 오지 않는다. **백엔드를 안 건드리면 이 작업은 프론트 전용이 되고 배포 위험이 사라진다.**

100건을 넘기면 그때 서버 정렬을 넣는다. 그 시점이 오면 `meta.total`이 100을 넘는 것으로 드러난다.

## 폴링

`WorkspaceContext`에 30초 주기 `setInterval`. 지킬 것:

- **`document.visibilitychange`로 탭이 숨으면 멈추고, 돌아오면 즉시 한 번 갱신한다.** 안 하면 백그라운드 탭이 Render 무료 티어를 계속 두드린다
- **폴링 실패는 기존 목록을 지우지 않는다.** 화면이 깜빡이며 비었다 차면 신뢰를 잃는다. 조용히 다음 주기를 기다리되 마지막 갱신 시각은 올리지 않는다
- **`loading` 스피너는 최초 1회만.** 폴링 갱신마다 스피너를 띄우면 30초마다 화면이 흔들린다
- 언마운트 시 `clearInterval` — 누락하면 라우트 이동마다 타이머가 쌓인다

## 서버 호출 없이 움직이는 것

가장 값싼 "동적 효과"는 클라이언트가 시간만으로 계산하는 것이다. API 호출이 0회인데 화면이 살아 있다.

| 효과 | 구현 |
|---|---|
| 마감 카운트다운 | `due_date`로 "3일 남음 / 오늘 마감 / 2일 지남". 1분마다 재계산. `is_overdue` 빨강, `is_due_soon` 주황 |
| "12초 전 갱신" | 1초마다 증가, 폴링 성공 시 0으로 리셋. 데이터 신선도가 보인다 |
| 새 항목 하이라이트 | 폴링으로 새로 들어온 id의 배경을 잠깐 줬다 뺀다 |

`transform`과 `opacity`만 애니메이션한다. 레이아웃 속성(`width`, `height`, `top`)은 건드리지 않는다. **이모지를 쓰지 않는다.**

## 조작은 어디서 하나

우측 패널의 약속 구역을 누르면 `/dashboard`로 이동한다. 확정·기각은 거기 `CommitmentPanel`에서 한다.

`CommitmentPanel`이 상태를 바꾸면 우측 패널도 따라와야 한다. 폴링이 30초 안에 맞춰주므로 별도 연동을 만들지 않는다 — 두 컴포넌트를 이벤트로 엮으면 결합이 생기고, 폴링이 이미 그 일을 한다.

## 검증 기준

1. 확인 필요·기한 임박이 둘 다 0건이면 약속 구역이 **렌더되지 않는다** (빈 카드가 아니라 없음)
2. `proposed`가 있으면 패널 맨 위에 "확인 필요 N건"이 뜨고, N이 `meta.total`(20건 상한이 아니라 전체)이다
3. 그 구역을 누르면 `/dashboard`로 이동한다
4. 대시보드에서 약속을 확정하면 30초 안에 우측 패널 숫자가 줄어든다
5. 탭을 숨기면 네트워크 요청이 멈추고, 돌아오면 즉시 한 번 갱신된다
6. 폴링이 실패해도 화면의 기존 목록이 비지 않는다
7. "N초 전 갱신"이 1초마다 올라가고 갱신 성공 시 0으로 돌아간다
8. 그룹을 바꾸면 약속·할 일·일정이 모두 그 그룹 것으로 바뀐다

**1번과 6번이 회귀 위험이 가장 큰 지점이다.** 지금 화면을 바꾸지 않는 것과, 폴링이 조용히 화면을 비우지 않는 것.

**8번이 `sort` 파라미터를 추가하는 이유다.**

## 테스트

백엔드는 `sort=due_date` 정렬 하나가 대상이다 — 마감 오름차순이고 `NULL`이 뒤로 가는지, 기본값이 기존 동작을 유지하는지 단언한다.

프론트엔드는 이 프로젝트에 테스트 인프라가 없다. `npx tsc --noEmit`과 빌드로 확인한다. 워크트리에서는 `npm run build`가 Turbopack 심링크 문제로 실패하므로 `npx next build --webpack`을 쓴다(TS-026).

## 범위 밖

| 항목 | 이유 |
|---|---|
| SSE / WebSocket | 폴링으로 부족한 것이 확인된 뒤에 검토 |
| 할 일·일정·약속 통합 타임라인 | 별도 건. 레이더가 자리잡은 뒤 |
| "그동안 생긴 일" 활동 피드 | 별도 건 |
| 진행률 바 | 별도 건 |
| `evidence` 원문 하이라이트·원본 이동 | 레이더 안정화 후 |
