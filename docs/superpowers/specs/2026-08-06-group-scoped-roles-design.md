# 그룹별 권한·계정 설계 (A묶음)

> 접수 원문: `docs/requirements/2026-08-06-기획자-요구-접수.md`
> 대상 항목: R-1(초대), R-2(관리자/멤버 구분), R-4(프로필 탭)

## 목표

역할을 사용자 전역 속성에서 **그룹 소속 속성**으로 옮긴다. 한 사람이 A팀에서는 관리자,
B팀에서는 멤버일 수 있어야 한다.

## 왜 지금인가 — 확인한 사실

`routers/auth.py:55`가 `role="admin" if is_first_user else "member"`다.
**DB 전체에서 가장 먼저 가입한 한 명만** admin이 된다. 그룹 생성은 admin만 가능하므로
(`routers/groups.py:79`), 두 번째로 가입한 사람은 팀을 만들 수도, 초대를 받을 수도 없다.

운영 DB 실측 (2026-08-06):

```
groups:            (3, '기본 그룹', created_by=2)
group_memberships: (user_id=2, group_id=3)
users:             (2, test@naver.com, admin) / (3, nm2321@naver.com, member)
announcements:     0행
```

user 3은 어느 그룹에도 속해 있지 않다.

### R-1은 독립 항목이 아니다

기획자의 "초대 기능이 있어? 안 보이는데"는 기능 부재가 아니다.
이메일 초대·대기 목록·초대 취소는 백엔드(`routers/groups.py:202-330`)와
프론트(`app/groups/page.tsx`)에 모두 구현되어 있고 사이드바에 "그룹 관리" 링크도 있다.

보이지 않은 이유는 `app/groups/page.tsx:189`다.

```
아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 표시됩니다.
```

소속 그룹이 0개면 초대 UI가 렌더링되지 않는다. 기획자 계정은 member이므로 그룹을 만들 수 없고,
초대해 줄 사람도 없다. **R-1은 R-2의 증상이다.** R-2를 고치면 함께 사라진다.

---

## 설계

### 1. 역할을 멤버십으로 이동

```python
class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "group_id"),
        CheckConstraint(f"role IN {GROUP_ROLES}", name="ck_group_memberships_role"),
    )

    user_id: Mapped[int]
    group_id: Mapped[int]
    role: Mapped[str]          # 신규
    created_at: Mapped[datetime]
```

```python
GROUP_ROLES = ("admin", "member")
```

`User.role` 컬럼은 **남기되 어떤 코드도 읽지 않는다.** 응답 직렬화에서도 뺀다.
배포된 구코드가 SELECT에 그 컬럼을 포함하므로 DROP은 신코드 안정화 후 별도 작업으로 한다.
(TS-016 — 배포 중 스키마 불일치로 테이블 전체 쿼리가 죽은 사례)

### 2. 권한 판정 집중

신규 `permissions.py`:

```python
def require_group_member(db, user, group_id) -> GroupMembership
def require_group_admin(db, user, group_id) -> GroupMembership
```

없거나 권한이 모자라면 `HTTPException(403, detail={"code": ..., "message": ...})`.
기존 에러 코드(`GROUP_ACCESS_FORBIDDEN`, `GROUP_INVITE_FORBIDDEN` 등)는 그대로 유지한다 —
프론트가 `code`로 분기하므로 코드 변경은 깨는 변경이다.

교체 대상 16곳:

| 파일 | 지점 |
|---|---|
| `routers/groups.py` | 7곳 — 생성/조회/멤버추가/멤버제거/초대/초대목록/초대취소 |
| `main.py` | 5곳 — 문서 삭제, 일정 생성·수정·삭제, 채팅방 삭제, 방 멤버 강퇴 |
| `routers/announcements.py` | 1곳 — 공지 작성 |
| `routers/users.py` | 1곳 — 삭제 예정 (§6) |

**nullable group_id 구멍**: `Document.group_id`(`models.py:154`)와
`Schedule.group_id`(`models.py:128`)는 nullable이다. group_id가 NULL인 자료는
관리자 대리 삭제 대상에서 제외하고 **작성자만** 삭제할 수 있다.
어느 그룹의 관리자가 권한을 갖는지 정의되지 않기 때문이다.

### 3. 그룹 생성 개방

- `POST /api/v1/groups`에서 `_require_admin` 제거. 인증된 사용자면 누구나 생성.
- 생성과 **같은 트랜잭션에서** 생성자를 `role="admin"` 멤버십으로 삽입한다.
  분리하면 멤버십 없는 고아 그룹이 남는다.
- `routers/auth.py`의 `is_first_user` 분기 제거.

### 4. 전사 공지 → 팀 공지

```python
class Announcement(Base):
    group_id: Mapped[int]      # 신규, NOT NULL
```

현재 0행이므로 백필이 없다.

- `GET /api/v1/announcements` — 내 소속 그룹의 공지만. `group_id` 쿼리 파라미터 필수.
- `POST /api/v1/announcements` — 해당 그룹의 admin만.
- 프론트 사이드바 라벨 "전사 공지" → "팀 공지".

`group_id`를 필수로 만드는 것은 **깨는 변경**이다. 지금 프론트는 파라미터 없이 호출한다.
백엔드와 프론트를 같은 배포에 함께 올린다. 공지가 0행이고 사용자가 2명이므로
버전 분리 없이 한 번에 바꾸는 편이 싸다.

### 5. 프로필 (R-4)

