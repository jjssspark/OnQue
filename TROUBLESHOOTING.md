# OnQue 트러블슈팅 기록

> **이 프로젝트 전용 파일.** `~/Project/TROUBLESHOOTING.md`(전역 누적 파일)와 별도로,
> 사용자 요청에 따라 OnQue 폴더 안에 독립적으로 관리한다.
> 문제 → 원인 → 해결 → 추후 관리 순서로, 포트폴리오·면접 자료로 바로 쓸 수 있게 작성한다.

---

## 작성 규칙

1. 문제를 해결한 직후에 쓴다.
2. 재현되지 않은 추측은 원인에 쓰지 않는다. 확인한 것과 추정한 것을 구분한다.
3. 실패한 시도도 남긴다.
4. 새 항목은 인덱스 표 맨 위(최신순), 본문도 맨 위에 이어 붙인다.
5. 로그·에러 메시지는 원문 그대로 코드블록에 넣는다.
6. 비밀값(키·토큰·비밀번호·실제 도메인/IP)은 `<REDACTED>`로 치환한다.

---

## 인덱스

| ID | 날짜 | 영역 | 문제 | 심각도 | 상태 |
|---|---|---|---|---|---|
| TS-016 | 2026-08-05 | Infra/DB | 프로덕션 DB의 4개 테이블이 그룹 기능 이전 스키마에 머물러 할 일·일정·채팅·문서가 전부 실패 중이었으나, 프론트엔드가 오류를 삼켜 정상으로 보임 | High | 해결됨 |
| TS-015 | 2026-08-05 | BE/UX | 요약 리포트의 이모지가 프론트엔드를 아무리 고쳐도 사라지지 않음 — 출처가 백엔드 LLM 프롬프트였음 | Medium | 해결됨 |
| TS-014 | 2026-08-05 | Infra/Auth | 배포된 앱에서 로그인이 무한 대기 — Render 무료 티어 콜드스타트(54초) + 백엔드 구버전 배포 + `render.yaml`에 `JWT_SECRET` 누락이 겹침 | High | 해결됨 |
| TS-013 | 2026-08-05 | BE | pytest용 SQLite 인메모리 DB가 FastAPI 워커 스레드에서 `no such table` 에러 (StaticPool 누락) | Medium | 해결됨 |
| TS-012 | 2026-08-05 | Infra | 프로젝트 폴더 이동(`~/Desktop`→`~/Project`) 후 venv 셔뱅 경로가 깨져 `ModuleNotFoundError` | Medium | 해결됨 |
| TS-011 | 2026-08-04 | Infra | Vercel이 GitHub push에 자동 반응하지 않아 백엔드만 재배포되고 프론트는 구버전으로 남음 | Medium | 해결됨 |
| TS-010 | 2026-08-04 | 외부API | Gemini 무료 티어 일시 과부하(503)로 `@비서` 봇 답변이 폴백 메시지로 나감 | Low | 해결됨 (재시도로 해소) |
| TS-009 | 2026-08-04 | DB | SQLAlchemy가 `postgresql://` 스킴에서 기본으로 psycopg2를 찾는데 psycopg3만 설치되어 있어 `ModuleNotFoundError` | Medium | 해결됨 |
| TS-008 | 2026-08-04 | Infra | `.env`의 `DATABASE_URL` 키 뒤 공백 + 키 없는 값만 있는 빈 줄이 섞여 환경변수 인식 실패 | Medium | 해결됨 |
| TS-007 | 2026-08-04 | BE | `db.py`가 `.env`를 직접 로드하지 않아 import 순서에 따라 `DATABASE_URL`을 못 찾고 기동 실패 | Medium | 해결됨 |
| TS-006 | 2026-08-04 | FE | 이력 페이지가 SSR에서는 빈 상태, 클라이언트에서는 즉시 localStorage 값으로 렌더링돼 hydration mismatch 발생 | Medium | 해결됨 |
| TS-005 | 2026-08-04 | FE/Build | 서버 컴포넌트에서 함수를 클라이언트 컴포넌트 props로 전달해 Next.js 빌드가 `/calls`에서 실패 | High | 해결됨 |
| TS-004 | 2026-08-04 | Build/Infra | Next.js 16.0.3의 critical RCE(CVSS 10) 등 취약점으로 Vercel이 배포를 차단 | Critical | 해결됨 |
| TS-003 | 2026-08-04 | 외부API | Google이 신규 발급한 Auth key(`AQ.` 형식)가 구버전 `google-generativeai` SDK와 비호환 | High | 해결됨 |
| TS-002 | 2026-08-04 | Auth/Infra | `gemini_test.py`에 하드코딩된 실제 Gemini API 키가 첫 커밋으로 공개 저장소에 노출 (보안 사고) | Critical | 해결됨 (키 폐기·재발급, git 히스토리 정리는 사용자 판단으로 보류) |
| TS-001 | 2026-08-04 | Infra/Build | `requirements.txt`에 무관한 패키지 63개가 그대로 남아있어 Render pip 설치가 `ResolutionImpossible`로 실패 | High | 해결됨 |

**영역**: `FE` / `BE` / `DB` / `Infra` / `Build` / `Auth` / `외부API`
**심각도**: `Critical`(서비스 중단·데이터/보안 손실) / `High`(핵심 기능 불가) / `Medium`(우회 가능) / `Low`(불편)

---

## 기록

## TS-016 · 프로덕션 DB가 구스키마에 머물러 4개 기능이 죽어 있었으나 화면상 정상으로 보임

| | |
|---|---|
| **날짜** | 2026-08-05 |
| **영역** | Infra / DB / UX |
| **심각도** | High |
| **상태** | 해결됨 |
| **소요 시간** | 약 15분 (발견 후 조치) |

### 증상

`Document.summary_json` 컬럼을 추가하고 배포한 뒤, Neon에 컬럼이 실제로 생겼는지 확인하려고 스키마를 조회했다. 그 과정에서 **의도치 않게 훨씬 큰 문제가 드러났다.**

```
documents 컬럼: ['id', 'source_type', 'category', 'filename', 'summary', 'created_at']
```

`group_id`도 `is_template`도 없었다. 그룹 기능 도입 전 스키마 그대로였다. 전체 테이블을 조회하니 4개가 같은 상태였다.

```
chat_messages (행 0): ['id', 'sender', 'content', 'is_bot', 'created_at']
documents     (행 0): ['id', 'source_type', 'category', 'filename', 'summary', 'created_at']
schedules     (행 0): ['id', 'title', 'scheduled_date', 'created_at', 'updated_at']
todos         (행 0): ['id', 'content', 'due_date', 'is_done', 'created_at', 'updated_at']

announcements     (행 0): 정상
groups            (행 1): 정상
group_memberships (행 1): 정상
users             (행 1): 정상
```

즉 배포된 앱에서 **할 일·일정·채팅·문서 관련 요청이 이미 전부 실패하고 있었다.** 이 코드들은 모두 `WHERE group_id = ...`로 조회한다.

### 재현 조건

1. 그룹 기능 도입 이전에 생성된 Neon 인스턴스를 그대로 사용
2. 그룹 기능이 포함된 백엔드를 배포 (`Base.metadata.create_all(bind=engine)` 실행됨)
3. 로그인 → 대시보드 진입

### 원인

**표면**: 브라우저로 확인했을 때 로그인·그룹 생성·공지 등록이 모두 정상 동작해 배포가 성공한 것으로 판단했다.

**근본 (두 겹)**

첫째, **`Base.metadata.create_all()`은 없는 테이블만 만들고, 이미 존재하는 테이블에는 컬럼을 추가하지 않는다.** 이름이 "create_all"이라 전체를 최신 상태로 맞춰줄 것처럼 읽히지만 실제 동작은 `CREATE TABLE IF NOT EXISTS`에 가깝다. 마이그레이션 도구(Alembic 등) 없이 이것만 쓰면, 모델에 컬럼을 추가해도 기존 테이블은 영원히 옛 모양으로 남는다.

둘째, **프론트엔드가 그 실패를 조용히 삼켰다.** `WorkspaceContext.refresh()`의 `catch`는 주석까지 달아 의도적으로 침묵하고 있었고, 대시보드의 문서 조회도 `.catch(() => setDocuments([]))`였다.

```ts
} catch {
  // 대시보드 패널은 조용히 실패한다 — 원인 파악은 채팅/업로드 화면의 에러 메시지에서 이뤄진다.
}
```

그 결과 화면에서 **"항목이 0개"와 "요청이 실패함"이 완전히 동일하게 보였다.** 신규 배포라 데이터가 없는 게 자연스러운 상황이었기 때문에, 빈 목록을 정상으로 읽고 넘어갔다.

### 시도했지만 안 된 것

- **브라우저 E2E 확인**: 로그인 → 대시보드 → 그룹 생성 → 공지 등록을 실제로 수행하고 "검증 완료"로 판단했다. 하필 정상 동작한 네 가지(`users`, `groups`, `group_memberships`, `announcements`)가 모두 스키마가 맞는 테이블이었고, 깨진 네 가지는 전부 침묵하는 경로였다. **UI 관찰만으로는 이 장애를 잡을 수 없었다.**
- 컬럼 추가 후 "`create_all`이 처리하겠지"라고 가정한 것 — 실제로는 `ALTER TABLE`을 하지 않는다.

### 해결

대상 4개 테이블이 모두 **행 0개**임을 먼저 확인한 뒤(참조하는 외래키도 없음) 삭제하고 현재 모델로 재생성했다. 행이 0이 아니면 중단하도록 assert를 걸고 실행했다.

```python
with engine.begin() as c:
    for t in ['chat_messages', 'documents', 'schedules', 'todos']:
        n = c.execute(text(f'SELECT count(*) FROM {t}')).scalar()
        assert n == 0, f'{t}에 {n}행이 있어 중단'
        c.execute(text(f'DROP TABLE {t}'))

Base.metadata.create_all(bind=engine)
```

