# 우측 패널 AI 비서 설계

**날짜:** 2026-08-09
**대상:** `onque-frontend/components/SmartDashboardPanel.tsx`, 신규 `routers/assistant.py` · `assistant_service.py`

## 배경

우측 패널은 `AuthGuard`(루트 레이아웃)를 통해 **로그인된 모든 화면에 상시 떠 있다.** 이름은 "Smart Dashboard"인데 하는 일은 할 일·일정 나열이다. 대시보드 페이지에 같은 목록이 이미 있어 중복이기도 하다.

물어보면 답하는 비서를 그 자리에 놓는다. 나열로는 못 하는 일 — **찾아보는 게 아니라 물어보는 것** — 을 맡긴다.

## 기존 자산 — 다시 만들지 않는다

**이 앱에는 이미 챗봇이 있다.** 새 비서는 그것과 역할이 갈려야 한다.

| 이미 있는 것 | 위치 |
|---|---|
| `@비서` 페르소나, 대화 답변 | `gemini_service.py:521` `_BOT_PERSONA_PROMPT`, `:528` `generate_bot_reply` |
| 말에서 할 일·일정 추출/완료/삭제 | `:442` `extract_chat_actions` — `add_todos`, `complete_todo_hints`, `delete_todo_hints`, `add_schedules`, `delete_schedule_hints` |
| `/요약` 명령 | `:466` `summarize_conversation` |
| `/문서` 명령 → Document 저장 | `:489` `draft_document_from_conversation` |
| 대화에서 약속 추출 (자동 스윕) | `:154` `extract_chat_commitments` |

**역할 구분:**

| | 기존 `@비서` (`/chat`) | 새 비서 (우측 패널) |
|---|---|---|
| 자리 | 팀 채팅방 | 1:1, 나만 본다 |
| 아는 것 | 그 방의 대화 맥락 | **내 업무 데이터**(약속·할 일·일정·클라이언트) |
| 약속 조작 | 못 한다 | 한다 |
| 대상 지목 | 문자열 힌트 퍼지 매칭 | **id 직접 지목** |

기존 챗봇은 `delete_todo_hints` 같은 **문자열 힌트**로 대상을 짐작해 지운다. 새 비서는 컨텍스트에 `id`를 실어주므로 모델이 **정확한 id를 지목**한다. 같은 기능인데 오폭 확률이 다르다.

`extract_chat_actions`를 재사용하지 않고 새 함수를 만드는 이유가 이것이다 — 반환 구조(힌트 문자열)가 다르고, 약속 전이가 없다.

## 핵심 결정: 비서 엔드포인트는 DB를 쓰지 않는다

**읽고, 답하고, 제안만 한다.** 실제 변경은 전부 **기존 엔드포인트**를 통해 프론트가 실행한다.

```
POST /api/v1/assistant/messages   ← 읽기 전용. INSERT/UPDATE/DELETE 없음
   ↓ 제안(actions[])
프론트가 승인 판정
   ↓
POST /todos · DELETE /todos/{id} · PATCH /todos/{id}
POST /schedules · DELETE /schedules/{id}
POST /api/v1/commitments/bulk-status
```

이유: 권한 검사와 상태 전이 규칙이 이미 그 엔드포인트들에 있다. 비서 전용 실행 경로를 새로 만들면 **같은 규칙을 두 벌로 유지**해야 하고, 한쪽만 고치는 순간 구멍이 된다. 새 쓰기 표면을 만들지 않으면 보안 검토 범위도 안 늘어난다.

## API

### 요청

