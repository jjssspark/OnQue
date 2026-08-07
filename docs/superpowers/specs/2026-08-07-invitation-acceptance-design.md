# 초대 수락 절차 설계

**날짜:** 2026-08-07
**전제:** A묶음(그룹별 권한·계정, `2026-08-06-group-scoped-roles-design.md`)이 머지·배포된 상태

## 배경

A묶음이 그룹 생성을 인증된 모든 사용자에게 열었다. 그 전에는 초대 엔드포인트가 전역 admin(가장 먼저 가입한 1명) 전용이었으므로 사실상 한 사람만 쓸 수 있었다. 지금은 누구나 팀을 하나 만들면 그 팀의 admin이 되므로, **초대 엔드포인트가 전 인증 사용자에게 열렸다.**

A묶음 최종 브랜치 리뷰가 이를 Important로 지적했다(원장 `.superpowers/sdd/2026-08-06-group-scoped-roles/progress.md`의 I-2). 플랜·스펙 어디에도 초대 수락 절차나 열거 방어가 없었고, 그룹 생성 개방의 부수효과로 처음 생긴 문제다.

## 문제

`routers/groups.py:201-261`의 `invite_to_group_by_email`이 초대 대상의 가입 여부에 따라 세 갈래로 갈린다.

| 상황 | 현재 응답 |
|---|---|
| 가입자 | 200 `{"status": "joined", "user": {id, email, name}}` + **즉시 합류** |
| 미가입자 | 200 `{"status": "pending", ...}` |
| 이미 우리 팀 멤버 | 409 `GROUP_INVITE_ALREADY_MEMBER` |

두 가지가 새고 있다.

**1. 이메일 열거 오라클.** 임의의 인증 사용자가 팀 하나를 만든 뒤 이메일을 반복 초대하면, 응답만으로 그 이메일의 가입 여부를 알아낼 수 있다. 가입자인 경우 **이름과 사용자 id까지** 응답에 실려 나가므로 단순 존재 여부보다 더 샌다.

**2. 무동의 편입.** 가입자는 본인 의사와 무관하게 그룹 멤버십과 기본 채팅방 멤버십이 생성된다(`join_group`). 상대의 `/api/v1/me` 그룹 목록과 채팅 목록에 모르는 팀이 나타난다. 미가입자도 `routers/auth.py:59-70`이 가입 시점에 자동 합류시키므로 **어느 경로로든 동의 절차가 없다.**

`GROUP_INVITE_ALREADY_MEMBER`(409)는 이 문제에 포함되지 않는다. 관리자가 `GET /groups/{id}/members`로 이미 볼 수 있는 자기 팀 정보라 새로 새는 정보가 없다. `GROUP_INVITE_ALREADY_SENT`도 같다.

## 왜 응답 문구만 바꾸면 안 되는가

응답을 `{"status": "invited"}`로 단일화하되 가입자를 계속 즉시 합류시키면, 관리자가 초대 직후 멤버 목록을 새로고침해서 그 사람이 떴는지 보면 가입 여부를 그대로 알 수 있다. **한 단계 늘어날 뿐 같은 오라클이다.**

열거를 실제로 막으려면 즉시 합류를 없애야 하고, 즉시 합류를 없애면 수락 절차가 필요해진다. 두 문제는 하나의 해법을 공유한다.

## 결정

**누구든 수락해야 팀에 들어간다.** 가입자든 미가입자든 규칙이 하나다.

가입 모델이 아직 확정되지 않았고(공개 서비스로 갈지 미정) 당분간 사내용이므로, 지금은 초대 경로만 손보고 **가입 플로우(`/auth/signup`) 자체는 건드리지 않는다.**

거절은 **`GroupInvitation` 행 삭제**로 표현한다. `declined_at` 컬럼을 추가하면 거절 이력이 남지만, 이 프로젝트는 Alembic이 없어 컬럼 추가마다 `scripts/migrate_*.py`와 "마이그레이션 먼저, 코드 나중" 배포 절차를 치러야 한다. 사내 소규모 운영에서 거절 이력의 값이 그 비용보다 작다. 관리자가 다시 초대하면 새 행이 생긴다.

## 데이터 모델

**변경 없음.** `GroupInvitation`의 기존 컬럼(`group_id`, `email`, `invited_by`, `created_at`, `accepted_at`)을 그대로 쓴다.

| 상태 | 표현 |
|---|---|
| 대기 | `accepted_at IS NULL` |
| 수락됨 | `accepted_at` 설정 + `GroupMembership` 생성 |
| 거절됨 | 행 삭제 |

**마이그레이션이 필요 없다.** 이 설계의 가장 큰 이점이며, 거절을 행 삭제로 표현하기로 한 이유이기도 하다.

## API

### 변경: `POST /api/v1/groups/{group_id}/invitations`

가입자 분기(`routers/groups.py:218-239`)를 통째로 제거한다. 누구를 초대하든 `_upsert_invitation(accepted=False)` 하나로 끝난다.

```jsonc
{"success": true, "data": {"status": "invited", "email": "<입력한 이메일>"}, "error": null}
```

`user` 객체(id·email·name)를 응답에서 제거한다. **가입 여부와 무관하게 바이트 단위로 동일한 응답**이 나가야 한다.

409 두 개는 그대로 둔다. 에러 코드 문자열 `GROUP_INVITE_ALREADY_MEMBER`·`GROUP_INVITE_ALREADY_SENT`도 바뀌지 않는다 — 프론트가 `code`로 분기하므로 코드 변경은 깨는 변경이다.