`users`·`groups`·`group_memberships`는 실제 계정 데이터가 있어 건드리지 않았다.

동시에 **침묵하던 예외 처리를 걷어냈다.**
- `WorkspaceContext`에 `error: string | null`을 추가하고 `refresh()`의 `catch`가 이를 설정하도록 변경
- `SmartDashboardPanel`과 대시보드에 경고 배너 추가 — "비어 있는 것이 아니라 조회에 실패한 상태"라고 명시

### 검증

```
chat_messages ['id', 'group_id', 'sender', 'content', 'is_bot', 'created_at']
documents     ['id', 'group_id', 'is_template', 'source_type', 'category', 'filename',
               'summary', 'summary_json', 'created_at']
schedules     ['id', 'group_id', 'title', 'scheduled_date', 'created_at', 'updated_at']
todos         ['id', 'group_id', 'content', 'due_date', 'is_done', 'created_at', 'updated_at']
```

`pytest` 50건 / `tsc --noEmit` / `next build` 모두 통과.

### 추후 관리

- **`create_all`만으로는 스키마 변경을 배포할 수 없다.** 모델에 컬럼을 추가할 때마다 수동 `ALTER TABLE`이 필요하며, 지금처럼 놓치기 쉽다. 데이터가 쌓이기 시작하면 Alembic 도입이 사실상 필수다. (현재는 데이터가 거의 없어 drop & recreate로 넘어감)
- 배포 후 확인 항목에 **DB 스키마 대조**를 넣어야 한다. UI 관찰로는 침묵하는 실패를 못 잡는다.
- 남아 있는 조용한 `catch`가 더 있는지 주기적으로 점검할 것.

### 배운 점

**빈 화면은 "데이터가 없다"는 뜻이 아니라 "아무것도 모른다"는 뜻이다.** 신규 배포 직후처럼 빈 상태가 자연스러운 상황에서는 이 둘을 구분할 단서가 화면에 전혀 없다. 오류를 삼키는 `catch`는 그 순간에는 화면을 깔끔하게 만들어주지만, 정확히 장애를 발견해야 할 때 발견을 막는다.

그리고 **"E2E로 확인했다"는 확인한 경로에 대해서만 참이다.** 이번엔 정상 동작한 기능들이 우연히 전부 스키마가 맞는 쪽이었고, 깨진 쪽은 전부 침묵했다. 확인했다고 말하기 전에 "무엇을 확인했고 무엇을 확인하지 않았는가"를 나눠서 봐야 한다.

---

## TS-015 · 요약 리포트의 이모지가 프론트엔드 수정으로 사라지지 않음 (출처가 LLM 프롬프트)

| | |
|---|---|
| **날짜** | 2026-08-05 |
| **영역** | BE / UX |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 20분 (원인 파악), 이후 구조 전환 |

### 증상

"UI에 애플 이모티콘 쓰는 것을 자제해달라"는 요구에 따라 프론트엔드 전반의 이모지를 제거했는데도, 통화 요약과 문서 요약 결과 화면에는 이모지가 그대로 남았다.

```
[📌 한 줄 요약]
- 9월 출시 일정을 확정함

[💬 주요 논의 내용]
- ...

[🙋‍♀️ 고객/상대방 요구사항]
- ...

[✅ 다음 액션 아이템]
- ...

[📝 기타 메모]
- ...
```

### 재현 조건

1. `/calls` 또는 `/documents`에서 파일 업로드 → 요약 실행
2. 결과 리포트 또는 `/history`에서 해당 항목 펼치기
3. 프론트엔드 소스 전체를 이모지로 grep해도 아무것도 나오지 않음

### 원인

**표면**: 프론트엔드 어딘가에 이모지가 남아 있다고 판단했다. 실제로는 프론트엔드 코드에 해당 이모지가 한 글자도 없었다.

**근본**: `gemini_service.py`의 `CALL_SUMMARY_PROMPT` / `DOCUMENT_SUMMARY_PROMPT`가 LLM에게 이모지 섹션 헤더를 **출력 형식으로 강제**하고 있었다.

```python
CALL_SUMMARY_PROMPT = """
...
[📌 한 줄 요약]
- 통화 내용을 한두 문장으로 요약

[💬 주요 논의 내용]
...
규칙:
- 출력은 반드시 위와 같은 섹션 제목 형식을 그대로 사용할 것.
"""
```

그 응답 문자열이 통째로 `documents.summary` TEXT 컬럼에 저장되고(`main.py`), 화면에서는 `<pre>{summary}</pre>`로 그대로 출력됐다(`UploadPanel.tsx`, `history/page.tsx`). 즉 **화면에 보이는 이모지의 출처는 코드가 아니라 프롬프트**였고, 렌더링 계층에는 손댈 지점이 아예 없었다.

같은 원인으로 세 가지가 동시에 막혀 있었다는 점도 이때 드러났다:
- 요약을 섹션 단위로 다룰 수 없음 (한 줄 요약만 카드에 띄우기, 액션 아이템만 할 일로 넘기기 불가)
- 대시보드에 집계할 구조가 없어 정적 카드 나열이 한계
- 이모지 제거 불가

### 시도했지만 안 된 것

- **프론트엔드 전역 이모지 grep 후 제거**: `Sidebar.tsx`, `MobileNav.tsx`, `dashboard/page.tsx` 등에서 8건을 찾아 제거했다. 실제로 남아 있던 것들이라 제거 자체는 유효했지만, **요약 리포트의 이모지는 그대로였다.**
- **프론트엔드에서 정규식으로 이모지 치환하는 방안 검토**: LLM 출력 형식이 흔들리면 같이 깨지고, 근본 원인을 화면단에서 덮는 방식이라 채택하지 않았다.

### 해결

프롬프트를 이모지 섹션 헤더 대신 **`response_schema` 기반 구조화 JSON**으로 교체했다. 같은 파일의 `classify_document_category`와 `extract_chat_actions`가 이미 쓰던 방식이라 새 의존성은 없었다.

```python
_SUMMARY_SCHEMA = {
    "type": "OBJECT",
    "required": ["headline", "key_points", "requests", "action_items", "notes"],
    "properties": {
        "headline": {"type": "STRING"},
        "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "requests": {"type": "ARRAY", "items": {"type": "STRING"}},
        "action_items": {...},
        "notes": {"type": "STRING"},
    },
}
```

부수 조치:
- `Document.summary_json` (Text, nullable) 추가. 평문 사본은 `summary`에 계속 저장해 이력 검색(문자열 매칭)과 구버전 레코드 호환을 유지.
- `normalize_summary()`로 저장 전 필드 보정 (빈 content 제거, 알 수 없는 priority → `normal`, 리스트 아닌 값 → `[]`).
- 오디오 + `response_schema` 조합이 실패할 여지가 있어, 파싱 실패 시 스키마 없이 재호출해 평문만 확보하는 폴백을 넣었다. 이 경우 `summary_json`은 `NULL`이 되고 프론트는 평문으로 렌더한다.

### 검증

- `pytest` 50건 통과 (신규 9건: 정규화 보정, 평문 렌더, 구조화 저장, `auto_todo` 할 일 생성, 폴백 경로, `POST /todos` 권한 3건)
- 실제 Gemini 호출로 합성 회의록을 요약 — 스키마 준수 확인. 상대 날짜("8월 12일까지")가 `"2026-08-12"` 절대 날짜로, 급한 건이 `priority: "high"`로 정확히 매핑됐고 **출력 전체에 이모지 없음**
- `npx tsc --noEmit` / `next build` 통과

### 추후 관리

- **기존 Postgres(Neon) 테이블에는 `create_all`이 컬럼을 추가하지 않는다.** DB를 리셋하지 않는 경우 아래가 필요하다.
  ```sql
  ALTER TABLE documents ADD COLUMN summary_json TEXT;
  ```
- 구버전 레코드는 `structured: null`로 내려가 평문 폴백으로 렌더된다. 데이터 마이그레이션은 하지 않았다.
- 폴백 경로가 조용히 동작하므로, `summary_json IS NULL` 비율이 올라가면 스키마 준수가 깨지고 있다는 신호다.

### 배운 점

LLM 출력이 화면에 그대로 나오는 구간에서는, **보이는 문자열의 출처가 코드가 아니라 프롬프트일 수 있다.** 프론트엔드 grep이 아무것도 찾지 못했을 때 "이미 다 지웠다"로 해석한 것이 첫 오판이었다. 정확한 해석은 "여기가 출처가 아니다"였고, 그 신호를 제대로 읽었다면 백엔드를 20분 먼저 봤을 것이다.

부수적으로, 프롬프트가 출력 **형식**을 텍스트로 강제하는 구조는 표현 계층을 LLM에 위임하는 것과 같다. 스키마로 데이터만 받고 표현은 UI가 정하게 바꾸면, 이모지 문제뿐 아니라 섹션별 렌더링·집계·액션 연동이 한꺼번에 열린다.

---

## TS-014 · 배포된 앱에서 로그인이 무한 대기 (콜드스타트 + 구버전 배포 + 환경변수 누락)

| | |
|---|---|
| **날짜** | 2026-08-05 |
| **영역** | Infra / Auth |
| **심각도** | High |
| **상태** | 해결됨 |
| **소요 시간** | 약 1시간 |

### 증상
그룹/인증 기능을 프론트엔드에 배포한 뒤, 실제 배포 주소에서 로그인을 시도하면 버튼이 "로그인 중..."에서 멈춘 채 아무 반응이 없었다. 브라우저 콘솔에는 에러가 없고, 네트워크 탭에도 백엔드 요청이 아예 잡히지 않았다.