```
POST /api/v1/assistant/messages
Authorization: Bearer <token>

{
  "group_id": 1,
  "message": "A사한테 뭐 약속했더라?",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

- `message`: 1~2000자. 빈 문자열은 422
- `history`: 클라이언트가 들고 다닌다. **서버는 최근 20개 메시지(사용자·비서 합쳐, 약 10왕복)만 쓰고 나머지는 조용히 버린다.** 초과를 422로 거절하지 않는다 — 사용자 잘못이 아니다. 단위는 "왕복"이 아니라 **배열 항목 개수**다
- `group_id`: `require_group_member`로 검사. 미소속이면 403

대화 기록을 서버에 두지 않으므로 **새 테이블도, 마이그레이션도, 보관 정책도 없다.**

### 응답

```jsonc
{
  "success": true,
  "data": {
    "reply": "A사 약속은 4건입니다. 시안 전달은 2일 지났고, 나머지 3건은 기한이 없습니다.",
    "actions": [ /* 아래 */ ]
  },
  "error": null
}
```

### Action

```jsonc
{
  "id": "a1b2c3d4",              // 프론트가 승인/거절을 구분할 임시 id (uuid4). 저장되지 않는다
  "risk": "safe" | "confirm",
  "kind": "todo_add" | "todo_delete" | "todo_done"
        | "schedule_add" | "schedule_delete" | "commitment_status",
  "label": "이걸 이행 완료로 바꿀까요?",   // 사람이 읽을 문장
  "warning": "이행 완료는 되돌릴 수 없습니다",  // 없으면 null
  "payload": { /* kind별 */ }
}
```

`kind`별 `payload`:

| kind | payload | 프론트가 부르는 것 |
|---|---|---|
| `todo_add` | `{content, due_date\|null}` | `createTodo` |
| `todo_done` | `{todo_id, content}` | `updateTodo(id, {is_done: true})` |
| `todo_delete` | `{todo_id, content}` | `deleteTodo` |
| `schedule_add` | `{title, scheduled_date}` | `createSchedule` |
| `schedule_delete` | `{schedule_id, title}` | `deleteSchedule` |
| `commitment_status` | `{commitment_id, content, client_name, from_status, to_status}` | `bulkUpdateCommitments([id], to_status)` |

**응답에 URL이나 HTTP 메서드를 담지 않는다.** 프론트가 `kind`로 고정 분기해 자기 API 래퍼를 부른다. 서버가 경로를 지시하면 모델 출력이 요청 경로에 영향을 줄 여지가 생긴다 — 그 여지를 아예 만들지 않는다.

**`createSchedule` 래퍼는 없어서 새로 만들어야 한다.** 백엔드 `POST /schedules`(`main.py:484`)는 있는데 프론트가 일정을 직접 만든 적이 없어(지금은 채팅 추출로만 생긴다) `lib/api.ts`에 래퍼가 없다. 나머지 5개는 있다 — `createTodo:298`, `updateTodo:309`, `deleteTodo:313`, `deleteSchedule:321`, `bulkUpdateCommitments:517`.

`updateTodo`는 `{is_done?: boolean}`만 받는데 `todo_done`에는 그것으로 충분하다. 시그니처를 넓히지 않는다.

## 위험 분류

| risk | 무엇 | 화면 동작 |
|---|---|---|
| `safe` | `todo_add`, `schedule_add`, `todo_done` | **즉시 실행** 후 결과 표시 + `[취소]` |
| `confirm` | `todo_delete`, `schedule_delete`, `commitment_status` | **제안 카드** → `[그렇게 해]` 눌러야 실행 |

약속 상태 전이를 **전부** `confirm`으로 두는 이유: `_ALLOWED_TRANSITIONS`(`commitment_service.py:26-29`)에 역방향이 없다.

```
proposed → confirmed → fulfilled
        ↘ dismissed