| 엔드포인트 | 동작 |
|---|---|
| `GET /api/v1/me` | 이름·이메일·가입일 + 소속 팀 목록과 각 팀에서의 역할 |
| `PATCH /api/v1/me` | 이름 변경 |
| `POST /api/v1/me/password` | 현재 비밀번호 확인 후 변경 |

`GET /api/v1/me` 응답:

```jsonc
{
  "success": true,
  "data": {
    "id": 2,
    "email": "test@naver.com",
    "name": "관리자",
    "created_at": "2026-07-31T07:12:00Z",
    "groups": [ { "id": 3, "name": "기본 그룹", "role": "admin" } ]
  },
  "error": null
}
```

비밀번호 변경은 현재 비밀번호를 반드시 검증한다. 토큰만으로 바꿀 수 있으면
탈취된 토큰이 계정 탈취로 직결된다.

프로필 사진은 범위 밖. 업로드 저장소가 선행돼야 하고, Render 무료 티어는
디스크가 재기동마다 초기화된다.

### 6. `GET /users` 삭제

전체 사용자 목록을 반환하지만 호출하는 화면이 없다 (`lib/api.ts:341`에 헬퍼만 존재).
그룹별 권한 구조에서는 다른 조직 사용자의 이메일이 노출되는 구멍이다.
엔드포인트, 프론트 헬퍼, 관련 테스트를 함께 제거한다.
멤버 목록은 `GET /api/v1/groups/{id}/members`가 이미 제공한다.

### 7. 프론트엔드

- **막다른 길 제거** — 소속 그룹 0개일 때 `app/groups/page.tsx:189`의 안내문 대신
  **팀 만들기 폼**을 렌더한다. 기획자가 겪은 문제의 직접적 수정.
- 사이드바에 프로필 탭 추가.
- 관리자 전용 조작(초대·내보내기·공지 작성)은 해당 그룹에서 `role === "admin"`일 때만 렌더.
  단, **서버 검사가 정본이다.** 화면 숨김은 편의일 뿐 권한 경계가 아니다.
- 이모지를 아이콘으로 쓰지 않는다.

### 8. 마이그레이션

`scripts/migrate_group_roles.py` — `_column_exists`(information_schema) 기반 멱등 실행.

```
1. group_memberships.role 추가 (server_default 'member')
2. 각 그룹의 created_by에 해당하는 멤버십을 'admin'으로 UPDATE
   → (user_id=2, group_id=3) 이 admin
3. announcements.group_id 추가 (NOT NULL)
```

2단계는 1단계에서 컬럼을 **방금 추가한 경우에만** 실행한다 (재실행 시 수동 변경 덮어쓰기 방지).

**마이그레이션 먼저, 배포 나중.** 컬럼 추가는 구코드에 무해하다.
반대 순서면 신코드가 없는 컬럼을 읽어 `group_memberships`·`announcements`를 건드리는
모든 쿼리가 죽는다.

3단계는 announcements가 0행일 때만 안전하다. 실행 시점에 0행인지 확인하고,
아니면 중단한다.

---

## 권한 표 (확정)

| 동작 | 관리자 | 멤버 |
|---|---|---|
| 그룹 생성 (생성자가 관리자가 됨) | O | O |
| 멤버 초대 / 내보내기 | O | X |
| 팀 공지 작성 | O | X |
| 남의 문서·일정 삭제 | O | X |
| 남의 채팅방 삭제 / 방 멤버 강퇴 | O | X |
| 문서·통화 업로드, 요약 조회 | O | O |
| 본인이 올린 것 수정·삭제 | O | O |
| 약속 확정·기각 | O | O |
| 채팅방 개설 | O | O |
| 내 프로필 조회·수정 | O | O |

"남의 문서·일정 삭제"는 그 자료에 `group_id`가 있을 때만 성립한다.
`group_id`가 NULL인 자료는 작성자만 삭제한다 (§2 참조).

---

## 검증 기준

전 과정이 이어져야 완료다.

1. 새 사용자가 가입한다 → 팀 만들기 화면이 보인다 (빈 화면이 아니다)
2. 팀을 만든다 → 그 팀에서 admin이 된다
3. 아직 가입하지 않은 이메일을 초대한다 → 대기 초대 목록에 뜬다
4. 그 이메일로 가입한다 → 자동 합류하고 role은 member다
5. 합류한 멤버가 초대를 시도한다 → 403 `GROUP_INVITE_FORBIDDEN`
6. 합류한 멤버가 공지 작성을 시도한다 → 403
7. 관리자가 공지를 쓴다 → 그 팀 멤버에게만 보인다
8. 두 번째 사용자가 자기 팀을 따로 만든다 → 첫 팀 데이터가 보이지 않는다

8번이 이번 변경의 존재 이유다. 지금은 불가능하다.

---

## 범위 밖

| 항목 | 이유 |
|---|---|
| R-3 알림창 | B묶음. 약속 추적 데이터에 얹는 별개 작업 |
| R-5~R-8 회의록 | C묶음. 버전·자동분류·고유ID·폴더가 서로 얽혀 따로 못 뗌 |
| 프로필 사진 | 외부 저장소 연동 선행 필요 |
| `users.role` 컬럼 DROP | 신코드 안정화 후 별도 배포 |
| 소유권 이전 / 관리자 위임 | 요구에 없음. 관리자가 팀을 떠나는 경우는 지금도 정의되지 않음 |