### 재현 조건
- 환경: 프론트 Vercel(`onque-frontend.vercel.app`), 백엔드 Render 무료 티어
- 재현 절차: 15분 이상 유휴 상태 후 배포 주소에서 로그인 시도
- 재현율: 유휴 후 첫 요청에서 항상

### 원인
세 가지 문제가 겹쳐 있었고, 표면 증상은 하나였다.

- **표면**: "로그인이 안 된다" → 프론트엔드 인증 코드 버그로 오해하기 쉬움.
- **근본 1 (무응답의 직접 원인)**: Render 무료 인스턴스는 유휴 시 슬립되고, 깨어나는 데 실측 **54초**가 걸린다. 프론트에는 타임아웃도 안내 문구도 없어서 그냥 멈춘 것처럼 보였다.
- **근본 2 (실제로 로그인이 불가능했던 원인)**: 백엔드가 인증 기능 병합 **이전 버전**으로 떠 있었다. `openapi.json`을 직접 조회해보니 `/todos`, `/documents` 같은 구버전 라우트만 있고 `/api/v1/auth/login`은 아예 없었다(404).
- **근본 3 (재배포하면 터졌을 문제)**: `auth.py:15`가 `os.environ["JWT_SECRET"]`로 필수 조회하는데 `render.yaml`의 `envVars`에는 `GOOGLE_API_KEY`, `DATABASE_URL`만 선언돼 있었다. 그대로 재배포했다면 기동 즉시 `KeyError`로 죽었을 것이다. 배포 전에 코드를 훑다가 발견했다.

**확인 방법**: 서비스 존재 여부를 판별할 때, 존재하지 않는 Render 서브도메인은 즉시 404를 주는 반면 문제의 주소는 90초 대기 후 무응답(`status=000`)이었다. 이 차이로 "서비스가 삭제된 것이 아니라 기동 실패/슬립 상태"임을 구분했다.

```
# 존재하지 않는 주소
$ curl -s -o /dev/null -w "status=%{http_code}\n" https://onque-backend-nonexistent-xyz123.onrender.com/
status=404

# 문제의 주소 (라우팅은 살아있으나 응답 없음)
$ curl -s -o /dev/null -w "status=%{http_code} time=%{time_total}s\n" https://onque-backend-<REDACTED>.onrender.com/ --max-time 90
status=000 time=90.001938s
```

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| 브라우저 콘솔·네트워크 탭 확인 | 단서 없음 | 요청이 pending 상태로 남아 있어 에러도 응답도 잡히지 않았다. 콜드스타트라는 사실을 모르면 여기서 막힌다 |
| `curl`로 백엔드 루트 호출 | 처음엔 1.4초 만에 200 응답 | 이미 깨어 있는 상태를 우연히 찔러서 "백엔드는 멀쩡하다"고 잘못 판단했다. 잠시 후 다시 호출하니 90초 무응답이 나와서야 슬립 동작을 인지 |
| Render 대시보드에서 서비스 찾기 | 사용자가 서비스를 못 찾음 | 실제로는 존재했다. 이 때문에 "서비스가 삭제됐다"는 잘못된 가설로 새 서비스 생성까지 준비했다 |

### 해결
1. **구버전 배포**: Render가 git push에 자동 반응하도록 되어 있어, 이후 커밋 푸시로 신버전이 배포됨. `openapi.json`에 `/api/v1/auth/login`, `/signup`, `/groups`, `/me`, `/announcements`가 나타난 것으로 확인.
2. **`JWT_SECRET` 누락**: `render.yaml`에 `generateValue: true`로 추가해 Render가 안전한 랜덤값을 자동 생성하도록 함. 비밀값을 저장소에 넣지 않으면서 필수 변수를 보장한다.
3. **콜드스타트 체감**: `useSlowRequestHint` 훅을 만들어 요청이 3초를 넘기면 로그인/회원가입 폼에 "서버를 깨우는 중입니다. 처음 접속은 1분까지 걸릴 수 있습니다." 안내를 띄우도록 함. 무료 티어를 유지하면서 멈춘 것으로 오해하지 않게 하는 선택.

추가로, 로그인에 성공해도 소속 그룹이 없어 모든 화면이 비는 문제가 드러나, 첫 가입자(admin)에게 기본 그룹을 자동 생성·가입시키는 온보딩을 함께 넣었다.

### 검증
- `curl`로 잘못된 자격증명 로그인 → `401` + `{"code":"AUTH_INVALID_CREDENTIALS"}` (봉투 형식 정상, DB 조회까지 도달 확인)
- 회원가입 → `role: admin`, `/api/v1/me`의 `groups`에 `기본 그룹` 자동 생성 확인
- 브라우저로 로그인 → 대시보드 진입, 사이드바 그룹 선택기에 `기본 그룹` 표시 확인
- 백엔드 테스트 36개 전부 통과 (자동 온보딩 테스트 2건 추가, 기존 테스트 1건은 바뀐 동작에 맞게 수정)

### 추후 관리
- **무료 티어 콜드스타트는 근본 해결이 아니라 안내로 우회한 상태다.** 포트폴리오 시연 직전에 미리 한 번 접속해 깨워두거나, 외부 cron으로 주기적 헬스체크를 걸거나, 유료 티어로 올리는 선택지가 남아 있다.
- 자동 온보딩은 **첫 가입자에게만** 적용된다. 두 번째 이후 가입자는 관리자가 초대해야 하는데 아직 그룹 관리 UI가 없어, 앱 안에서는 초대할 방법이 없다.
- `render.yaml`과 실제 코드가 요구하는 환경변수가 어긋나면 기동 즉시 죽는다. 새 필수 환경변수를 추가할 때 블루프린트도 함께 갱신해야 한다.

### 배운 점
- **한 번의 성공 응답으로 "서비스 정상"이라 결론내면 안 된다.** 슬립되는 무료 인스턴스는 깨어 있을 때와 잠들었을 때 완전히 다르게 행동한다. 최소 두 번, 간격을 두고 확인해야 한다.
- **"없다"와 "응답하지 않는다"는 다르다.** 존재하지 않는 리소스(즉시 404)와 기동 실패(타임아웃)를 구분하는 대조 실험이 잘못된 가설을 빨리 접게 해줬다.
- 배포 실패는 로그를 봐야 알 수 있지만, **배포 전에 코드가 요구하는 환경변수와 배포 설정을 대조하면 미리 잡을 수 있다.** `grep`으로 `os.environ`/`getenv`를 훑는 30초가 실패한 배포 한 번보다 싸다.

---

## TS-013 · pytest용 SQLite 인메모리 DB가 FastAPI 워커 스레드에서 `no such table` 에러

| | |
|---|---|
| **날짜** | 2026-08-05 |
| **영역** | BE (테스트 인프라) |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 30분 (구현·리뷰·수정 라운드 포함) |

