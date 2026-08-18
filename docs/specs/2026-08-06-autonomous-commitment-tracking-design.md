# 자율 약속 추적 (Commitment Tracking) 설계

## 배경

`2026-08-05-group-workspace-auth-design.md`에서 4개 축(그룹 구조 / 채팅 중심 UI /
에이전틱 자동화 / 대행업체 특화 업무 모델) 중 그룹 구조만 다루고 나머지는 후속 스펙으로
미뤘다. 이번 스펙은 그중 **에이전틱 자동화 + 대행업체 특화 업무 모델**을 함께 다룬다.
두 축은 분리되지 않는다 — 무엇을 향해 자율적인가가 곧 업무 모델이기 때문이다.

### 출발점: 지금 OnQue는 "생성형 AI"다

삼성SDS AI Agent 페이지가 세우는 구분을 그대로 빌리면:

> "생성형 AI가 '어떻게' 해결할지 답한다면, AI Agent는 무엇을 해결해야 할지부터 '스스로' 파악"

현재 OnQue는 전자다. 사용자가 파일을 **업로드해야** 요약하고, 채팅에서 **명령어를 쳐야**
(`main.py:854` `_handle_command`) 할 일을 뽑는다. 시켜야 움직인다.

### 차별점: 무엇을 향해 자율적인가

삼성SDS의 레퍼런스 사례 세 건(보험 약관 심사, SOP 규제정보 검색, 다국어 회의록)은 모두
**내부 규정 준수**를 자동화한다. 사내 IT팀과 기간계 시스템(ERP·그룹웨어)이 전제다.

OnQue의 대상은 5~30명 대행업체 팀이다. 그런 기간계가 없고, 고통도 다른 데 있다 —
**클라이언트에게 한 약속이 새는 것**. 통화로 "다음 주까지 시안 드릴게요" 해놓고 아무도
기록하지 않아 놓치면 돈이 빠진다. 시장이 겹치지 않으며, 그것이 정당한 차별점이다.

단, 현재는 그 차별점이 랜딩 카피(`app/page.tsx:56` "대행업체 팀을 위해 만들었습니다")에만
있고 제품에는 없다. 기능(문서요약·통화요약·채팅비서)은 업종 무관 범용이다.
이 스펙이 그 간극을 메운다.

## 핵심 개념: 약속은 할 일이 아니다

| | Todo (기존) | Commitment (신규) |
|---|---|---|
| 정체 | 우리가 하기로 정한 내부 작업 | 클라이언트에게 말한 것 |
| 상대 | 없음 | 있음 (`client_id`) |
| 근거 | 없음 | 원문 인용 + 출처 |
| 놓치면 | 일이 밀린다 | 돈이 샌다 |

기존 `Todo`는 그대로 둔다. 약속은 별도 개념으로 추가한다.

## 데이터 모델

### 신규 테이블 2개

```
Client
- id
- group_id (FK groups.id, not null)
- name (not null)
- created_at
- UniqueConstraint(group_id, name)

Commitment
- id
- group_id (FK groups.id, not null)     # 접근 제어 기준
- client_id (FK clients.id, nullable)   # 상대를 특정 못하면 null
- content (not null)
- due_date (nullable)
- status: "proposed" | "confirmed" | "fulfilled" | "dismissed"
- source_type: "call" | "document" | "chat"
- source_id (nullable)                  # documents.id 또는 chat_messages.id
- evidence (not null)                   # 원문 인용 — 사람이 판단하는 근거
- created_at, updated_at
- confirmed_at (nullable)
```

`status`와 `source_type`은 `CheckConstraint`로 강제한다. 기존 `Document`가 쓰는 패턴
(`models.py:138-145`)과 동일하게 맞춘다.

접근 제어는 `group_id` 기준이며 기존 `_require_group_member`(`main.py:83`)를 재사용한다.
`client_id`를 접근 기준으로 삼지 않는다 — 권한 판정 경로를 두 개로 늘리지 않는다.

