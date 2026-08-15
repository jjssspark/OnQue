# 프론트엔드 셸 개편 설계 — 반응형·버튼 위치·전환

작성일 2026-08-15

## 목표

OnQue 프론트엔드의 셸(내비게이션, 페이지 컨테이너, 로딩·전환 표현)을 고쳐
반응형 결함과 도달 불가능한 컨트롤을 없앤다.

화면별 디자인을 새로 하는 작업이 아니다. 여러 화면이 **같은 문제를 반복해서
겪게 만드는 구조**를 고치는 작업이다.

## 배경 — 현재 상태에서 확인된 사실

코드 스캔으로 확인한 것만 적는다. 추측은 포함하지 않는다.

### 반응형

- 반응형 클래스(`sm:`/`md:`/`lg:`/`xl:`)가 앱 전체에 49개다. 13개 화면 중 9개는 0개다.
  `/calls`, `/documents`, `/announcements`, `/profile`, `/login`, `/signup`이 여기 속한다.
- 7개 인증 화면이 `mx-auto max-w-* px-6 py-10`을 각자 복사해 갖고 있다.
  `px-6 py-10`은 모든 폭에서 고정이다. 320px 화면에서 좌우 여백이 48px을 차지한다.
- `max-w`만 화면마다 다르다: `3xl`(calls, documents, chat, announcements),
  `4xl`(history, groups, profile), `6xl`(dashboard).
- `components/dashboard/SummaryColumn.tsx:18`이 좁은 화면에서 `grid-cols-2`,
  넓은 화면에서 `lg:grid-cols-1`이다. 방향이 뒤집혀 있다.

### 내비게이션

- `Sidebar.tsx`의 `NAV_ITEMS`는 8개(프로필 포함), `MobileNav.tsx`의 `NAV_ITEMS`는
  7개다. 두 배열이 따로 선언돼 있다.
- 그 결과 **768px 미만에서 `/profile`에 도달할 방법이 없다.** 로그아웃 버튼도
  사이드바 바닥에만 있어 마찬가지로 도달 불가다.
- 같은 항목의 이름이 어긋나 있다: `/announcements`가 사이드바에서는 "팀 공지",
  모바일에서는 "전사 공지"다. `/documents`는 "문서·회의록 요약" vs "문서·회의록"이다.

### 숨은 컨트롤

hover에서만 나타나는 컨트롤 3개가 있다.

| 위치 | 키보드 도달 | 터치 도달 |
|---|---|---|
| `app/chat/page.tsx:228` | 가능 (`focus-visible:opacity-100`) | **불가** |
| `components/SmartDashboardPanel.tsx:159` (할 일 삭제) | **불가** | **불가** |
| `components/SmartDashboardPanel.tsx:187` (일정 삭제) | **불가** | **불가** |

`app/globals.css`의 `.card-actions` 규칙(157~192행)은 이 문제를 이미 세 갈래로
모두 해결해 두었다 — `:focus-within`, `@media (pointer: coarse)`,
`@media (prefers-reduced-motion: reduce)`. 위 3곳이 그 처리를 못 받고 있다.

### 로딩과 전환

- `app/**/loading.tsx`가 하나도 없다. 그러나 **이것은 이 앱의 문제가 아니다.**
  인증 화면 7개 중 `/calls`, `/documents`를 제외한 5개가 `'use client'`이고,
  나머지 2개도 서버 데이터를 가져오지 않는다. 라우트 전환은 이미 즉시 완료된다.
  `loading.tsx`를 넣어도 사실상 보이지 않는다.
- 실제 지연은 전환 이후의 클라이언트 fetch에서 온다. 백엔드가 Render 무료 티어라
  콜드 스타트가 실측 32~54초다.
- 그 동안 화면은 `불러오는 중...`이라는 맨 글자를 보여준다. 이 문자열이 9곳에
  흩어져 있다 (`announcements:103`, `chat:160`, `history:102`, `ClientPanel:86`,
  `CommitmentPanel:143`, `ChatWindow:208`, `SmartDashboardPanel:139`,
  `RoomMembers:91`, `PriorityStream:27`).
  최종 레이아웃과 모양이 달라, 데이터가 도착하는 순간 화면이 튄다.