### 증상
그룹/인증 구조 도입 작업의 Task 1(pytest + SQLite 인메모리 테스트 인프라)에서, `conftest.py`의 `client` fixture로 DB를 실제로 건드리지 않는 라우트(`GET /`)를 테스트할 때는 통과했지만, DB를 쓰는 라우트(`GET /todos`)를 테스트하는 순간 다음 에러로 실패했다.

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: todos
```

### 재현 조건
- 환경: `create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})`로 만든 SQLite 엔진에 `poolclass`를 지정하지 않음
- 재현 절차: fixture 함수(메인 스레드)에서 `Base.metadata.create_all(bind=TEST_ENGINE)` 실행 → FastAPI `TestClient`로 동기 `Depends(get_db)` 라우트 호출
- 재현율: 항상. DB를 쓰지 않는 라우트(`GET /`)는 절대 이 문제를 드러내지 않아, 애초에 검증용으로 고른 스모크 테스트(`test_health_check`)가 문제를 못 잡고 통과시켰다.

### 원인
- **표면**: "테이블이 없다"는 메시지라 스키마 생성(`create_all`)을 빼먹은 줄 알기 쉽다.
- **근본**: SQLite `:memory:` 엔진의 기본 커넥션 풀은 `SingletonThreadPool`로, 스레드마다 별도의 인메모리 DB를 새로 만든다. FastAPI는 동기(`def`, 비-`async def`) 의존성인 `get_db`를 `run_in_threadpool`로 별도 워커 스레드에서 실행하는데, `create_all()`은 fixture가 실행되는 메인 스레드에서 돌기 때문에 워커 스레드는 매번 텅 빈 새 DB를 보게 된다. 모든 스레드가 같은 커넥션(=같은 인메모리 DB)을 공유하게 하려면 `poolclass=StaticPool`이 필요하다 — SQLite+FastAPI 테스트 조합에서 잘 알려진 함정.
- **확인 방법**: 코드 리뷰 서브에이전트가 동일 조건(SQLite `:memory:` 엔진 + 메인 스레드 `create_all` + 동기 `Depends(get_db)` 라우트 + `TestClient`)을 별도 스크립트로 직접 재현해 정확히 같은 에러를 재확인했다.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 애초 작성한 계획 문서의 `conftest.py` 코드 자체에 `poolclass` 누락이 있었고, 구현 직후 코드 리뷰 단계에서 바로 걸러져 별도 시행착오 없이 원인이 특정됨 |

### 해결
`TEST_ENGINE` 생성 코드에 `from sqlalchemy.pool import StaticPool`을 추가하고 `create_engine(..., poolclass=StaticPool)`로 수정. 재발 방지로, fixture 검증용 테스트에 DB를 실제로 쓰는 라우트(`GET /todos`) 호출을 추가했다 — 기존엔 DB 미사용 라우트만 테스트해서 이 버그를 놓쳤었다.

### 검증
`StaticPool` 적용 후 `GET /todos`를 호출하는 신규 테스트를 포함해 전체 pytest 스위트가 통과했고, 이후 이어진 태스크들의 DB 의존 테스트(회원가입/로그인/그룹 등)도 모두 정상 동작했다.

### 추후 관리
- **재발 방지**: 앞으로 SQLite 인메모리 엔진으로 FastAPI 테스트 fixture를 만들 때는 `poolclass=StaticPool`을 기본값으로 넣는다.
- **모니터링**: 해당 없음(테스트 전용 이슈).
- **남은 리스크**: fixture 스모크 테스트를 짤 때 DB 미사용 라우트만 고르면 이런 종류의 버그를 계속 놓칠 수 있다 — 최소 하나는 DB 의존 라우트를 포함시키는 습관이 필요.

## TS-012 · 프로젝트 폴더 이동 후 venv 셔뱅 경로가 깨져 `ModuleNotFoundError`

| | |
|---|---|
| **날짜** | 2026-08-05 |
| **영역** | Infra |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 10분 |

### 증상
로컬에서 앱을 시연하려고 백엔드(`uvicorn main:app`)를 실행하자 곧바로 다음 에러로 죽었다.

```
ModuleNotFoundError: No module named 'sqlalchemy'
```

`sqlalchemy`는 `requirements.txt`에 명시돼 있고 이전에 정상 설치되어 있던 패키지라 의아했다.

### 재현 조건
- 환경: 프로젝트 폴더가 원래 `~/Desktop/OnQue`였다가 이후 `~/Project/OnQue`로 이동됨. `venv/`는 그 이동 전에 `~/Desktop/OnQue`에서 생성된 것을 그대로 가지고 옴.
- 재현 절차: 이동된 폴더에서 `source venv/bin/activate && uvicorn ...` 또는 `./venv/bin/python -m uvicorn ...` 실행
- 재현율: 항상 (venv를 재생성하기 전까지)

### 원인
- **표면**: `sqlalchemy` import 실패
- **근본**: `venv/bin/uvicorn`, `venv/bin/pip` 등 venv 내부의 실행 스크립트들은 셔뱅(shebang) 줄에 venv 생성 당시의 절대 경로를 그대로 박아둔다(`#!/Users/tina/Desktop/OnQue/venv/bin/python3.12`). 폴더가 `~/Project/OnQue`로 이동되면서 그 경로의 `python3.12` 실행파일 자체가 더는 존재하지 않게 됐고, `uvicorn` 실행 시 셸이 시스템 전역 Python(3.13)으로 조용히 폴백해 venv에 설치된 패키지를 전혀 못 찾는 상태가 됐다.
- **확인 방법**: `./venv/bin/pip show sqlalchemy` 실행 시 `bad interpreter: /Users/tina/Desktop/OnQue/venv/bin/python3.12: no such file or directory` 에러로 셔뱅 경로 문제를 직접 확인.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| `source venv/bin/activate` 후 재실행 | 동일하게 실패 | activate 스크립트도 결국 셔뱅이 깨진 인터프리터를 가리켜, PATH만 바뀔 뿐 실제 실행 파일 문제는 해결 안 됨 |

### 해결
`rm -rf venv && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`로 현재 경로(`~/Project/OnQue`) 기준으로 venv를 완전히 재생성.

### 검증
`./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8001` 정상 기동, `curl localhost:8001/docs` 200 응답 확인.

### 추후 관리
- **재발 방지**: 프로젝트 폴더를 다시 옮기게 되면 venv는 절대 같이 옮기지 말고 항상 새 위치에서 재생성한다. venv를 `.gitignore`에 유지하는 것도 이 때문에 중요 (재현 가능한 산출물로 취급).
- **모니터링**: 해당 없음.
- **남은 리스크**: 없음 — 원인이 명확하고 재생성으로 완전히 해소됨.

## TS-011 · Vercel이 GitHub push에 자동 반응하지 않아 백엔드만 재배포되고 프론트는 구버전으로 남음

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | Infra |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 5분 |

### 증상
DB 연동 기능을 `git push`한 뒤 Render 백엔드는 자동 재배포되어 `/todos` 등 신규 엔드포인트가 정상 응답했지만, 같은 시점에 Vercel 프론트엔드(`https://onque-frontend.vercel.app`)에 접속하면 새로 추가한 `/chat` 등 경로가 반영되지 않은 상태였다.

### 재현 조건
- 환경: GitHub 저장소(`jjssspark/OnQue`) → Render(Blueprint 자동 배포 연동) / Vercel(초기에 `npx vercel` CLI로 device-code 로그인 후 수동 배포)
- 재현 절차: 코드 변경 → `git push origin main` → Render는 몇 분 내 자동 재배포, Vercel은 아무 변화 없음
- 재현율: 항상 (Vercel 프로젝트가 GitHub App으로 연결된 게 아니라 CLI로 최초 배포됐기 때문)

### 원인
- **표면**: 백엔드는 최신인데 프론트엔드만 예전 버전으로 남아 있음
- **근본**: 이 프로젝트의 Vercel 배포는 초기 설정 시 GitHub 저장소 연동(웹훅 기반 자동 배포)이 아니라 `npx vercel --prod --yes` CLI 명령으로 직접 배포했다. Render는 `render.yaml` Blueprint가 GitHub push를 감지해 자동 재배포하지만, Vercel 쪽은 그런 트리거가 걸려 있지 않아 코드를 아무리 push해도 그 자체로는 재배포되지 않는다.
- **확인 방법**: `curl -s -o /dev/null -w "%{http_code}" https://onque-frontend.vercel.app/documents` 등으로 신규 라우트를 직접 호출해 404를 확인. Render 쪽 동일 점검(`/openapi.json`에 새 경로 포함 여부)은 정상이라 두 배포 파이프라인의 동작 차이임을 특정.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| git push 후 그대로 대기 | 프론트 반영 안 됨 | Vercel 프로젝트가 GitHub 웹훅에 연결돼 있지 않음 |

### 해결
`onque-frontend/`에서 `npx vercel --prod --yes`를 수동으로 재실행해 최신 커밋 기준으로 프로덕션에 재배포.

### 검증
`curl -s -o /dev/null -w "%{http_code}\n" https://onque-frontend.vercel.app/chat` 등으로 200 확인, 브라우저로 대시보드 접속해 실제 DB 데이터(할 일·일정·이력)가 렌더링되는 것까지 최종 확인.

### 추후 관리
- **재발 방지**: 없음(수동 배포 절차를 알고 있는 상태로 진행). Vercel 대시보드에서 GitHub App 연동을 켜면 이후 `git push`만으로 자동 배포되도록 개선 가능 — 사용자에게 안내함.
- **모니터링**: 없음.
- **남은 리스크**: 앞으로도 코드 변경 후 `git push`만 하고 Vercel 수동 배포를 잊으면 같은 문제가 재발한다.
- **후속 작업**: (선택) Vercel 프로젝트 설정에서 GitHub 저장소 연동 활성화.

### 배운 점
"같은 GitHub 저장소를 보고 있다"는 사실만으로 모든 배포 플랫폼이 동일하게 자동 배포된다고 가정하면 안 된다. 각 플랫폼이 *어떤 방식으로* 연결됐는지(웹훅 기반 연동 vs. CLI 수동 배포)를 배포 초기에 확인해두지 않으면, "푸시했는데 왜 안 바뀌지"를 매번 새로 진단해야 한다.

### 참고
- 없음

---

## TS-010 · Gemini 무료 티어 일시 과부하(503)로 `@비서` 봇 답변이 폴백 메시지로 나감

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | 외부API |
| **심각도** | Low |
| **상태** | 해결됨 (재시도로 해소, 코드 변경 없음) |
| **소요 시간** | 약 15분 (원인 특정 포함) |

### 증상
팀 채팅에서 `@비서 오늘 할 일 뭐 있어?`처럼 멘션했을 때, 메시지 자체는 정상 저장되고 할 일/일정 자동 추출도 잘 되는데 봇 답변만 아래처럼 고정 폴백 문구로 나왔다.

```
죄송해요, 지금은 답변을 생성하지 못했어요.
```

### 재현 조건
- 환경: `gemini_service.generate_bot_reply()`, 모델 `gemini-2.5-flash`
- 재현 절차: `/chat/messages`에 `@비서`가 포함된 메시지 POST
- 재현율: 간헐적 (같은 프롬프트를 몇 초 뒤 재시도하면 정상 응답)

### 원인
- **표면**: 봇 답변 생성 함수가 예외를 삼키고 고정 폴백 문자열을 반환.
- **근본**: `generate_bot_reply()` 내부 `client.models.generate_content()` 호출이 Google 서버로부터 `503 UNAVAILABLE`을 받았음. 같은 프롬프트를 바로 재시도하면 정상 응답이 오는 것으로 보아 코드 결함이 아니라 Gemini API 쪽의 순간적 트래픽 과부하였다.
- **확인 방법**: `try/except`로 감춰진 실제 예외를 보려고 함수 내부 로직을 그대로 복제해 직접 실행, `traceback.print_exc()`로 전체 스택 확인:
  ```
  google.genai.errors.ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message':
  'This model is currently experiencing high demand. Spikes in demand are usually
  temporary. Please try again later.', 'status': 'UNAVAILABLE'}}
  ```
  직후 동일 호출을 재실행하니 정상 응답(`response.candidates`에 실제 텍스트 포함)을 받아, 일시적 과부하였음을 확인.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 전체 스택트레이스에서 `503 UNAVAILABLE`이 바로 드러나 다른 가설을 세울 필요가 없었다 |

### 해결
코드 변경 없음. `gemini_service.py`의 `generate_bot_reply()`는 이미 예외 발생 시 사용자에게 자연스러운 한국어 폴백 메시지("죄송해요, 지금은 답변을 생성하지 못했어요.")를 보여주도록 설계돼 있어, 이 상황 자체는 UX상 허용 가능한 정상 동작으로 판단하고 그대로 두었다.