### 기존 테이블 변경

- `ChatRoom.last_scanned_message_id` (nullable int) — 방별 마지막 스캔 지점
- `Group.last_swept_at` (nullable datetime) — 그룹별 마지막 스윕 시각

둘 다 null이 "아직 없음"을 뜻하므로 **백필이 필요 없다.** TS-018에 기록된 "접근 규칙을
좁히는 스키마 변경의 백필 누락" 유형을 구조적으로 피한다. 두 컬럼 모두 접근 규칙과
무관하고, 값이 없어도 동작이 정의된다.

## 약속 추출

### 통화·문서 — 추가 API 호출 없음

`_summarize_and_store`(`main.py:115`)가 이미 업로드마다 Gemini를 호출한다. 그 응답
스키마에 `commitments[]` 필드를 추가한다:

```jsonc
"commitments": [
  {
    "content": "시안 3종 전달",
    "client_name": "A사",
    "due_date": "2026-08-13",
    "evidence": "다음 주 수요일까지 시안 세 개 정리해서 보내드릴게요"
  }
]
```

`due_date`는 `YYYY-MM-DD`. 호출 횟수가 늘지 않으므로 추가 비용은 출력 토큰 증가분뿐이다.

### 채팅 — 방 단위 배치

매 메시지마다 모델을 호출하면 비용이 감당되지 않는다. 방 단위로 훑는다.

조건: `last_scanned_message_id` 이후 새 메시지가 **15개 이상** 쌓였을 때.

한산한 방은 영영 스캔되지 않을 수 있다. 이는 의도된 트레이드오프다 — 대화가 15개도
쌓이지 않은 방에서 놓칠 약속은 적고, 사용자는 여전히 명령어로 직접 호출할 수 있다.
운영하며 임계값을 조정한다.

### client_name → client_id 해석

모델이 뱉은 `client_name`을 같은 그룹의 `Client.name`과 대조한다. 정확히 일치하면 연결,
없으면 `client_id = null`로 둔다. **모델이 언급했다는 이유로 Client를 자동 생성하지
않는다** — 오탈자와 환각이 클라이언트 목록을 오염시킨다. 클라이언트 생성은 사람이 한다.

## 자율 점검 — 요청 편승

Render 무료 티어에는 상주 워커가 없다. 유휴 시 인스턴스가 내려가므로 백그라운드
스케줄러를 전제한 설계는 동작하지 않는다.

대신 `GET /commitments` 처리 중에 스윕을 태운다:

1. `Group.last_swept_at` 확인. **쿨다운 10분** 이내면 즉시 반환
2. 배치 조건을 만족하는 채팅방 스캔 → `proposed` 약속 생성
3. `last_scanned_message_id`와 `last_swept_at` 갱신

아무도 접속하지 않으면 스윕도 돌지 않는다. 그러나 접속하지 않으면 알림을 볼 사람도
없으므로 실질적 손실이 아니다.

### 기한 경고는 저장하지 않는다

`status == "confirmed"` 이고 `due_date`가 임박(D-2 이내) 또는 초과인 약속은 조회 시점에
계산한다. 별도 알림 테이블을 두지 않는다.

경고는 상태가 아니라 파생값이다. 저장하면 약속 상태와 알림 상태가 어긋날 경로가
생기고, 그 동기화를 관리할 이유가 없다.

## 승인 게이트

추출된 약속은 **전부 `proposed`로 들어간다.** 자동 확정하지 않는다.

LLM 추출은 틀린다. "다음 주에 한번 볼게요"가 약속인지 인사치레인지 모델은 자신 있게
혼동한다. 오탐이 추적 목록에 바로 들어가면 사용자가 알림을 무시하기 시작하고, 그 시점에
기능이 죽는다.

