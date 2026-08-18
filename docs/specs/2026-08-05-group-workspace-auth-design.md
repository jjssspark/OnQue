# 그룹/워크스페이스 구조 + 최소 인증 설계

## 배경

OnQue는 현재 로그인 없이 전 직원이 하나의 전역 데이터(할일/일정/문서/채팅)를 공유하는
단일 워크스페이스 형태다. 목표는 이 앱을 "회사 내부에 심어두는 회사 에이전트"로
포지셔닝하는 것이고, 그 첫 단계로 Slack처럼 부서/팀 단위 그룹을 나누고 그룹별로
업무 데이터를 분리해야 한다.

이번 스펙은 4개 축(그룹 구조 / 채팅 중심 UI / 에이전틱 자동화 / 대행업체 특화 업무 모델)
중 가장 기초가 되는 **그룹/워크스페이스 구조**만 다룬다. 나머지 세 축은 이 구조 위에
후속 스펙으로 쌓는다.

범위: 단일 회사(대행사) 내부용. 여러 고객사가 각자 쓰는 멀티테넌트 SaaS가 아니다.

## 데이터 모델

### 신규 테이블

```
User
- id
- email (unique)
- password_hash
- name
- role: "admin" | "member"
- created_at

Group
- id
- name
- created_by (User.id)
- created_at

GroupMembership (다대다)
- user_id
- group_id
- created_at

Announcement (전사 공지, 그룹 무관)
- id
- title
- content
- author_id (User.id)
- created_at
```

### 기존 테이블 변경

| 테이블 | 변경 | 의미 |
|---|---|---|
| `Todo` | `group_id` 추가 (NOT NULL) | 완전히 그룹 전용 |
| `ChatMessage` | `group_id` 추가 (NOT NULL) | 완전히 그룹 전용 |
| `Schedule` | `group_id` 추가 (nullable) | NULL = 전사 일정(휴일·회의), 값 있음 = 그룹 전용. 조회 시 "내 그룹 + 전사"를 합쳐서 반환 |
| `Document` | `group_id` 추가 (nullable) + `is_template: bool` 추가 | `is_template=true`면 그룹 무관 전체 공유(템플릿 라이브러리), 아니면 그룹 전용 |

### 권한 규칙

- 그룹 생성: `admin`만
- 그룹 멤버 추가/제거: `admin`만. **관리자가 기존 유저를 직접 지정해서 그룹에 추가**한다 —
  직원이 그룹 목록을 보고 스스로 가입 신청하는 방식이 아니다
- 공지사항(`Announcement`) 작성: `admin`만 / 열람: 전원
- 한 사용자는 여러 그룹에 동시 소속될 수 있고, UI에서 그룹을 전환하며 사용
- 최초 가입자는 자동으로 `admin`. 이후 가입자는 기본 `member` (admin이 나중에 승격 가능 —
  이번 스펙에서 승격 API는 만들지 않고 DB에서 직접 처리해도 됨, YAGNI)

## 인증

- 이메일 + 비밀번호 자체 가입/로그인. 비밀번호는 bcrypt 해시로 저장
- 로그인 성공 시 JWT 발급. 이후 요청은 `Authorization: Bearer <token>` 헤더로 인증
  (쿼리 파라미터로 토큰을 받지 않는다 — `api-contract.md` 규칙)
- 그룹 컨텍스트가 필요한 요청은 `group_id`를 함께 받고, 서버는 매 요청마다
  "이 유저가 이 그룹 소속인가"를 검증한다. 검증 로직은 FastAPI dependency로 공통화

## API

### 신규 엔드포인트

```
POST   /api/v1/auth/signup                  {email, password, name} → {user, token}
POST   /api/v1/auth/login                   {email, password} → {user, token}
GET    /api/v1/me                           → 내 정보 + 소속 그룹 목록

POST   /api/v1/groups                       (admin) {name} → 그룹 생성
GET    /api/v1/groups                       → 내가 속한 그룹 목록
POST   /api/v1/groups/{id}/members          (admin) {user_id} → 멤버 추가
DELETE /api/v1/groups/{id}/members/{userId} (admin) → 멤버 제거

GET    /api/v1/announcements                → 공지 목록 (전원)
POST   /api/v1/announcements                (admin) {title, content} → 공지 작성
```

### 기존 엔드포인트 변경

`/todos`, `/schedules`, `/documents`, `/chat` 계열 전부 `group_id`를 필수 파라미터로 받고,
서버에서 소속 검증 후 해당 그룹(+전사 공유분)만 필터링해서 반환하도록 수정.

### 에러 코드

| 코드 | 상황 |
|---|---|
| `401 AUTH_TOKEN_EXPIRED` / `AUTH_TOKEN_INVALID` | 토큰 없음/만료/위조 |
| `403 GROUP_ACCESS_FORBIDDEN` | 비소속 그룹 데이터 요청 |
| `403 GROUP_CREATE_FORBIDDEN` | admin이 아닌데 그룹 생성 시도 |
| `403 GROUP_MEMBER_ADD_FORBIDDEN` | admin이 아닌데 멤버 추가/제거 시도 |
| `404 GROUP_NOT_FOUND` | 존재하지 않는 그룹 |
| `409 USER_EMAIL_DUPLICATE` | 가입 시 이메일 중복 |

## 프론트엔드 영향

- 로그인/회원가입 페이지 신규 추가
- 기존 `WorkspaceContext`를 확장 — 로그인 유저, 소속 그룹 목록, "현재 선택된 그룹" 상태 보유
- 사이드바에 그룹 전환 드롭다운 추가
- 기존 `calls`, `chat`, `history`, `documents` 페이지는 전부 "현재 선택된 그룹" 기준으로
  데이터를 불러오도록 수정 (그룹 미선택 상태 처리 포함)
- 인증 안 된 상태로 접근 시 로그인 페이지로 리다이렉트하는 라우트 가드 필요

## 테스트

- 회원가입 → 로그인 → 토큰으로 `/me` 조회 흐름
- 최초 가입자가 admin이 되는지
- admin만 그룹 생성/멤버 추가·제거 가능한지 (member가 시도하면 403)
- 그룹 간 데이터 격리: A그룹 멤버가 B그룹의 할일/채팅/일정/문서를 요청하면 403 또는 빈 결과
- `Schedule`/`Document`의 전사 공유(`group_id NULL` / `is_template=true`) 항목이
  모든 그룹에서 정상적으로 함께 조회되는지

## 이번 스펙에서 제외 (다음 축으로 미룸)

- 채팅 중심 UI 리디자인 (지금은 기존 페이지 구조 유지, group_id만 반영)
- 에이전틱 자동화 (AI가 능동적으로 할일/일정/문서를 처리하는 로직)
- 대행업체 특화 업무 모델 (클라이언트/행사/프로젝트 단위 데이터 구조)
- 관리자 승격 API, 비밀번호 재설정, 이메일 인증 등 부가 계정 관리 기능