### 검증
같은 프롬프트로 몇 초 뒤 재호출 → 정상 텍스트 응답 확인. 이후 브라우저 e2e 테스트에서도 대부분의 호출은 정상 응답했다.

### 추후 관리
- **재발 방지**: 없음(외부 API 가용성 문제라 애플리케이션 코드로 근본 해결 불가).
- **모니터링**: 없음. 필요하면 재시도 로직(지수 백오프 1~2회)을 추가해 사용자 체감 실패율을 낮출 수 있음 — 미적용.
- **남은 리스크**: Gemini API가 과부하 상태일 때는 여전히 폴백 메시지가 노출된다.
- **후속 작업**: (선택) `generate_bot_reply()`에 짧은 재시도(예: 1회, 1~2초 대기) 추가 검토.

### 배운 점
`except Exception`으로 폭넓게 잡아 사용자 친화적 폴백을 보여주는 설계는 안정성 면에서 옳지만, 그 대가로 "코드 버그"와 "외부 서비스 일시 장애"가 로그상 구분되지 않는다. 폴백이 반복될 때는 항상 `except` 블록을 우회해 실제 예외 타입(여기서는 `google.genai.errors.ServerError`)을 직접 확인하는 것이 원인 오판을 막는 가장 빠른 방법이었다.

### 참고
- 없음

---

## TS-009 · SQLAlchemy가 `postgresql://` 스킴에서 기본으로 psycopg2를 찾는데 psycopg3만 설치되어 있어 `ModuleNotFoundError`

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | DB |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 10분 |

### 증상
`DATABASE_URL`을 정상적으로 읽도록 고친 뒤(TS-007, TS-008 해결 후) `main.py`를 임포트하면 다음 에러로 죽었다.

```
File ".../sqlalchemy/dialects/postgresql/psycopg2.py", line 696, in import_dbapi
    import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

### 재현 조건
- 환경: `requirements.txt`에 `psycopg[binary]==3.2.10`(psycopg **3**)만 명시, Neon이 발급한 connection string은 `postgresql://user:pass@host/db?sslmode=require` 형태(스킴에 드라이버 명시 없음)
- 재현 절차: `python -c "import main"`
- 재현율: 항상

### 원인
- **표면**: `psycopg2`라는, 애초에 설치한 적 없는 패키지를 찾다가 실패.
- **근본**: SQLAlchemy는 URL 스킴이 `postgresql://`(드라이버 미지정)이면 **기본값으로 psycopg2용 드라이버**를 로드하려 시도한다. 이 프로젝트는 최신 유지보수 라인인 psycopg3(`psycopg[binary]`)를 설치했는데, SQLAlchemy에게 "psycopg3를 쓰라"고 명시하지 않아 기본 동작(psycopg2 시도)과 실제 설치된 패키지가 어긋났다.
- **확인 방법**: 트레이스백이 `sqlalchemy/dialects/postgresql/psycopg2.py`를 직접 가리켜 원인이 즉시 드러났다.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 에러 메시지가 원인을 명확히 지목해 바로 수정 |

### 해결
`db.py`에서 `postgresql://`로 시작하는 URL을 `postgresql+psycopg://`(psycopg3 드라이버 명시)로 변환한 뒤 엔진을 생성하도록 수정.

```python
# psycopg(v3) 드라이버를 쓰도록 스킴을 명시한다. Neon 등이 주는 기본
# `postgresql://`는 SQLAlchemy가 psycopg2를 찾게 만든다.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

### 검증
`python -c "import main; print(sorted(r.path for r in main.app.routes if hasattr(r,'path')))"` 실행 → 에러 없이 전체 라우트 목록 출력, DB 테이블 생성(`Base.metadata.create_all`)까지 정상 완료.

### 추후 관리
- **재발 방지**: `requirements.txt`에 psycopg3를 쓰기로 한 이상, `DATABASE_URL`을 다루는 코드는 항상 스킴을 `+psycopg`로 명시하는 규칙을 `db.py` 안에 코드로 강제해뒀다(사람이 URL 형식을 매번 기억할 필요 없음).
- **모니터링**: 없음.
- **남은 리스크**: 없음.
- **후속 작업**: 없음.

### 배운 점
DB 드라이버를 pip로 설치하는 것과, ORM(SQLAlchemy)이 그 드라이버를 실제로 사용하도록 커넥션 문자열에 명시하는 것은 별개의 단계다. 클라우드 DB 서비스(Neon, Supabase 등)가 주는 기본 `postgresql://` connection string은 드라이버에 대해 중립적이므로, 어떤 드라이버를 설치했는지에 따라 애플리케이션 코드에서 스킴을 보정해줘야 한다.

### 참고
- SQLAlchemy PostgreSQL 드라이버 문서: <https://docs.sqlalchemy.org/en/20/dialects/postgresql.html>

---

## TS-008 · `.env`의 `DATABASE_URL` 키 뒤 공백 + 키 없는 값만 있는 빈 줄이 섞여 환경변수 인식 실패

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | Infra |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 10분 |

### 증상
사용자가 Neon에서 발급받은 connection string을 `.env`에 추가했다고 확인했는데("했어"), `grep -q "^DATABASE_URL=" .env`로 확인하면 계속 "아직 없음"으로 나왔다.

### 재현 조건
- 환경: `/Users/tina/Project/OnQue/.env`
- 재현 절차: `grep -E "^DATABASE_URL="  .env` 실행
- 재현율: 항상 (파일 내용이 그렇게 저장돼 있었으므로)

### 원인
- **표면**: `DATABASE_URL=` 로 시작하는 줄이 없다고 grep이 보고.
- **근본**: 값 자체는 레딕트해 확인한 결과, ①`DATABASE_URL` 키 뒤에 공백이 붙어 `DATABASE_URL =...` 형태였고(`=` 앞 공백 때문에 `^DATABASE_URL=` 패턴에 안 걸림), ②그와 별개로 키 없이 값만 있는(`=<값>`) 정체불명의 빈 줄이 하나 더 섞여 있었다. 두 문제 모두 `.env`를 편집하는 과정에서 붙여넣기 실수로 생긴 것으로 추정(직접 확인은 안 함 — 추정).
- **확인 방법**: 비밀값을 노출하지 않기 위해 `sed -E 's/=.*/=<REDACTED>/' .env | cat -e`로 값은 가리고 줄 구조만 확인:
  ```
  GOOGLE_API_KEY=<REDACTED>$
  $
  =<REDACTED>$
  $
  DATABASE_URL=<REDACTED>
  ```
  (수정 전에는 `DATABASE_URL` 앞에 공백이 있었고, 3번째 줄이 `=<REDACTED>`로 키가 비어 있었다.)

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| `grep -q "^DATABASE_URL="` 재확인만 반복 | 계속 "없음" | grep 패턴 자체는 맞았고, 문제는 파일 내용 쪽이라 재확인만으로는 못 찾음. 실제 파일 구조를 값 레딕트 후 직접 들여다봐야 했다 |

### 해결
값은 절대 화면에 노출하지 않고 `sed`로 키 이름·구조만 교정:

```bash
# 1) 키 이름의 트레일링 공백 제거: "DATABASE_URL =" → "DATABASE_URL="
sed -i.bak -E 's/^DATABASE_URL[[:space:]]*=/DATABASE_URL=/' .env && rm .env.bak

# 2) 키 없이 "=값"만 있는 빈 줄 삭제
sed -i.bak '/^=/d' .env && rm .env.bak
```

### 검증
`grep -q "^DATABASE_URL=" .env && echo 설정됨` → "설정됨" 출력. 이후 `python -c "import main"`으로 실제 DB 연결까지 성공(TS-009로 이어짐)해 최종 확인.

### 추후 관리
- **재발 방지**: `.env.example`을 새로 만들어(`GOOGLE_API_KEY`, `DATABASE_URL` 키 목록만 문서화) 이후 값을 추가할 때 형식을 참고할 수 있게 함.
- **모니터링**: 없음.
- **남은 리스크**: 사람이 `.env`를 손으로 편집하는 한 같은 유형의 오타는 재발할 수 있음.
- **후속 작업**: 없음.

### 배운 점
환경변수가 "설정 안 됨"으로 읽힐 때는 값 자체보다 **줄 구조(키 이름의 공백, 빈 줄, 인코딩)** 를 먼저 의심해야 한다. 특히 비밀값이 섞인 파일을 진단할 때는 `sed`로 값만 레딕트하고 키/구조만 노출하는 방식을 쓰면, 실제 값을 노출하지 않고도 안전하게 원인을 좁힐 수 있다.

### 참고
- 없음

---

## TS-007 · `db.py`가 `.env`를 직접 로드하지 않아 import 순서에 따라 `DATABASE_URL`을 못 찾고 기동 실패

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | BE |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 5분 |

### 증상
`DATABASE_URL`을 `.env`에 넣은 직후(TS-008 수정 전 상태) `python -c "import main"`을 실행하면 다음 에러로 즉시 죽었다.

```
File "/Users/tina/Project/OnQue/main.py", line 10, in <module>
    import gemini_service
File "/Users/tina/Project/OnQue/gemini_service.py", line 12, in <module>
    from models import DOCUMENT_CATEGORIES
File "/Users/tina/Project/OnQue/models.py", line 6, in <module>
    from db import Base
File "/Users/tina/Project/OnQue/db.py", line 9, in <module>
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")
RuntimeError: DATABASE_URL 환경변수가 설정되어 있지 않습니다.
```

### 재현 조건
- 환경: `main.py` → `gemini_service.py`(내부에서 `load_dotenv()` 호출) → `models.py` → `db.py`(`os.getenv("DATABASE_URL")`만 호출, `load_dotenv()` 없음) import 체인
- 재현 절차: `python -c "import main"`
- 재현율: 항상 (모듈이 이 순서로 임포트되는 한)