대시보드의 "확인 필요" 카드에 원문 인용(`evidence`)과 함께 모아 보여주고, 체크박스
다중선택으로 [확정] / [무시]를 일괄 처리한다. 근거가 함께 보이므로 건당 판단은 1초면
끝난다.

신뢰도 기반 자동 분기는 채택하지 않는다. LLM의 자기보고 신뢰도는 실제 정확도와 잘
맞지 않아 임계값 튜닝에 시간이 소모된다.

### 상태 전이

```
proposed --확정--> confirmed --완료--> fulfilled
    |                  |
   무시               무시
    v                  v
dismissed          dismissed
```

`fulfilled`와 `dismissed`는 종료 상태다. 종료 상태에서 다른 상태로 되돌리는 전이는
허용하지 않는다 — 잘못 눌렀다면 새 약속을 만든다.

## API

`api-contract.md`의 envelope 형식을 따른다.

```
GET   /commitments?status=&client_id=&limit=20   # 스윕 편승 지점
PATCH /commitments/{id}          { status }
POST  /commitments/bulk-status   { ids[], status }
GET   /clients
POST  /clients                   { name }
```

목록은 기본 `limit=20`, 최대 100. 타임스탬프 응답은 ISO 8601 UTC, `due_date`는
`YYYY-MM-DD`. 에러 코드:

| HTTP | 코드 |
|---|---|
| 403 | `COMMITMENT_ACCESS_FORBIDDEN` |
| 404 | `COMMITMENT_NOT_FOUND` |
| 409 | `CLIENT_NAME_DUPLICATE` |
| 400 | `COMMITMENT_STATUS_INVALID` |

## 화면

- **대시보드 "확인 필요" 카드** — `proposed` 약속 목록. 각 항목에 내용·클라이언트·기한·
  원문 인용·출처 링크. 체크박스 다중선택 + [확정]/[무시] 일괄 버튼
- **기한 배너** — 임박(D-2 이내)하거나 초과한 `confirmed` 약속
- **클라이언트별 약속 뷰** — 클라이언트 선택 시 해당 약속과 상태

아이콘에 이모지를 쓰지 않는다.

## 실패 처리

**약속 추출 실패가 요약을 실패시켜서는 안 된다.** 기존 `_parse_summary_json`
(`main.py:216`)의 None 폴백 패턴을 따른다 — 모델이 스키마를 어기면 `WARN`을 남기고
`commitments`만 빈 배열로 처리한다. 요약은 정상 저장된다.

스윕 중 예외가 나면 `WARN`을 남기고 조회 응답은 정상 반환한다. 스윕은 부가 작업이므로
본 요청을 실패시키지 않는다. 폴백은 조용히 넘어가지 않고 반드시 로그를 남긴다.

## 테스트

- 약속 추출 파싱 — 모델 응답 mock. 정상 / 스키마 위반 / 빈 배열
- 추출 실패 시 요약이 정상 저장되는지
- `client_name` 해석 — 일치 / 불일치(null) / **자동 생성되지 않음**
- 스윕 쿨다운 — 10분 이내 재호출 시 스캔하지 않음
- 배치 임계값 — 15개 미만이면 스캔하지 않음
- 상태 전이 — 종료 상태(`fulfilled`/`dismissed`)에서의 전이 거부
- **그룹 격리** — 다른 그룹의 약속이 조회·수정되지 않음
- 일괄 상태 변경 — 일부 id가 남의 그룹이면 전체 거부

## 범위 밖

후속 스펙으로 미룬다.

- 자동화 규칙 (조건→행동 등록형) — 이 스펙의 실행 레이어를 재사용
- 통합 질의 (문서·통화·채팅 가로지르는 질의응답)
- 회의 코파일럿 (실시간 자막·번역) — 기존 요약과 중복이 커 보류
- 클라이언트를 `Todo`·`Document`·`Schedule`까지 확장
- 외부 cron 연동 및 메일 알림