`GROUP_INVITE_ALREADY_MEMBER` 검사는 여전히 `User` 조회가 필요하다. 미가입 이메일은 멤버일 수 없으므로 그 경우 검사는 통과하고 `invited`가 나간다 — 미가입자와 "가입했지만 우리 팀 아닌 사람"의 응답이 같아야 한다는 요구를 만족한다.

### 신규: 받은 초대 (3개)

`routers/auth.py`의 `/me` 계열에 둔다. 그룹 소속이 아니라 "나"에 대한 자원이라 `permissions.py`를 쓰지 않는다.

| 메서드·경로 | 동작 |
|---|---|
| `GET /api/v1/me/invitations` | 내 이메일로 온 대기 초대 목록 |
| `POST /api/v1/me/invitations/{id}/accept` | `join_group` + `accepted_at` 기록 |
| `DELETE /api/v1/me/invitations/{id}` | 행 삭제 (거절) |

목록 응답의 각 항목: 초대 id, 그룹 id, 그룹 이름, 초대한 사람 이름, `created_at`.

**소유권 검사.** 수락·거절은 초대의 `email`이 현재 사용자 이메일과 일치하는지 먼저 확인하고, 아니면 **404 `INVITATION_NOT_FOUND`**를 낸다. 403으로 나누면 초대 id의 존재 여부가 샌다 — `permissions.py`가 그룹에서 "권한 먼저, 존재 확인 나중"으로 세운 원칙과 같다.

**이메일 비교는 양쪽 `func.lower()`로 한다.** 가입 컬럼이 대소문자를 구분해 저장하고, 기존 코드(`routers/groups.py:217`, `routers/auth.py:62`)가 이미 그렇게 하고 있다.

**이미 수락된 초대**(`accepted_at IS NOT NULL`)에 다시 수락을 호출하면 404를 낸다. 목록에 뜨지 않는 것에 대한 조작이므로 존재하지 않는 것과 같이 취급한다.

### 변경: `POST /api/v1/auth/signup`

`routers/auth.py:59-70`의 대기 초대 정산 블록을 제거한다. 초대는 대기 상태로 남고 가입자가 직접 수락한다. 응답 형태는 바뀌지 않는다.

`join_group`·`GroupInvitation` import가 이 파일에서 더 이상 쓰이지 않으면 정리한다. `GET /me/invitations`가 같은 파일에 생기므로 `GroupInvitation`은 남을 가능성이 높다.

## 프론트엔드

**받은 초대 카드**를 두 곳에 둔다. 같은 컴포넌트와 같은 API를 재사용한다.

- `app/groups/page.tsx` **최상단** — 가입 직후 도착하는 곳
- `app/profile/page.tsx` — 나중에 다시 찾아보는 곳. "소속 팀" 구역 위

각 항목: 팀 이름, 초대한 사람, `수락` / `거절` 버튼. 이모지를 쓰지 않는다. 기존 카드·버튼 클래스를 따른다.

**빈 상태 우선순위.** 받은 초대가 있으면 초대 카드가 팀 만들기 폼보다 위에 온다. 가입 직후 초대받아 온 사람에게 "팀을 만드세요"부터 보이면 잘못된 안내다.

`app/groups/page.tsx`의 `result.status === 'joined'` 분기를 제거한다 — 그런 응답이 더 이상 없다.

`lib/api.ts`에 `listMyInvitations()`, `acceptInvitation(id)`, `declineInvitation(id)`를 추가하고 `inviteToGroupByEmail`의 반환 타입을 새 응답에 맞춘다.

## 검증 기준

A묶음 검증 기준 4번이 **개정된다.**

> 기존: 그 이메일로 가입한다 → 자동 합류하고 role은 member다
> 개정: 그 이메일로 가입한다 → 대기 중인 초대가 보인다. 수락하면 합류하고 role은 member다

전 과정이 이어져야 완료다.

1. 관리자가 **가입자** 이메일을 초대한다 → 응답이 `{"status": "invited", "email": ...}`
2. 관리자가 **미가입자** 이메일을 초대한다 → **1번과 동일한 응답**
3. 초대받은 가입자의 `/api/v1/me` 그룹 목록에 그 팀이 **아직 없다**
4. 그 사용자가 `GET /me/invitations`에서 초대를 본다
5. 수락한다 → 그 팀에 `member`로 합류한다
6. 다른 초대를 거절한다 → 목록에서 사라지고 멤버가 아니다
7. 남의 초대 id로 수락을 시도한다 → 404 `INVITATION_NOT_FOUND`
8. 초대받은 이메일로 새로 가입한다 → 자동 합류하지 않고 대기 초대가 보인다

**2번이 이 변경의 존재 이유다.** 두 응답이 다르면 열거가 가능하다.

## 테스트

핵심은 **응답 동일성**이다. 가입자 초대와 미가입자 초대의 응답 본문을 직접 비교해 단언한다. 상태 코드만 비교하면 부족하다.

기존 테스트 중 자동 합류에 기대던 것들이 깨진다 — 최소한 `test_invited_member_joins_as_member_not_admin`(`tests/test_group_routes.py`), `test_member_list_returns_membership_role_not_user_role`, 공지·일정 테스트 중 초대로 멤버를 만든 것들. **수락 호출을 넣도록 고친다. 단언을 느슨하게 만들어 통과시키지 않는다.**

## 범위 밖

| 항목 | 이유 |
|---|---|
| 초대 레이트 리밋 | 공개 서비스 전환 시 필요. 사내 단계에선 과잉 |
| 초대 알림 메일 | 외부 메일 발송 연동 선행 필요 |
| 거절 이력 보관 (`declined_at`) | 마이그레이션 비용 대비 값이 작다 |
| 가입 플로우를 초대 기반으로 닫기 | 가입 모델이 미확정 |