## 설계

### 1. 내비게이션 단일 출처

`lib/navigation.ts`를 만들어 `NAV_ITEMS`를 한 번만 선언한다.
`Sidebar.tsx`와 `MobileNav.tsx`가 이 배열을 읽는다.

```ts
export type NavItem = {
  href: string;
  label: string;
  shortLabel: string;   // 모바일 칩용. CSS로 줄이지 않고 명시한다
  description: string;  // 사이드바 2행 설명
  icon: ReactNode;
};

export const NAV_ITEMS: NavItem[] = [ /* 아래 표 7개 */ ];
```

`label`·`description`·`icon`은 현재 `Sidebar.tsx`의 값을 그대로 옮긴다
(사이드바 쪽이 정본). `shortLabel`은 신규이며, 모바일 칩이 짧아야 하는
2개만 축약하고 나머지는 `label`과 같게 둔다.

| href | label (Sidebar 현재값) | shortLabel |
|---|---|---|
| `/dashboard` | 대시보드 | 대시보드 |
| `/calls` | 통화 요약 | 통화 요약 |
| `/documents` | 문서·회의록 요약 | 문서·회의록 |
| `/chat` | 팀 채팅 | 팀 채팅 |
| `/history` | 이력 조회 | 이력 조회 |
| `/announcements` | 팀 공지 | 팀 공지 |
| `/groups` | 그룹 관리 | 그룹 관리 |

`MobileNav.tsx`의 현재 "전사 공지"는 **버린다.** 사이드바의 "팀 공지"가
맞는 이름이다 — 이 앱의 공지는 그룹 단위이지 전사 단위가 아니다
(`routers/announcements.py:40,44`가 `Announcement.group_id`로 필터하고
`require_group_member`로 접근을 막는다).

`/profile`은 이 배열에 넣지 않는다. 프로필과 로그아웃은 내용 메뉴가 아니라
**계정 동작**이다. 두 셸 모두에서 계정 동작을 별도 자리에 둔다.

- 사이드바: 현재대로 바닥 영역 (이미 이름과 로그아웃이 있다)
- 모바일: 헤더 우측에 계정 버튼. 누르면 프로필 이동과 로그아웃을 제공한다

메뉴 이름의 단일 출처는 `NAV_ITEMS`다. 사이드바가 쓰는 긴 이름
("문서·회의록 요약")을 `label`로, 모바일 칩이 쓰는 짧은 이름을 `shortLabel`로
둔다. 두 곳에서 각자 문자열을 적는 방식으로 돌아가지 않는다.

**해결되는 결함**: 모바일에서 프로필·로그아웃 도달 불가, 메뉴 이름 불일치.

### 2. `PageShell`

`components/PageShell.tsx`를 만든다.

```ts
type Props = {
  eyebrow: string;              // "Call Summary"
  title: string;                // "통화 요약"
  description?: string;
  width?: 'narrow' | 'default' | 'wide';
  actions?: ReactNode;          // 헤더 우측 버튼 자리
  children: ReactNode;
};
```

- 여백: `px-4 sm:px-6 py-6 sm:py-10`
- 폭: `narrow` = `max-w-3xl`, `default` = `max-w-4xl`, `wide` = `max-w-6xl`.
  **새로 정하는 값이 아니라 현재 쓰이는 값에 이름을 붙인 것이다.**
- 기본값은 `width="default"`
- `actions`는 헤더 우측에 배치하고, 좁은 폭에서는 제목 아래로 내린다
  (`flex-wrap`)

적용 대상 8개 화면과 각각의 `width`:

| 화면 | width | 현재 max-width |
|---|---|---|
| `/calls` | narrow | `max-w-3xl` |
| `/documents` | narrow | `max-w-3xl` |
| `/chat` | narrow | `max-w-3xl` |
| `/announcements` | narrow | `max-w-3xl` |
| `/history` | default | `max-w-4xl` |
| `/groups` | default | `max-w-4xl` |
| `/profile` | default | `max-w-4xl` |
| `/dashboard` | wide | `max-w-6xl` |