### 원인
- **표면**: `.env`에 값을 넣었는데도 "설정 안 됨" 에러.
- **근본**: `.env` 로딩(`load_dotenv()`)이 `gemini_service.py`에만 있었다. Python import 체인상 `db.py`가 `gemini_service.py`보다 **먼저** 평가되는데(정확히는 `models.py`가 `db.py`를 import하는 시점에 `db.py` 최상단 코드가 실행됨), 이 시점엔 아직 `load_dotenv()`가 호출되지 않아 프로세스 환경변수에 `.env` 내용이 반영돼 있지 않았다.
- **확인 방법**: 트레이스백의 import 체인을 그대로 읽으면 `db.py`가 가장 먼저 죽는 지점이라는 게 바로 드러남.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 트레이스백만으로 원인이 명확했다 |

### 해결
`db.py`가 다른 모듈의 로딩 순서에 의존하지 않도록, 자체적으로 `.env`를 로드하게 수정.

```python
# 수정 전
import os
from sqlalchemy import create_engine
...
DATABASE_URL = os.getenv("DATABASE_URL")

# 수정 후
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
...
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
```

### 검증
`python -c "import main"` 재실행 → 이 에러는 사라지고 다음 문제(TS-009, psycopg 드라이버)로 넘어감. 최종적으로 전체 임포트 성공 확인.

### 추후 관리
- **재발 방지**: 환경변수를 읽는 모든 진입점 모듈(`db.py`, `gemini_service.py`)이 각자 `load_dotenv()`를 호출하도록 함 — 어느 모듈이 먼저 임포트되든 안전.
- **모니터링**: 없음.
- **남은 리스크**: 없음.
- **후속 작업**: 없음.

### 배운 점
여러 모듈에 걸쳐 환경변수를 읽을 때 `load_dotenv()`를 "진입점 한 곳에서만" 호출하면, 그 진입점보다 먼저 평가되는 다른 모듈에서는 환경변수가 비어 있을 수 있다. `python-dotenv`의 `load_dotenv()`는 여러 번 호출해도 안전(idempotent)하므로, 환경변수에 의존하는 모듈은 각자 방어적으로 호출하는 편이 import 순서에 안전하다.

### 참고
- python-dotenv 문서: <https://saurabh-kumar.com/python-dotenv/>

---

## TS-006 · 이력 페이지가 SSR에서는 빈 상태, 클라이언트에서는 즉시 localStorage 값으로 렌더링돼 hydration mismatch 발생

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | FE |
| **심각도** | Medium |
| **상태** | 해결됨 |
| **소요 시간** | 약 10분 |

### 증상
UI를 업무 플랫폼 셸로 재구성한 직후, `/history` 페이지에서 화면 좌하단에 Next.js dev 오버레이가 "1 Issue" 배지를 띄웠다. 열어보면:

```
Recoverable Error
Hydration failed because the server rendered HTML didn't match the client.
...
+       className="rounded-xl border border-border bg-surface shadow-sm"
-       className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-...
...
app/history/page.tsx (74:15) @ <unknown>
> 74 |     <button
```

### 재현 조건
- 환경: Next.js 16.3.0(App Router), `app/history/page.tsx`가 `'use client'` 컴포넌트, `useMemo(() => searchHistory(...), [query, typeFilter])`로 브라우저 `localStorage`에서 이력을 즉시 계산
- 재현 절차: `/history` 페이지 새로고침(서버 렌더링 + 클라이언트 hydration이 모두 일어나는 시점)
- 재현율: 항상 (localStorage에 이미 저장된 이력이 있는 상태에서)

### 원인
- **표면**: 서버가 만든 HTML과 클라이언트가 다시 그린 HTML이 달라 React가 hydration을 포기하고 해당 트리를 통째로 재생성.
- **근본**: `'use client'` 컴포넌트도 최초 진입 시 서버에서 한 번 렌더링(SSR)된다. 서버에는 `window`/`localStorage`가 없으므로 `lib/history.ts`의 `readAll()`이 빈 배열을 반환 → 서버가 만드는 HTML은 "이력 없음" 빈 상태(점선 테두리 카드)였다. 반면 클라이언트에서는 `useMemo`가 렌더링 시점에 즉시 `localStorage`를 읽어 실제 이력 목록(카드 리스트)을 그렸다. 이 두 결과물이 첫 페인트에서 서로 달라 hydration mismatch가 났다.
- **확인 방법**: Next.js dev 오버레이가 정확한 파일·줄(`app/history/page.tsx (74:15)`)과 diff를 직접 보여줘 원인이 바로 드러남.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 에러 메시지에 정확한 원인과 위치가 이미 담겨 있었다 |

### 해결
`useMemo`로 렌더링 중 즉시 계산하던 것을, `useState` 초기값을 빈 배열로 두고 `useEffect`(마운트 이후, 클라이언트에서만 실행)에서 채우는 방식으로 변경. 서버와 클라이언트의 **첫 렌더링 결과를 동일하게(빈 상태)** 맞춘 뒤, mount 이후에만 실제 데이터로 갱신되도록 함.

```tsx
// 수정 전
const entries = useMemo(
  () => searchHistory(query, typeFilter === 'all' ? undefined : typeFilter),
  [query, typeFilter]
);

// 수정 후
const [entries, setEntries] = useState<HistoryEntry[]>([]);
useEffect(() => {
  setEntries(searchHistory(query, typeFilter === 'all' ? undefined : typeFilter));
}, [query, typeFilter]);
```

### 검증
페이지 재접속 후 화면 좌하단 이슈 배지가 사라짐을 확인. 이력 목록도 정상적으로 표시되고, 항목 펼치기·검색·타입 필터 모두 정상 동작 확인.

### 추후 관리
- **재발 방지**: 이후 만든 `RecentActivity.tsx` 등 브라우저 저장소(당시 localStorage, 이후 백엔드 API)에 의존하는 컴포넌트는 처음부터 "초기값 없음 → `useEffect`에서 채움" 패턴으로 작성.
- **모니터링**: 없음(개발 환경 dev 오버레이가 사실상의 모니터링 역할).
- **남은 리스크**: 없음.
- **후속 작업**: 없음 — 이후 이 페이지 자체가 DB 기반(`/documents` API)으로 전환되며 localStorage 의존은 완전히 제거됨.

### 배운 점
Next.js의 `'use client'`는 "이 컴포넌트는 클라이언트에서도 상호작용 가능하다"는 뜻이지 "서버에서 렌더링 안 한다"는 뜻이 아니다. `window`/`localStorage`처럼 서버에 없는 브라우저 전용 값을 렌더링 중(useMemo, 함수 본문)에 직접 읽으면, 서버와 클라이언트의 첫 결과물이 갈라져 hydration mismatch가 난다. 브라우저 전용 데이터는 항상 "빈 초기값 → `useEffect`에서 채움" 패턴으로 서버/클라이언트 첫 렌더링을 일치시켜야 한다.

### 참고
- Next.js hydration 에러 문서: <https://nextjs.org/docs/messages/react-hydration-error>

---

## TS-005 · 서버 컴포넌트에서 함수를 클라이언트 컴포넌트 props로 전달해 Next.js 빌드가 `/calls`에서 실패

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | FE/Build |
| **심각도** | High |
| **상태** | 해결됨 |
| **소요 시간** | 약 10분 |

### 증상
UI를 3단 레이아웃으로 재구성하면서 통화/문서 요약 업로드 UI를 `UploadPanel` 공용 컴포넌트로 뽑고, `app/calls/page.tsx`(서버 컴포넌트)에서 `onSubmit={summarizeCall}`처럼 함수를 props로 넘겼더니 프로덕션 빌드가 실패했다.

```
Error occurred prerendering page "/calls". Read more: https://nextjs.org/docs/messages/prerender-error
Error: Event handlers cannot be passed to Client Component props.
  {accept: ..., acceptHint: ..., historyType: ..., submitLabel: ..., loadingLabel: ..., loadingHint: ..., emptySelectionMessage: ..., onSubmit: function}
                                                                                                                                                ^^^^^^^^
If you need interactivity, consider converting part of this to a Client Component.
    at ignore-listed frames {
  digest: '3398921023'
}
Export encountered an error on /calls/page: /calls, exiting the build.
⨯ Next.js build worker exited with code: 1 and signal: null
```

### 재현 조건
- 환경: Next.js 16.3.0 App Router, `app/calls/page.tsx`는 `'use client'` 없는 기본 서버 컴포넌트, `components/UploadPanel.tsx`는 `'use client'` 컴포넌트
- 재현 절차: `app/calls/page.tsx`에서 `lib/api.ts`의 `summarizeCall` 함수를 import해 `<UploadPanel onSubmit={summarizeCall} .../>`로 전달 후 `npm run build`
- 재현율: 항상

### 원인
- **표면**: 빌드가 `/calls` 정적 페이지 생성 단계에서 예외로 중단.
- **근본**: React Server Components 모델에서 서버 컴포넌트가 클라이언트 컴포넌트에 넘기는 props는 **직렬화 가능한 값**이어야 한다. 함수(이벤트 핸들러 포함)는 서버→클라이언트 경계를 건널 수 없다. `summarizeCall`은 일반 함수이지만 Next.js 입장에서는 "직렬화 불가능한 값을 클라이언트 컴포넌트 props로 넘긴 것"과 동일하게 취급돼 빌드 타임에 에러가 난다.
- **확인 방법**: 에러 메시지가 정확히 어떤 prop(`onSubmit: function`)이 문제인지, 어떤 페이지(`/calls`)에서 발생했는지까지 명시해 원인이 즉시 드러남.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음) | — | 에러 메시지가 원인과 해법 방향("Client Component로 바꾸는 걸 고려하라")까지 제시해 바로 수정 |