```

한 번 넘어가면 앱 안에서 되돌릴 수 없다. `todo_done`은 `is_done` 토글이라 되돌릴 수 있어 `safe`다.

`safe`의 `[취소]`는 방금 만든 것을 지우거나(`todo_add`/`schedule_add`) 다시 토글한다(`todo_done`).

## 서버가 액션을 검증한다

모델이 없는 `id`를 지어낼 수 있다. **액션을 내려보내기 전에 서버가 걸러낸다.**

1. `todo_id` · `schedule_id` · `commitment_id`가 **실재하고 그 `group_id`에 속하는지** 확인한다. 아니면 그 액션을 버린다
2. `commitment_status`는 `commitment_service.can_transition(from, to)`를 통과해야 한다. 아니면 버린다 — 승인 눌렀는데 409가 나면 사용자 잘못이 아닌 실패다
3. 버린 액션은 **조용히 사라지지 않는다.** `reply` 아래에 "일부 제안을 적용할 수 없어 제외했습니다"를 덧붙인다

## 컨텍스트 수집 (`assistant_service.build_context`)

매 메시지마다 내 업무 상태를 프롬프트에 싣는다. **상한을 두는 이유는 매번 전량을 싣기 때문**이다 — 토큰이 곧 비용이고 Gemini 무료 티어에 분당 한도가 있다.

| 자료 | 상한 | 싣는 필드 |
|---|---|---|
| 약속 `proposed` | 100 | `id`, `content`, `client_name`, `due_date`, `status`, `source_type` |
| 약속 `confirmed` | 100 | 위 + `is_overdue`, `is_due_soon` |
| 할 일 (미완료) | 50 | `id`, `content`, `due_date` |
| 일정 (오늘 이후) | 30 | `id`, `title`, `scheduled_date` |
| 클라이언트 | 전체 | `name` |
| 오늘 날짜 (KST) | — | 기존 `korean_date_context()` 재사용 |

정렬은 **약속·할 일은 `due_date` 오름차순(NULL은 뒤), 일정은 `scheduled_date` 오름차순**이다. 상한에 걸려 잘릴 때 급한 것부터 남아야 한다 — `created_at desc`로 자르면 마감 임박 건이 통째로 빠질 수 있다.

NULL을 뒤로 보내는 건 `NULLS LAST`가 아니라 `func.coalesce(due_date, date(9999,12,31))`로 한다. SQLite가 `NULLS LAST`를 지원하지 않아 테스트에서만 순서가 달라진다.

**일정은 `group_id`가 NULL인 것도 함께 읽는다.** 기존 `GET /schedules`(`main.py:504`)가 그렇게 동작해서 사용자 화면에 이미 섞여 보이고 있다. 비서가 화면과 다른 걸 보면 답이 어긋난다. 그룹 격리 테스트는 **다른 그룹의(NULL이 아닌) 일정**이 안 섞이는지를 단언한다.

모델은 기존과 같은 `gemini-2.5-flash`(`gemini_service.py:25`)를 쓴다. 새 모델을 도입하지 않는다.

`is_overdue`/`is_due_soon`은 `commitment_service.due_flags()`가 조회 시 계산하는 파생값이고 **`confirmed`일 때만 True가 될 수 있다**(`commitment_service.py:53-61`). `proposed`는 기한이 지나도 항상 False다. 프롬프트가 이 사실을 알아야 "확인 안 한 약속의 기한이 지났다"를 스스로 말할 수 있다 — 규칙에 명시한다.

**이 조회는 `GET /api/v1/commitments`를 부르지 않고 DB를 직접 읽는다.** 그 엔드포인트는 `maybe_sweep`을 겸해서(`routers/commitments.py:197`) 비서에 말 걸 때마다 Gemini 스윕이 딸려 돌 수 있다.

## 프롬프트 규칙

- **주어진 데이터에만 근거해 답한다. 없으면 "그 정보는 없습니다"라고 말한다. 지어내지 않는다**
- 약속을 언급할 땐 출처(통화·문서·채팅)와 기한을 함께 말한다
- 개수를 셀 땐 주어진 목록을 센다
- `proposed`는 아직 사람이 확인하지 않은 상태다. 기한이 지났어도 `is_overdue`가 False이므로, **날짜를 직접 비교해서** 지났으면 지났다고 말한다
- 액션을 제안할 땐 반드시 주어진 `id` 중에서 고른다
- 이모지를 쓰지 않는다

틀린 답의 안전판은 **화면에 같은 데이터가 떠 있다**는 것이다. 사용자가 바로 대조한다.

## 화면

```
┌─ Smart Dashboard ────────────┐
│ 오늘 마감 1 · 할 일 5      ∨ │  ← 접힌 요약
│ 확인 필요 3 · 기한 주의 2   ∨ │
├──────────────────────────────┤
│                              │
│  나: A사 약속 뭐 있지?        │
│                              │
│  비서: 4건입니다. 시안 전달은  │
│  2일 지났고, 나머지 3건은     │
│  기한이 없습니다.             │
│                              │
│  ┌────────────────────────┐  │
│  │ 이걸 이행 완료로 바꿀까요? │  │
│  │ "시안 화요일까지 드릴게요" │  │
│  │ A사 · 통화 · 확정됨       │  │
│  │ 이행 완료는 되돌릴 수 없음 │  │
│  │   [그렇게 해]  [아니]     │  │
│  └────────────────────────┘  │
│                              │
├──────────────────────────────┤
│ [ 무엇이든 물어보세요    ] [↑]│
└──────────────────────────────┘
```

- 접힌 줄의 숫자는 **전부 `WorkspaceContext`에 이미 있다** — 새 조회 0. `openTodos.length`, `schedules.length`, `proposedCount`, `dueSoon.length`
- 펼치면 **지금의 할 일·일정 목록이 그대로** 나온다(체크박스·삭제 포함). 기존 기능을 잃지 않는다
- 대화는 React state. `AuthGuard`가 루트 레이아웃에 있어 **화면을 옮겨다녀도 유지되고, 새로고침에서만 사라진다**
- 폭은 기존 그대로(`lg` 320px / `xl` 360px). `lg` 미만에서는 지금처럼 렌더되지 않는다
- **이모지를 쓰지 않는다**

## 에러 처리

| 상황 | 응답 | 화면 |
|---|---|---|
| Gemini 실패·타임아웃 | `502 ASSISTANT_UNAVAILABLE` | 대화에 실패 표시. **사용자가 친 문장을 입력창에 되돌려 놓는다** — 날리면 다시 타이핑해야 한다 |
| 그룹 미소속 | `403 GROUP_ACCESS_FORBIDDEN` (기존 코드) | 기존 에러 배너 |
| `message` 빈 값·2000자 초과 | `422 VALIDATION_FAILED` | 입력창 아래 문구 |
| 액션 실행 실패 (승인 후) | 기존 엔드포인트의 코드 그대로 | 카드에 실패 표시. 대화는 유지 |

Gemini 실패를 조용히 넘기지 않는다. "답이 없음"과 "모델이 죽음"은 사용자에게 전혀 다른 의미다.

## 테스트

백엔드는 pytest, Gemini는 목으로 막는다. 프론트는 테스트 인프라가 없어 `npx tsc --noEmit`과 `npx next build --webpack`으로 확인한다(워크트리에서 `npm run build`는 Turbopack 심링크 문제로 실패한다 — TS-026).

**제일 먼저 쓸 테스트는 그룹 격리다.** A그룹에서 물었는데 컨텍스트에 B그룹 약속이 섞이면 정보 유출이다.

| # | 단언 |
|---|---|
| 1 | **A그룹 컨텍스트에 B그룹의 약속·할 일·일정이 하나도 없다** |
| 2 | 비멤버가 그 그룹으로 물으면 403 |
| 3 | Gemini가 예외를 던지면 502 `ASSISTANT_UNAVAILABLE` 봉투 |
| 4 | history 20턴을 보내면 프롬프트에 10턴만 들어간다 (422 아님) |
| 5 | 컨텍스트가 상한(약속 100·할 일 50·일정 30)을 지킨다 |
| 6 | 모델이 없는 `todo_id`를 반환하면 그 액션이 제외된다 |
| 7 | 모델이 다른 그룹의 `commitment_id`를 반환하면 제외된다 |
| 8 | 불법 전이(`proposed → fulfilled`)를 반환하면 제외된다 |
| 9 | 삭제·약속 전이는 `risk="confirm"`으로 나온다 |
| 10 | **비서 엔드포인트 호출이 DB를 바꾸지 않는다** — 호출 전후 todos·schedules·commitments 행이 동일 |
| 11 | `message`가 빈 문자열이면 422 |

## 검증 기준

1. 약속·할 일·일정에 대해 물으면 **실제 내 데이터에 근거한** 답이 온다
2. 데이터에 없는 걸 물으면 지어내지 않고 없다고 답한다
3. "할 일 추가해줘"는 바로 실행되고 `[취소]`로 되돌아간다
4. "이거 지워줘"·"완료 처리해줘"는 **카드가 뜨고 승인 전엔 아무것도 안 바뀐다**
5. 약속 전이 카드에 "되돌릴 수 없습니다" 경고가 있다
6. 화면을 옮겨다녀도 대화가 유지되고, 새로고침하면 비워진다
7. 접힌 요약을 펼치면 기존 할 일·일정 목록이 그대로 동작한다(체크·삭제)
8. Gemini가 죽어도 화면이 깨지지 않고, 친 문장이 입력창에 남는다
9. 그룹을 바꾸면 비서가 그 그룹 데이터로 답한다

**1·4·9번이 회귀 위험이 가장 크다.**

## 범위 밖

| 항목 | 이유 |
|---|---|
| 위험 레이더(기한 지난 미확인 약속을 안 물어봐도 띄우기) | 비서가 자리잡은 뒤 별건. 프롬프트 규칙으로 "물어보면" 답하는 것까지만 |
| 대화 영구 저장 | 새 테이블·마이그레이션·보관 정책이 따라온다 |
| 스트리밍 응답 | 응답이 짧아 체감 이득이 적다 |
| 음성 입력 | — |
| 기존 `/chat`의 `@비서` 변경 | 건드리지 않는다 |
| 여러 그룹을 가로지르는 질문 | 컨텍스트는 현재 그룹 하나로 한정한다 |