`/login`, `/signup`, `/`는 `AuthLayout`을 쓰는 별개 셸이므로 대상이 아니다.

**해결되는 결함**: 반응형 여백을 8군데 대신 1군데에서 고침. 페이지 헤더 버튼
위치가 화면마다 달라지는 것.

### 3. 로딩과 전환

세 가지를 각각 다른 이유로 넣는다.

**3-1. 스켈레톤 (가장 큰 효과)**

`components/ui/Skeleton.tsx`를 만들고, 위에 나열한 9곳의 `불러오는 중...`을
최종 레이아웃과 같은 골격의 스켈레톤으로 바꾼다.

- 스켈레톤의 목적은 "기다리는 중"을 알리는 것이 아니라 **도착할 내용의 모양을
  미리 자리잡아 레이아웃 이동을 없애는 것**이다. 따라서 각 사용처의 스켈레톤은
  그 자리의 실제 콘텐츠와 같은 높이·개수여야 한다.
- 맥동 애니메이션은 `opacity`만 쓴다.
- `prefers-reduced-motion`에서는 `globals.css`의 기존 전역 규칙(117~125행)이
  애니메이션을 멈춘다. 별도 처리가 필요 없다.

**3-2. 페이지 진입 모션**

`PageShell`에 짧은 진입 애니메이션을 넣는다. 전환이 즉시라서 오히려 화면이
바뀐 것을 인지하기 어렵다. `globals.css`의 기존 `summary-in` 키프레임과 같은
성격(`opacity` + `translateY`)으로 통일한다.

**3-3. `useLinkStatus` 힌트**

Next 16의 `useLinkStatus`(`next/link`)로 내비게이션 링크에 pending 표시를 넣는다.

**이 항목의 효과는 작다.** 라우트 전환이 이미 즉시라, 해당 라우트의 JS 청크가
아직 안 받아진 첫 클릭에서만 pending이 관측된다. 100ms 지연 후에만 나타나도록
`animation-delay`와 `opacity: 0` 시작으로 디바운스해서, 빠른 전환에서는 절대
보이지 않게 한다. 비용이 거의 없어 넣는 것이지 주된 개선이 아니다.

### 4. 숨은 컨트롤 노출

`globals.css`에 `.hover-reveal` 클래스를 추가한다. `.card-actions`가 이미
검증한 세 갈래 처리를 그대로 따르되, `max-height`가 아니라 `opacity`만 다룬다.

```css
.hover-reveal { opacity: 0; transition: opacity 0.2s; }
.group:hover .hover-reveal,
.group:focus-within .hover-reveal { opacity: 1; }

@media (pointer: coarse) { .hover-reveal { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .hover-reveal { opacity: 1; } }
```

적용 대상 3곳:
- `app/chat/page.tsx:228`
- `components/SmartDashboardPanel.tsx:159`
- `components/SmartDashboardPanel.tsx:187`

각 대상에서 기존의 `opacity-0 group-hover:opacity-100`(및 chat의
`focus-visible:opacity-100`)을 제거하고 `.hover-reveal`로 교체한다. 부모에
`group`이 있는지 확인한다 — 세 곳 모두 현재 있다.

**새 규칙을 발명하지 않는다.** 이미 코드에 있고 주석으로 근거까지 남아 있는
해법을 재사용한다.

### 5. 화면별 잔여 반응형

1~4를 마친 뒤, 320 / 375 / 768 / 1024 / 1440px에서 8개 화면을 실제로 열어
남은 문제를 찾고 고친다.

**이 단계의 대상 목록을 지금 작성하지 않는다.** `PageShell`이 여백과 최대폭을
바꾸면 무엇이 깨지는지도 달라진다. 지금 적은 목록은 절반이 틀린 목록이 된다.
`SummaryColumn.tsx:18`의 뒤집힌 그리드는 이 단계에서 다룬다.