### 해결
`page.tsx`를 클라이언트 컴포넌트로 바꾸는 대신(서버 컴포넌트 이점을 유지하기 위해), `UploadPanel`이 함수를 props로 받지 않고 `historyType`(`'call' | 'document'`) 문자열만 받아 내부에서 어떤 API 함수를 호출할지 스스로 선택하도록 리팩터링.

```tsx
// components/UploadPanel.tsx — 수정 후
const SUMMARIZE_FN: Record<UploadKind, (file: File) => Promise<SummaryResponse>> = {
  call: summarizeCall,
  document: summarizeDocument,
};
// ...
const data = await SUMMARIZE_FN[historyType](file);
```

```tsx
// app/calls/page.tsx — onSubmit prop 제거
<UploadPanel
  accept=".mp3,.m4a,.wav"
  historyType="call"
  // onSubmit={summarizeCall}  ← 제거
  ...
/>
```

### 검증
`npm run build` 재실행 → `/calls`, `/documents`, `/chat`, `/history` 등 전 라우트가 정적 페이지로 정상 생성됨을 확인.

### 추후 관리
- **재발 방지**: 서버 컴포넌트에서 클라이언트 컴포넌트로 "동작"을 전달해야 할 때는 함수 prop 대신 문자열/enum 같은 식별자를 넘기고, 실제 함수 매핑은 클라이언트 컴포넌트 내부(또는 별도 client-only 모듈)에 두는 패턴을 이후에도 계속 사용.
- **모니터링**: 없음(빌드 타임에 항상 걸러짐).
- **남은 리스크**: 없음.
- **후속 작업**: 없음.

### 배운 점
Next.js App Router에서 "서버 컴포넌트가 기본값"이라는 점은 개발 중 종종 잊기 쉽다. 클라이언트 컴포넌트에 재사용 가능한 로직을 주입하고 싶을 때 가장 먼저 드는 생각(콜백 함수를 prop으로 넘기기)이 바로 이 아키텍처에서는 막혀 있다는 것을, 빌드 에러가 아니라 설계 시점에 미리 인지하고 있어야 반복적인 리팩터링을 줄일 수 있다.

### 참고
- Next.js Server/Client Component 경계 문서: <https://nextjs.org/docs/app/building-your-application/rendering/composition-patterns>

---

## TS-004 · Next.js 16.0.3의 critical RCE(CVSS 10) 등 취약점으로 Vercel이 배포를 차단

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | Build/Infra |
| **심각도** | Critical |
| **상태** | 해결됨 |
| **소요 시간** | 약 15분 |

### 증상
`onque-frontend`를 처음 Vercel에 배포하려 하자 배포 자체가 진행되지 않고 다음과 같은 취약점 경고로 차단됐다.

```
Vulnerable version of Next.js detected, please update immediately.
```

### 재현 조건
- 환경: `onque-frontend/package.json`의 `next` 버전 `16.0.3`
- 재현 절차: `npx vercel --prod --yes`
- 재현율: 항상

### 원인
- **표면**: Vercel이 배포 파이프라인에서 취약점 스캔에 걸려 배포를 거부.
- **근본**: Next.js 16.0.3에는 critical RCE(GHSA-9qr9-h5gf-34mp, CVSS 10) 등 다수의 알려진 취약점이 있었다. Vercel은 알려진 심각한 CVE가 있는 Next.js 버전의 배포를 자동으로 막는다.
- **확인 방법**: `npm audit`으로 `next` 패키지 관련 취약점 목록과 심각도를 직접 확인.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| 경고를 무시하고 재배포 시도 | 동일하게 차단 | Vercel 플랫폼 레벨의 하드 블록이라 애플리케이션 코드 변경 없이는 우회 불가 |

### 해결
`npm install next@16.3.0`으로 업그레이드. `npm audit` 재실행으로 `next` 관련 취약점 항목이 사라진 것을 확인(테스트/개발 의존성 관련 낮은 심각도 항목 7건은 이번 스코프 밖으로 남김).

### 검증
업그레이드 후 `npx vercel --prod --yes` 재실행 → 차단 없이 정상 배포 완료, 배포된 URL 정상 접속 확인.

### 추후 관리
- **재발 방지**: 신규 프로젝트를 `create-next-app`으로 만들 때 항상 최신 안정 버전인지 확인 후 시작하는 습관 필요.
- **모니터링**: 없음. 정기적인 `npm audit` 점검이 후속 작업으로 남음.
- **남은 리스크**: 남겨둔 7건의 낮은 심각도 취약점(개발 의존성 관련)은 아직 미해결.
- **후속 작업**: (선택) 나머지 `npm audit` 경고 정리.

### 배운 점
배포 플랫폼(Vercel)이 애플리케이션 프레임워크 자체의 CVE를 감시해 배포를 막아주는 것은 유용한 안전망이지만, 반대로 말하면 "새 프로젝트를 만들었다"는 사실만으로 최신·안전한 버전이 보장되지는 않는다는 뜻이기도 하다. 배포 전에는 습관적으로 `npm audit`을 먼저 돌려보는 게 싸다.

### 참고
- GHSA-9qr9-h5gf-34mp (Next.js RCE)

---

## TS-003 · Google이 신규 발급한 Auth key(`AQ.` 형식)가 구버전 `google-generativeai` SDK와 비호환

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | 외부API |
| **심각도** | High |
| **상태** | 해결됨 |
| **소요 시간** | 도구 호출 다수 (원인 오판 포함) |

### 증상
TS-002 보안 사고로 API 키를 재발급받아 `.env`와 Render에 반영했는데도, 배포된 백엔드가 통화 요약 요청마다 500 에러를 반환했다.

```
{"detail":"Gemini 요약 중 오류: <HttpError 400 when requesting
https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta&key=<REDACTED>
returned \"API key not valid. Please pass a valid API key.\". Details:
\"[{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'API_KEY_INVALID',
'domain': 'googleapis.com', 'metadata': {'service': 'generativelanguage.googleapis.com'}},
{'@type': 'type.googleapis.com/google.rpc.LocalizedMessage', 'locale': 'en-US',
'message': 'API key not valid. Please pass a valid API key.'}]\">"}
```

### 재현 조건
- 환경: `main.py`, `gemini_test.py`가 구버전 `google-generativeai==0.8.5` SDK(`import google.generativeai as genai`, `genai.configure()`, `genai.GenerativeModel()`) 사용, 재발급받은 키가 `AQ.`로 시작하는 신형식
- 재현 절차: `/summarize-call`에 파일 업로드
- 재현율: 항상 (새 키로는 항상, SDK를 바꾸지 않는 한)

### 원인
- **표면**: "API key not valid"라는 메시지만 보면 키 자체가 잘못됐다고 오판하기 쉬움. 실제로 처음엔 "Gemini 키는 항상 `AIzaSy...`로 시작한다"고 잘못 판단해, 사용자가 붙여넣은 키가 잘못된 곳에서 복사한 게 아니냐고 되물었다(사용자는 공식 발급 페이지 `aistudio.google.com/apikey`에서 정확히 복사했다고 확인).
- **근본**: Google이 2026년부터 신규 발급 Gemini API 키의 형식을 `AIzaSy...`(레거시 "Standard key")에서 `AQ....`(신형식 "Auth key")로 전환했다. 레거시 SDK(`google-generativeai`)는 이 신형식 키에 대한 discovery 요청(`$discovery/rest?version=v1beta`) 처리 방식이 새 키 형식과 맞지 않아 "API key not valid"를 반환한다 — 키 자체는 유효했다.
- **확인 방법**: 처음엔 "Gemini 키는 항상 AIzaSy로 시작한다"는 (틀린) 사전 지식으로 판단했다가, 웹 검색으로 Google의 2026년 키 형식 전환 공지를 확인하고 정정. 신규 SDK(`google-genai`)로 마이그레이션 후 같은 키로 정상 응답을 받아 "키는 문제없었고 SDK가 문제였다"를 최종 확인.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| 사용자에게 키를 다시 발급받거나 다른 경로로 복사했는지 확인 요청 | 사용자가 공식 페이지에서 정확히 복사했다고 확인 | 애초에 키는 문제가 아니었음 — 잘못된 가설로 시간을 소모 |

### 해결
`main.py`, `gemini_test.py`를 레거시 `google-generativeai` SDK에서 신규 공식 SDK `google-genai`(`google.genai.Client`)로 마이그레이션.

```python
# 수정 전
import google.generativeai as genai
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# 수정 후
from google import genai
client = genai.Client(api_key=GOOGLE_API_KEY)
uploaded_file = client.files.upload(file=temp_path)
response = client.models.generate_content(model="gemini-2.5-flash", contents=[uploaded_file, prompt])
```

`requirements.txt`도 `google-generativeai` → `google-genai==2.16.0`으로 교체.

### 검증
로컬 venv에 새 의존성 설치 후 실제 로컬 서버 기동 → 재발급받은 키로 `/summarize-call` 호출해 정상 요약 응답 확인. 이후 Render 재배포 후에도 동일 확인.

### 추후 관리
- **재발 방지**: 없음(SDK 마이그레이션으로 근본 해결).
- **모니터링**: 없음.
- **남은 리스크**: 없음.
- **후속 작업**: 없음.

### 배운 점
"API key not valid"라는 에러 메시지는 문자 그대로 "키가 틀렸다"만 의미하지 않는다 — 키 형식은 맞지만 그 키를 다루는 클라이언트(SDK) 쪽이 새 형식을 지원하지 못해도 같은 메시지가 나올 수 있다. 특히 "항상 이런 형식이다"라는 사전 지식은 서비스 제공자가 형식을 바꾸는 순간 바로 틀린 전제가 될 수 있으므로, 확신을 갖고 사용자를 의심하기 전에 먼저 "그 사이 서비스 쪽 사양이 바뀌지 않았는지"를 검색해봐야 한다.