## 범위 밖

명시적으로 하지 않는 것:

- 색·타이포·간격 토큰 변경. `globals.css`의 디자인 토큰은 그대로 둔다
- 화면별 정보 구조 재설계
- `/login`, `/signup`, `/`(랜딩)의 `AuthLayout` 셸
- API 응답 봉투 통일, `shared-types` 도입, `apps/` 모노레포 이동
  (`CLAUDE.md`의 목표 구조에 있으나 이 작업과 독립적이다)
- 백엔드 코드

## 검증

이 작업은 대부분 시각적이라 단위 테스트로 잡히는 것이 적다. 로직이 있는 곳에만
테스트를 붙이고, 나머지는 육안 검증을 명시적 절차로 둔다.

**자동 테스트를 붙이는 곳**

- `lib/navigation.ts` — `NAV_ITEMS`의 `href`가 `app/` 아래 실제 라우트와
  일치하는지. 이 테스트가 있으면 메뉴 추가 시 오타로 죽은 링크가 생기지 않는다
- 기존 `lib/priority.test.ts`가 계속 통과하는지 (회귀 확인)

**육안 검증 — 각 항목이 통과해야 완료**

1. 375px 폭에서 계정 버튼을 눌러 `/profile`로 이동하고, 로그아웃이 동작한다
2. 320 / 768 / 1024 / 1440px에서 8개 인증 화면 모두 가로 스크롤이 없다
3. 백엔드를 정지한 상태로 각 화면에 진입하면, 스켈레톤이 실제 콘텐츠와 같은
   자리·같은 높이로 뜬다 (데이터 도착 시 화면이 튀지 않는다)
4. 키보드 Tab만으로 숨은 삭제 버튼 3개에 모두 도달할 수 있다
5. 터치 에뮬레이션(`pointer: coarse`)에서 같은 3개가 처음부터 보인다
6. 사이드바와 모바일 내비의 메뉴 이름이 같다 (`shortLabel`이 `label`의 축약형
   이외의 다른 표현이 아니다)

## 파일 구조

**신규**

```
lib/navigation.ts               NAV_ITEMS 단일 출처
lib/navigation.test.ts          href ↔ 라우트 일치 검증
components/PageShell.tsx        페이지 컨테이너 + 헤더
components/ui/Skeleton.tsx      로딩 골격 프리미티브
```

**수정**

```
components/Sidebar.tsx          NAV_ITEMS 제거, lib/navigation에서 import
components/MobileNav.tsx        동일 + 계정 버튼 추가
components/SmartDashboardPanel.tsx  hover-reveal 적용(2곳), 스켈레톤
app/globals.css                 .hover-reveal, 진입 키프레임
app/{calls,documents,chat,announcements,history,groups,profile,dashboard}/page.tsx
                                PageShell로 교체
app/chat/page.tsx               위에 더해 hover-reveal, 스켈레톤
app/{announcements,history}/page.tsx  위에 더해 스켈레톤
components/{ClientPanel,CommitmentPanel,ChatWindow,RoomMembers}.tsx  스켈레톤
components/dashboard/PriorityStream.tsx  스켈레톤
components/dashboard/SummaryColumn.tsx   그리드 방향 (5단계)
```

## 주의

- `onque-frontend/AGENTS.md`가 이 Next.js는 기존 지식과 다르니
  `node_modules/next/dist/docs/`를 먼저 읽으라고 명시한다. `useLinkStatus`를
  쓰기 전 `01-app/01-getting-started/04-linking-and-navigating.md`와
  `useLinkStatus` API 문서를 확인한다.
- `AuthGuard.tsx:62-78`의 주석이 `lg:h-screen` 결정의 근거(TS-029)와 그것을
  `lg` 미만으로 내리면 안 되는 이유를 기록하고 있다. 셸 높이 구조를 건드리지
  않는다.
- `onque-frontend/`는 루트와 **별개의 git 저장소**다. 커밋 위치를 확인한다.