### 참고
- Google Gemini API 키 형식 전환 공지 (2026년, Standard key → Auth key)
- google-genai 공식 SDK: <https://github.com/googleapis/python-genai>

---

## TS-002 · `gemini_test.py`에 하드코딩된 실제 Gemini API 키가 첫 커밋으로 공개 저장소에 노출 (보안 사고)

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | Auth/Infra |
| **심각도** | Critical |
| **상태** | 해결됨 (키 폐기·재발급 완료, git 히스토리 정리는 사용자 판단으로 보류) |
| **소요 시간** | 즉시 대응 (발견 즉시 조치) |

### 증상
OnQue 저장소를 `github.com/jjssspark/OnQue`에 처음 push한 뒤, Google이 유출된 키를 자동 탐지해 경고를 보냈다("Your API key was reported as leaked"). 원인을 추적해보니 실험 스크립트 `gemini_test.py`에 실제 Gemini API 키가 문자열로 그대로 박혀 있었고, 이 파일이 저장소의 **첫 커밋**에 포함돼 공개 저장소 히스토리에 영구히 남은 상태였다.

```python
# gemini_test.py (수정 전)
GOOGLE_API_KEY = "<REDACTED — 실제 유출된 키, 이후 폐기·재발급됨>"
```

### 재현 조건
- 환경: 로컬에만 있던 `gemini_test.py`(실험용 스크립트)를 별도 `.gitignore` 처리 없이 그대로 `git add` → 첫 커밋 → `git push`
- 재현 절차: 저장소를 처음 공개로 push하는 시점에 발생
- 재현율: 100% (커밋에 포함된 순간 확정적으로 유출)

### 원인
- **표면**: Google이 "API 키가 유출됐다"는 자동 알림을 보냄.
- **근본**: 실험 스크립트를 빠르게 작성하면서 `.env`를 거치지 않고 API 키 문자열을 코드에 직접 박아넣었고, 이후 이 프로젝트를 git 저장소로 초기화(`git init`)해 GitHub에 처음 올릴 때 이 파일을 `.gitignore`로 제외하지 않아 그대로 포함됐다.
- **확인 방법**: Google의 유출 키 자동 탐지 알림과, 코드 검토로 `gemini_test.py`에서 하드코딩된 키 문자열을 직접 확인.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| (없음 — 발견 즉시 표준 대응 절차대로 진행) | — | — |

### 해결
1. **즉시**: `gemini_test.py`를 `.env`에서 키를 읽도록 수정(하드코딩 제거).
   ```python
   # 수정 후
   from dotenv import load_dotenv
   load_dotenv()
   GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
   if not GOOGLE_API_KEY:
       raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되어 있지 않습니다.")
   ```
2. 사용자에게 `https://aistudio.google.com/apikey`에서 **키 폐기 및 재발급**을 직접 진행하도록 안내(채팅에 새 키를 붙여넣지 말 것을 명시적으로 요청).
3. 사용자가 재발급한 새 키를 로컬 `.env`와 Render 환경변수에 반영(값은 한 번도 채팅에 노출되지 않음).
4. git 히스토리(첫 커밋)에 남은 옛 키 문자열은 `git filter-repo` 등으로 지울 수 있다고 안내했으나, 사용자가 "지금은 보류"를 명시적으로 선택해 **미실행 상태로 남김**.

### 검증
새로 발급된 키로 로컬 서버를 기동해 정상 응답 확인(단, 이 과정에서 신형식 키와 구버전 SDK 비호환 문제가 새로 드러남 — TS-003 참고). 옛 키는 폐기됐으므로 설령 히스토리에 남아 있어도 더 이상 유효하지 않음을 확인.

### 추후 관리
- **재발 방지**: `env-config.md` 규약(비밀값은 코드에 절대 넣지 않는다, `.env.example`만 커밋)을 이후 모든 신규 스크립트에 적용. 이번 사고로 배운 점을 계기로 `.env.example` 파일을 프로젝트에 새로 추가.
- **모니터링**: Google API 키 유출 자동 탐지에 의존(이번에 실제로 작동함을 확인).
- **남은 리스크**: git 히스토리 첫 커밋에는 여전히 폐기된 옛 키 문자열이 남아 있다. 키 자체는 무효화됐으므로 직접적 악용 위험은 없지만, 저장소를 보는 사람에게 "한때 실수가 있었다"는 흔적은 남아 있다.
- **후속 작업**: 사용자가 원하면 `git filter-repo` + force push로 히스토리에서 완전히 제거 가능 — 명시적 요청 시에만 진행하기로 합의.

### 배운 점
공개 저장소에 처음 `push`하는 순간은 "실험용으로 대충 쓴 코드"가 전부 영구 기록으로 남는 시점이다. 실험 스크립트라도 API 키를 다루는 코드는 프로덕션 코드와 동일한 기준(`.env` 경유)으로 작성해야 하며, 특히 **첫 커밋**은 나중에 지우기 훨씬 번거로우므로(히스토리 재작성 필요) `git init` 직후 `.gitignore`부터 작성하고 `git status`로 무엇이 포함되는지 반드시 확인한 뒤에 첫 커밋을 만들어야 한다.

### 참고
- `env-config.md` "유출 대응" 절차: 키 즉시 폐기·재발급 → 새 키 반영 → 그 다음 히스토리 정리

---

## TS-001 · `requirements.txt`에 무관한 패키지 63개가 그대로 남아있어 Render pip 설치가 `ResolutionImpossible`로 실패

| | |
|---|---|
| **날짜** | 2026-08-04 |
| **영역** | Infra/Build |
| **심각도** | High |
| **상태** | 해결됨 |
| **소요 시간** | 약 20분 |

### 증상
Render에 백엔드를 처음 배포하자 빌드 단계에서 실패했다. 사용자가 보고한 에러:

```
ERROR: ResolutionImpossible: for help visit
https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
```

### 재현 조건
- 환경: `requirements.txt`가 로컬 개발 환경에서 `pip freeze`로 그대로 뽑아낸 63개 패키지 목록 (Flask, moviepy, openai, imageio 등 이 프로젝트와 무관한 패키지 다수 포함)
- 재현 절차: Render Blueprint(`render.yaml`)의 `buildCommand: pip install -r requirements.txt` 실행
- 재현율: 항상

### 원인
- **표면**: pip가 의존성 조합을 풀 수 없다고 보고.
- **근본**: `requirements.txt`가 이 프로젝트(`main.py`)가 실제로 import하는 패키지만 담은 게 아니라, 로컬 개발 환경 전체의 `pip freeze` 결과를 그대로 옮겨 담고 있었다. 서로 다른 프로젝트에서 쓰던 무관한 패키지 63개가 뒤섞이면서 그 중 일부의 버전 요구사항이 서로 충돌해, Render의 격리된 빌드 환경에서 pip가 전체 조합을 만족하는 설치 계획을 찾지 못했다.
- **확인 방법**: `grep -E "^(import|from) " main.py`로 실제 import하는 최상위 패키지를 확인 → `fastapi`, `uvicorn`, `dotenv`, `google.generativeai`(당시), `multipart` 5개뿐임을 확인. `requirements.txt`의 63개 항목과 명백히 불일치.

### 시도했지만 안 된 것
| 시도 | 결과 | 왜 안 됐는가 |
|---|---|---|
| 에러 메시지의 pip 공식 문서 링크만 참고해 개별 패키지 버전을 조정 | 비효율적, 근본 해결 아님 | 애초에 이 프로젝트에 필요 없는 패키지들끼리의 충돌이라, 버전을 조정하는 것보다 무관한 패키지를 빼는 게 맞는 방향이었음 |

### 해결
`main.py`의 실제 import 목록만 기준으로 `requirements.txt`를 5개 패키지로 정리.

```
# 수정 전: pip freeze 결과 63개 패키지 (Flask, moviepy, openai, imageio 등 포함)
# 수정 후:
fastapi==0.121.2
uvicorn==0.38.0
python-dotenv==1.2.1
google-generativeai==0.8.5   # 이후 TS-003에서 google-genai로 교체
python-multipart==0.0.20
```

로컬 스크래치 디렉터리에 빈 venv를 새로 만들어 `pip install -r requirements.txt`가 깨끗하게 성공하는지 push 전에 먼저 검증.

### 검증
Render 재배포 트리거 → 빌드 로그에서 `ResolutionImpossible` 없이 설치 성공, 서비스가 정상 기동해 헬스체크(`/`) 응답 확인.

### 추후 관리
- **재발 방지**: 의존성 파일은 항상 "실제 import 기준"으로 유지 — 이후 SQLAlchemy/psycopg 등을 추가할 때도 이 원칙을 유지해 필요한 패키지만 추가함(TS-009 관련).
- **모니터링**: 없음.
- **남은 리스크**: 없음.
- **후속 작업**: 없음.

### 배운 점
`pip freeze > requirements.txt`는 "지금 이 가상환경에 뭐가 깔려 있는가"의 스냅샷일 뿐, "이 프로젝트가 실제로 필요로 하는 것"과는 다르다. 여러 프로젝트를 같은 로컬 환경(또는 같은 가상환경)에서 작업하고 있었다면 특히, 배포 전에는 항상 소스 코드의 import 문을 기준으로 의존성 목록을 다시 좁혀야 한다. 격리된 빌드 환경(Render, CI 등)은 로컬처럼 "어쩌다 보니 되는" 상태를 봐주지 않는다.

### 참고
- pip 의존성 해결 문서: <https://pip.pypa.io/en/latest/topics/dependency-resolution/>
