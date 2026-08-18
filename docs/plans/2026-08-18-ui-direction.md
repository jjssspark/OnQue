# UI 방향 재설정 구현 계획


**Goal:** 어두운 Next.js 스타터 기본값을 벗고 푸른 라이트 기조로 갈아입히면서, 대시보드를 지표 카드형에서 목록·상세 두 단 처리형으로 바꾼다.

**Architecture:** `globals.css`의 CSS 변수 한 곳에서 색을 바꾸고, 공용 컴포넌트 다섯 개가 그 토큰만 쓰게 만든 다음, 화면들이 하드코딩 색을 버리고 컴포넌트로 수렴하게 한다. 대시보드는 기존 `buildPriorityStream`이 만드는 통합 목록을 그대로 쓰되, 옆에 상세 패널을 붙이고 지표 카드를 필터 버튼으로 흡수한다. 판정 로직(필터, 상세에 무엇이 있는가)은 `lib/`의 순수 함수로 빼서 vitest로 고정한다.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind v4 (`@theme inline`), TypeScript, vitest, next/font/google

**Spec:** `docs/specs/2026-08-18-ui-direction-design.md`

## Global Constraints

- 기능 추가·변경 금지. API도 데이터도 그대로 둔다. 백엔드 파일을 열지 않는다
- 다크 모드 만들지 않는다. 라이트만
- `Todo`에는 근거 원문이 없다. 할 일 상세에 근거를 그리려 하지 않는다
- eslint 에러 기준선 5건. 이번 작업에서 늘리지 않는다
- vitest는 `lib/**`만 돈다. 컴포넌트 테스트 인프라를 새로 깔지 않는다
- 색은 반드시 토큰을 거친다. tsx에 `#`로 시작하는 색값이나 `text-white` / `bg-white` / `text-red-*` / `text-emerald-*` 같은 Tailwind 팔레트 클래스를 새로 쓰지 않는다
- 애니메이션은 `transform` / `opacity`만 건드린다. `globals.css`에 이미 있는 예외(`.card-actions`의 `max-height`)는 그대로 둔다
- 커밋 메시지는 한국어. `<type>: <설명>` 형식

**토큰 값 (스펙에서 그대로 옮김)**

| 토큰 | 값 | 쓰임 |
|---|---|---|
| `--paper` | `#DFE5EE` | 화면 바탕 |
| `--card` | `#F7F9FC` | 목록이 놓이는 면 |
| `--card-2` | `#FFFFFF` | 상세 패널 등 읽는 면 |
| `--navy` | `#16294A` | 왼쪽 메뉴 |
| `--navy-2` | `#1E3760` | 메뉴 안 선과 눌린 상태 |
| `--ink` | `#14202F` | 본문 |
| `--ink-2` | `#4A5A70` | 보조 |
| `--ink-3` | `#78879C` | 라벨과 날짜 |
| `--rule` | `#CFD8E5` | 가는 선 |
| `--rule-strong` | `#B3C0D2` | 구역을 나누는 선 |
| `--blue` | `#1B4FA8` | 링크, 지금 위치, 주 버튼 |
| `--blue-deep` | `#12376F` | 눌린 상태와 글자 위 파랑 |
| `--blue-wash` | `#DCE6F6` | 고른 행의 배경 |
| `--late` | `#A32017` | 기한 지남 |
| `--late-wash` | `#F7E3E0` | 그 배경 |
| `--soon` | `#8A5A00` | 오늘내일 마감 |
| `--soon-wash` | `#F7EDD8` | 그 배경 |

---

## 파일 구조

| 파일 | 상태 | 책임 |
|---|---|---|
| `app/globals.css` | 수정 | 토큰 정의 한 곳. 색은 여기서만 태어난다 |
| `app/layout.tsx` | 수정 | 글꼴 로딩 |
| `components/ui/Button.tsx` | 수정 | 버튼 한 종류. 새 토큰 |
| `components/ui/Surface.tsx` | 수정 | 면 세 단계(card / sunken / raised) |
| `components/ui/StatusChip.tsx` | 수정 | 상태 표시 칩 |
| `components/ui/Skeleton.tsx` | 수정 | 로딩 자리 |
| `components/ui/BudgetNotice.tsx` | 수정 | 한도 소진 안내 |
| `lib/priority.ts` | 수정 | `PriorityItem`에 상세용 필드 추가 |
| `lib/priority.test.ts` | 수정 | 위 필드 테스트 |
| `lib/dashboard-filter.ts` | 신규 | 필터 판정과 개수 세기. 순수 함수 |
| `lib/dashboard-filter.test.ts` | 신규 | 위 테스트 |
| `components/dashboard/FilterBar.tsx` | 신규 | 필터 버튼 줄. 숫자를 품는다 |
| `components/dashboard/DetailPanel.tsx` | 신규 | 오른쪽 패널. 고른 항목 상세 또는 오늘 개요 |
| `components/dashboard/TodayOverview.tsx` | 신규 | 아무것도 안 골랐을 때의 오른쪽 |
| `components/dashboard/BudgetGauge.tsx` | 신규 | AI 사용량 20칸 눈금 |
| `components/dashboard/PriorityStream.tsx` | 수정 | 선택 상태를 받는다 |
| `components/dashboard/SummaryColumn.tsx` | 삭제 | 지표 카드가 사라지면서 역할이 없어진다 |
| `lib/metrics.ts` | 삭제 검토 | `SummaryColumn`만 쓰면 같이 지운다 |
| `app/dashboard/page.tsx` | 수정 | 두 단 조립 |

---

### Task 1: 토큰과 글꼴을 갈아끼운다

이 작업의 첫 단추다. 여기서 정한 이름을 나머지 전부가 참조한다.

**Files:**
- Modify: `app/globals.css:3-64`
- Modify: `app/layout.tsx:1-38`

**Interfaces:**
- Consumes: 없음
- Produces: Tailwind 클래스로 쓸 수 있는 토큰 이름 — `bg-paper` `bg-card` `bg-card-2` `bg-navy` `bg-navy-2` `text-ink` `text-ink-2` `text-ink-3` `border-rule` `border-rule-strong` `text-blue` `bg-blue` `text-blue-deep` `bg-blue-wash` `text-late` `bg-late-wash` `text-soon` `bg-soon-wash`. 글꼴 변수 `--font-sans` `--font-mono`

- [ ] **Step 1: next/font 문서에서 한글 글꼴 로딩 방법을 확인한다**

`onque-frontend/AGENTS.md`가 이 Next.js는 학습 데이터와 다를 수 있으니 문서를 먼저 읽으라고 명시한다. 확인할 것은 하나다 — `IBM_Plex_Sans_KR`처럼 `subsets` 목록에 한글이 없는 글꼴을 어떻게 넣는가.

```bash
cd onque-frontend
ls node_modules/next/dist/docs/
grep -rn "preload" node_modules/next/dist/docs/ | grep -i font | head -20
```

기대: `subsets`를 못 주는 경우 `preload: false`로 전체 subset을 포함시킨다는 내용. 문서가 다른 방법을 말하면 그쪽을 따른다.

- [ ] **Step 2: `app/layout.tsx`의 글꼴을 바꾼다**

```tsx
import type { Metadata } from "next";
import { IBM_Plex_Sans_KR, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { WorkspaceProvider } from "@/components/WorkspaceContext";
import { AuthProvider } from "@/components/AuthContext";
import { AuthGuard } from "@/components/AuthGuard";

// IBM Plex Sans KR은 가변 글꼴이 아니라 weight를 명시해야 한다.
// preload를 끄는 이유는 한글이 next/font의 subsets 목록에 없어서다 —
// subsets: ['latin']만 주면 한글 글리프가 빠져 fallback으로 떨어진다.
const plexSans = IBM_Plex_Sans_KR({
  weight: ["400", "500", "600", "700"],
  preload: false,
  variable: "--font-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "OnQue Workspace",
  description: "Gemini 기반 업무 자동화 워크스페이스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className={`${plexSans.variable} ${plexMono.variable} antialiased`}>
        <AuthProvider>
          <WorkspaceProvider>
            <AuthGuard>{children}</AuthGuard>
          </WorkspaceProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 3: `app/globals.css`의 `:root`와 `@theme inline`을 통째로 바꾼다**

3행부터 64행까지를 아래로 교체한다. 그 아래 keyframes와 `.card-actions` 등은 건드리지 않는다.

```css
:root {
  /* 바탕이 무채색이 아니라 파랑이 섞여 있다. 파랑이 포인트가 아니라 기조가
     되게 하려면 종이 자체가 파랑 쪽이어야 한다. */
  --paper: #dfe5ee;
  --card: #f7f9fc;
  --card-2: #ffffff;

  --navy: #16294a;
  --navy-2: #1e3760;

  /* 글자 3등급. --ink는 --card 위에서 13:1, --ink-3도 4.6:1을 넘긴다. */
  --ink: #14202f;
  --ink-2: #4a5a70;
  --ink-3: #78879c;

  --rule: #cfd8e5;
  --rule-strong: #b3c0d2;

  --blue: #1b4fa8;
  --blue-deep: #12376f;
  --blue-wash: #dce6f6;

  /* 상태색. 색만으로 구분하지 않고 항상 글자를 함께 쓴다.
     임박을 노랑이 아니라 어두운 갈색으로 내린 것은 노랑 계열이 밝은 바탕에서
     대비가 안 나오기 때문이다. */
  --late: #a32017;
  --late-wash: #f7e3e0;
  --soon: #8a5a00;
  --soon-wash: #f7edd8;
}

@theme inline {
  --color-paper: var(--paper);
  --color-card: var(--card);
  --color-card-2: var(--card-2);
  --color-navy: var(--navy);
  --color-navy-2: var(--navy-2);
  --color-ink: var(--ink);
  --color-ink-2: var(--ink-2);
  --color-ink-3: var(--ink-3);
  --color-rule: var(--rule);
  --color-rule-strong: var(--rule-strong);
  --color-blue: var(--blue);
  --color-blue-deep: var(--blue-deep);
  --color-blue-wash: var(--blue-wash);
  --color-late: var(--late);
  --color-late-wash: var(--late-wash);
  --color-soon: var(--soon);
  --color-soon-wash: var(--soon-wash);
  --font-sans: var(--font-sans);
  --font-mono: var(--font-mono);
}

body {
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-sans), system-ui, sans-serif;
}
```

옛 이름(`--background` `--surface` `--brand` `--foreground` `--fg-muted` `--fg-dim` `--hairline` `--border` `--accent` `--late-bg` `--late-fg` `--soon-bg` `--soon-fg` `--sidebar`)을 남기지 않는다. 남기면 어느 화면이 옛 토큰을 쓰고 있는지 빌드가 안 알려준다. 지금 깨뜨려야 Task 9에서 전부 잡힌다.

- [ ] **Step 4: 얼마나 깨졌는지 센다**

```bash
cd onque-frontend && npx tsc --noEmit 2>&1 | tail -5
npx next build 2>&1 | tail -30
```

기대: 빌드가 통과할 수도, Tailwind가 모르는 클래스라며 넘어갈 수도 있다. Tailwind v4는 정의 안 된 유틸리티 클래스를 조용히 무시하므로 **빌드 통과가 안전을 뜻하지 않는다.** 실제 피해량은 아래로 센다.

```bash
grep -rnoE "(bg|text|border|ring|from|to)-(background|surface|surface-sunken|surface-hover|brand|brand-foreground|foreground|fg-muted|fg-dim|fg-disabled|hairline|border|accent|sidebar|sidebar-foreground|late-bg|late-fg|soon-bg|soon-fg)\b" app components | wc -l
```

이 숫자를 커밋 메시지에 적는다. Task 9의 목표는 이 숫자를 0으로 만드는 것이다.

- [ ] **Step 5: 한글이 실제로 Plex로 나오는지 눈으로 본다**

```bash
cd onque-frontend && npm run dev
```

브라우저에서 `http://localhost:3000/login`을 연다. 개발자 도구 Elements에서 한글이 있는 요소를 고르고 Computed 탭의 `font-family` 실제 적용값을 확인한다.

기대: `__IBM_Plex_Sans_KR_...` 형태의 클래스가 적용되어 있다. `system-ui`나 `sans-serif`로 떨어졌으면 Step 1의 문서 확인 결과대로 로딩 방식을 고친다.

- [ ] **Step 6: 커밋**

```bash
git add app/globals.css app/layout.tsx
git commit -m "style: 토큰을 푸른 라이트 기조로, 글꼴을 IBM Plex로 교체"
```

---

### Task 2: 공용 컴포넌트 다섯 개를 새 토큰으로 맞춘다

화면들이 수렴할 목적지를 먼저 만든다. 이게 있어야 Task 9에서 하드코딩 색을 "무엇으로" 바꿀지가 정해진다.

**Files:**
- Modify: `components/ui/Button.tsx`
- Modify: `components/ui/Surface.tsx`
- Modify: `components/ui/StatusChip.tsx`
- Modify: `components/ui/Skeleton.tsx`
- Modify: `components/ui/BudgetNotice.tsx`

**Interfaces:**
- Consumes: Task 1의 토큰 클래스
- Produces:
  - `buttonClasses(variant?: 'primary' | 'ghost' | 'danger', size?: 'sm' | 'md'): string`
  - `<Surface level="card" | "sunken" | "raised" tone="default" | "late" className>`
  - `<StatusChip tone="late" | "soon" | "neutral" | "unconfirmed">`
  - `<Skeleton className>`, `<SkeletonList rows rowClassName className label>` (시그니처 그대로)
  - `<BudgetNotice id hint>` (시그니처 그대로)

- [ ] **Step 1: 지금 시그니처를 확인한다**

```bash
cd onque-frontend
cat components/ui/Button.tsx components/ui/Surface.tsx components/ui/StatusChip.tsx
grep -rn "buttonClasses\|<Surface\|<StatusChip" app components | wc -l
```

호출부 개수를 적어둔다. 시그니처를 바꾸면 그만큼 고쳐야 한다. **기본값이 있는 prop만 늘리고, 기존 prop의 이름과 의미는 바꾸지 않는다.** 그래야 호출부를 안 건드린다.

- [ ] **Step 2: `Button.tsx`를 새 토큰으로 고친다**

핵심 교체:

```tsx
// primary
'bg-blue text-card-2 hover:bg-blue-deep active:bg-blue-deep'
// ghost
'bg-transparent text-ink-2 hover:bg-blue-wash hover:text-blue-deep'
// danger
'bg-late-wash text-late hover:bg-late hover:text-card-2'
// 공통 포커스 — 링 오프셋 바탕이 어두운 배경에서 종이색으로 바뀐다
'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper'
```

`rounded-2xl`을 `rounded-md`로 내린다. 스위스 실무 기조에서 큰 라운드는 어긋난다. 스펙의 안티 템플릿 항목이 `rounded-lg everywhere`를 지목한다.

- [ ] **Step 3: `Surface.tsx`를 고치고 `raised`를 추가한다**

지금 `level`은 `'card' | 'sunken'` 둘이다. 상세 패널이 목록보다 한 단 위로 올라와야 해서 `'raised'`를 더한다.

```tsx
type SurfaceProps = {
  level?: 'card' | 'sunken' | 'raised';
  tone?: 'default' | 'late';
  className?: string;
  children: React.ReactNode;
};

const LEVEL: Record<NonNullable<SurfaceProps['level']>, string> = {
  // 목록이 놓이는 기본 면
  card: 'bg-card border border-rule',
  // 바탕보다 가라앉은 면. 보조 정보용
  sunken: 'bg-paper border border-rule',
  // 읽는 면. 흰색이라 본문 대비가 가장 세다
  raised: 'bg-card-2 border border-rule-strong',
};

// 기한 지난 것은 색만이 아니라 왼쪽 굵은 선으로도 알린다.
// 색각 이상에서도 구분되게 하려면 색 하나로는 부족하다.
const TONE: Record<NonNullable<SurfaceProps['tone']>, string> = {
  default: '',
  late: 'border-l-2 border-l-late bg-late-wash',
};

export function Surface({ level = 'card', tone = 'default', className = '', children }: SurfaceProps) {
  return <div className={`rounded-md ${LEVEL[level]} ${TONE[tone]} ${className}`}>{children}</div>;
}
```

지금 `tone="late"`에 박혀 있는 `linear-gradient(101deg,#241318 0%,#12151f 58%)`를 지운다. 어두운 배경 전제의 값이라 종이색 위에서 검은 덩어리가 된다.

- [ ] **Step 4: `StatusChip.tsx`에 `unconfirmed`를 더한다**

상세 패널이 "아직 확정 안 됨"을 표시해야 한다.

```tsx
const TONE = {
  late: 'bg-late-wash text-late',
  soon: 'bg-soon-wash text-soon',
  neutral: 'bg-paper text-ink-2',
  unconfirmed: 'bg-blue-wash text-blue-deep',
};
```

`bg-white/[0.07]`처럼 흰색 투명도로 만든 배경을 전부 없앤다. 종이색 위에서는 아무것도 안 보인다.

- [ ] **Step 5: `Skeleton.tsx`와 `BudgetNotice.tsx`를 고친다**

```tsx
// Skeleton: bg-foreground/[0.07] → bg-rule
<div aria-hidden className={`animate-pulse rounded bg-rule ${className}`} />
```

```tsx
// BudgetNotice: 클래스만 교체. role="status"와 id/hint 동작은 그대로 둔다
className="rounded-md border border-rule bg-soon-wash px-4 py-3 text-xs leading-relaxed text-ink-2"
// hint 줄
className="mt-1.5 text-ink"
```

한도 소진은 에러가 아니라 "오늘 몫을 다 썼다"이므로 빨강이 아니라 임박색을 쓴다.

- [ ] **Step 6: 타입 검사와 빌드**

```bash
cd onque-frontend && npx tsc --noEmit && npx next build 2>&1 | tail -20
```

기대: 통과. `Surface`의 `level`에 새 값을 더하기만 했고 기존 값은 살아 있어서 호출부가 안 깨진다.

- [ ] **Step 7: 커밋**

```bash
git add components/ui
git commit -m "style: 공용 컴포넌트 다섯 개를 새 토큰으로 맞춤"
```

---

### Task 3: `PriorityItem`에 상세 패널이 쓸 필드를 더한다

상세 패널을 만들기 전에 데이터부터 흐르게 한다. `lib/`이라 vitest로 고정할 수 있는 몇 안 되는 지점이다.

**Files:**
- Modify: `lib/priority.ts`
- Test: `lib/priority.test.ts`

**Interfaces:**
- Consumes: `CommitmentRecord` (`evidence: string`, `client_name: string | null`, `source_type: 'call' | 'document' | 'chat'`, `status`), `Todo`
- Produces: `PriorityItem`에 세 필드 추가
  - `evidence: string | null` — 약속만 값을 가진다. 할 일은 항상 `null`
  - `clientName: string | null`
  - `sourceType: 'call' | 'document' | 'chat' | null` — 할 일은 `null`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`lib/priority.test.ts` 끝에 붙인다. 기존 테스트의 픽스처 만드는 방식을 먼저 읽고 그 형태에 맞춘다.

```ts
describe('상세 패널용 필드', () => {
  it('약속은 근거 원문과 고객, 출처를 함께 싣는다', () => {
    const commitment = makeCommitment({
      id: 1,
      content: '견적서 보내기',
      evidence: '내일까지 견적서 보내드릴게요',
      client_name: '한빛상사',
      source_type: 'chat',
    });

    const [item] = buildPriorityStream([commitment], [], '2026-08-18');

    expect(item.evidence).toBe('내일까지 견적서 보내드릴게요');
    expect(item.clientName).toBe('한빛상사');
    expect(item.sourceType).toBe('chat');
  });

  it('할 일은 근거가 없다는 것을 null로 밝힌다', () => {
    const todo = makeTodo({ id: 1, content: '자료 정리' });

    const [item] = buildPriorityStream([], [todo], '2026-08-18');

    // 빈 문자열이 아니라 null이어야 한다. ''는 "근거가 비어 있다"로 읽히고
    // null은 "근거라는 것이 애초에 없다"로 읽힌다. 상세 패널이 이 둘을
    // 다르게 그려야 한다.
    expect(item.evidence).toBeNull();
    expect(item.clientName).toBeNull();
    expect(item.sourceType).toBeNull();
  });
});
```

`makeCommitment` / `makeTodo` 헬퍼가 파일에 이미 있으면 그걸 쓰고, 없으면 기존 테스트가 객체를 만드는 방식을 그대로 따른다.

- [ ] **Step 2: 실패를 확인한다**

```bash
cd onque-frontend && npm test -- lib/priority.test.ts
```

기대: FAIL. `Property 'evidence' does not exist on type 'PriorityItem'` 또는 `expected undefined to be '내일까지...'`

여기서 통과하면 필드가 이미 있다는 뜻이다. 멈추고 왜인지 확인한다.

- [ ] **Step 3: 최소한으로 구현한다**

`lib/priority.ts`의 `PriorityItem` 타입에 더한다.

```ts
  /** 약속만 가진다. 할 일은 근거를 저장하지 않으므로 항상 null.
   *  빈 문자열과 null을 구분한다 — 전자는 "근거가 비었다", 후자는
   *  "이 종류에는 근거라는 개념이 없다"이고 화면이 다르게 그려야 한다. */
  evidence: string | null;
  clientName: string | null;
  sourceType: CommitmentRecord['source_type'] | null;
```

약속 루프에 더한다.

```ts
      evidence: c.evidence,
      clientName: c.client_name,
      sourceType: c.source_type,
```

할 일 루프에 더한다.

```ts
      evidence: null,
      clientName: null,
      sourceType: null,
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd onque-frontend && npm test
```

기대: PASS. 기존 테스트도 전부 통과. 출력에 경고가 없다.

- [ ] **Step 5: 커밋**

```bash
git add lib/priority.ts lib/priority.test.ts
git commit -m "feat: PriorityItem에 상세 패널용 근거·고객·출처 필드 추가"
```

---

### Task 4: 필터 판정을 순수 함수로 만든다

지표 카드가 없어지고 숫자가 필터 버튼으로 들어간다. "센다"와 "좁힌다"가 같은 함수를 써야 화면의 숫자와 목록이 어긋나지 않는다.

**Files:**
- Create: `lib/dashboard-filter.ts`
- Test: `lib/dashboard-filter.test.ts`

**Interfaces:**
- Consumes: `PriorityItem` (Task 3의 것)
- Produces:
  - `type FilterKey = 'all' | 'overdue' | 'today' | 'week' | 'unconfirmed'`
  - `const FILTERS: ReadonlyArray<{ key: FilterKey; label: string }>`
  - `matchesFilter(item: PriorityItem, key: FilterKey, todayKey: string): boolean`
  - `applyFilter(items: PriorityItem[], key: FilterKey, todayKey: string): PriorityItem[]`
  - `countByFilter(items: PriorityItem[], todayKey: string): Record<FilterKey, number>`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`lib/dashboard-filter.test.ts`를 만든다.

```ts
import { describe, expect, it } from 'vitest';
import { applyFilter, countByFilter, matchesFilter } from './dashboard-filter';
import type { PriorityItem } from './priority';

const TODAY = '2026-08-18';

function makeItem(over: Partial<PriorityItem>): PriorityItem {
  return {
    key: 'todo-1',
    kind: 'todo',
    id: 1,
    content: '무엇',
    dueDate: null,
    daysPastDue: null,
    isDueSoon: false,
    sourceLabel: '할 일',
    createdAt: '2026-08-18T00:00:00Z',
    isUnconfirmed: false,
    evidence: null,
    clientName: null,
    sourceType: null,
    ...over,
  };
}

describe('matchesFilter', () => {
  it('전체는 무엇이든 통과시킨다', () => {
    expect(matchesFilter(makeItem({}), 'all', TODAY)).toBe(true);
  });

  it('지남은 기한이 오늘보다 앞선 것만 고른다', () => {
    expect(matchesFilter(makeItem({ dueDate: '2026-08-17', daysPastDue: 1 }), 'overdue', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'overdue', TODAY)).toBe(false);
    expect(matchesFilter(makeItem({ dueDate: null }), 'overdue', TODAY)).toBe(false);
  });

  it('오늘은 기한이 오늘인 것만 고른다', () => {
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'today', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-19' }), 'today', TODAY)).toBe(false);
  });

  it('이번 주는 오늘부터 7일 안을 고르고 지난 것은 빼놓는다', () => {
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'week', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-25' }), 'week', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-26' }), 'week', TODAY)).toBe(false);
    // 지난 것은 '지남'이 맡는다. 여기 또 들어가면 한 항목이 두 번 세어진다.
    expect(matchesFilter(makeItem({ dueDate: '2026-08-17', daysPastDue: 1 }), 'week', TODAY)).toBe(false);
  });

  it('확인 필요는 아직 확정 안 된 약속만 고른다', () => {
    expect(matchesFilter(makeItem({ isUnconfirmed: true }), 'unconfirmed', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ isUnconfirmed: false }), 'unconfirmed', TODAY)).toBe(false);
  });
});

describe('countByFilter', () => {
  it('버튼에 붙일 숫자를 필터마다 센다', () => {
    const items = [
      makeItem({ key: 'a', dueDate: '2026-08-17', daysPastDue: 1 }),
      makeItem({ key: 'b', dueDate: TODAY }),
      makeItem({ key: 'c', dueDate: '2026-08-20', isUnconfirmed: true }),
      makeItem({ key: 'd', dueDate: null }),
    ];

    expect(countByFilter(items, TODAY)).toEqual({
      all: 4,
      overdue: 1,
      today: 1,
      week: 2,
      unconfirmed: 1,
    });
  });
});

describe('applyFilter', () => {
  it('센 숫자와 좁힌 결과의 개수가 같다', () => {
    const items = [
      makeItem({ key: 'a', dueDate: '2026-08-17', daysPastDue: 1 }),
      makeItem({ key: 'b', dueDate: TODAY }),
      makeItem({ key: 'c', dueDate: null }),
    ];
    const counts = countByFilter(items, TODAY);

    // 숫자와 목록이 다른 로직으로 만들어지면 언젠가 어긋난다.
    // 같은 판정을 쓰는지 여기서 못 박는다.
    for (const key of ['all', 'overdue', 'today', 'week', 'unconfirmed'] as const) {
      expect(applyFilter(items, key, TODAY)).toHaveLength(counts[key]);
    }
  });

  it('좁혀도 원래 순서를 흐트러뜨리지 않는다', () => {
    const items = [makeItem({ key: 'a' }), makeItem({ key: 'b' }), makeItem({ key: 'c' })];
    expect(applyFilter(items, 'all', TODAY).map((i) => i.key)).toEqual(['a', 'b', 'c']);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd onque-frontend && npm test -- lib/dashboard-filter.test.ts
```

기대: FAIL. `Failed to resolve import "./dashboard-filter"`

- [ ] **Step 3: 최소한으로 구현한다**

`lib/dashboard-filter.ts`를 만든다.

```ts
import type { PriorityItem } from './priority';

/** '이번 주'가 보는 날짜 폭. 오늘을 포함해 7일 뒤까지. */
const WEEK_WINDOW_DAYS = 7;

const MS_PER_DAY = 86_400_000;

export type FilterKey = 'all' | 'overdue' | 'today' | 'week' | 'unconfirmed';

/** 화면에 이 순서로 그린다. 급한 것부터 왼쪽. */
export const FILTERS: ReadonlyArray<{ key: FilterKey; label: string }> = [
  { key: 'all', label: '전체' },
  { key: 'overdue', label: '지남' },
  { key: 'today', label: '오늘' },
  { key: 'week', label: '이번 주' },
  { key: 'unconfirmed', label: '확인 필요' },
];

function shiftKey(dayKey: string, days: number): string {
  return new Date(Date.parse(`${dayKey}T00:00:00Z`) + days * MS_PER_DAY)
    .toISOString()
    .slice(0, 10);
}

/**
 * 항목이 이 필터에 걸리는가.
 *
 * '이번 주'가 지난 것을 빼는 이유는 '지남'과 겹치면 한 항목이 두 버튼에서
 * 세어지고, 사용자가 숫자를 더해 봤을 때 전체보다 커지기 때문이다.
 */
export function matchesFilter(item: PriorityItem, key: FilterKey, todayKey: string): boolean {
  switch (key) {
    case 'all':
      return true;
    case 'overdue':
      return item.daysPastDue !== null;
    case 'today':
      return item.dueDate === todayKey;
    case 'week':
      if (!item.dueDate) return false;
      return item.dueDate >= todayKey && item.dueDate <= shiftKey(todayKey, WEEK_WINDOW_DAYS);
    case 'unconfirmed':
      return item.isUnconfirmed;
  }
}

export function applyFilter(
  items: PriorityItem[],
  key: FilterKey,
  todayKey: string,
): PriorityItem[] {
  return items.filter((item) => matchesFilter(item, key, todayKey));
}

/** 버튼에 붙일 숫자. applyFilter와 같은 판정을 써야 화면이 어긋나지 않는다. */
export function countByFilter(
  items: PriorityItem[],
  todayKey: string,
): Record<FilterKey, number> {
  const counts = { all: 0, overdue: 0, today: 0, week: 0, unconfirmed: 0 };
  for (const item of items) {
    for (const { key } of FILTERS) {
      if (matchesFilter(item, key, todayKey)) counts[key] += 1;
    }
  }
  return counts;
}
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd onque-frontend && npm test
```

기대: PASS 전부. `week` 경계 테스트(`2026-08-25` 통과, `2026-08-26` 탈락)가 특히 통과해야 한다.

- [ ] **Step 5: 커밋**

```bash
git add lib/dashboard-filter.ts lib/dashboard-filter.test.ts
git commit -m "feat: 대시보드 필터 판정과 개수 세기를 순수 함수로 분리"
```

---

### Task 5: 필터 바를 만든다

**Files:**
- Create: `components/dashboard/FilterBar.tsx`

**Interfaces:**
- Consumes: `FILTERS`, `FilterKey` (Task 4)
- Produces: `<FilterBar counts value onChange />`

- [ ] **Step 1: 컴포넌트를 만든다**

```tsx
'use client';

import { FILTERS, type FilterKey } from '@/lib/dashboard-filter';

type Props = {
  counts: Record<FilterKey, number>;
  value: FilterKey;
  onChange: (key: FilterKey) => void;
};

/**
 * 지표 카드를 대신하는 필터 줄.
 *
 * 카드 네 장으로 숫자를 보여주고 목록을 따로 두면, 숫자를 보고 나서 그 숫자에
 * 해당하는 것을 목록에서 다시 찾아야 한다. 세는 일과 좁히는 일을 한 자리에
 * 합치면 그 왕복이 없어진다.
 *
 * role="tablist"를 쓰지 않은 이유: 탭은 패널을 갈아끼우지만 여기는 같은 목록을
 * 좁힐 뿐이다. 대신 aria-pressed로 눌린 상태를 알린다.
 */
export function FilterBar({ counts, value, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="목록 좁히기">
      {FILTERS.map(({ key, label }) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={`flex items-baseline gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper ${
              active
                ? 'border-blue bg-blue text-card-2'
                : 'border-rule bg-card text-ink-2 hover:border-rule-strong hover:text-ink'
            }`}
          >
            <span>{label}</span>
            {/* 숫자는 mono. 버튼 폭이 숫자 자릿수에 따라 덜 흔들린다 */}
            <span
              className={`font-mono text-[11px] tabular-nums ${
                active ? 'text-card-2/80' : 'text-ink-3'
              }`}
            >
              {counts[key]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: 타입 검사**

```bash
cd onque-frontend && npx tsc --noEmit
```

기대: 통과.

- [ ] **Step 3: 커밋**

```bash
git add components/dashboard/FilterBar.tsx
git commit -m "feat: 지표 카드를 대신할 필터 바 추가"
```

---

### Task 6: AI 사용량 눈금을 만든다

**Files:**
- Create: `components/dashboard/BudgetGauge.tsx`

**Interfaces:**
- Consumes: `useWorkspace()`의 `aiBudget`, `formatResetTime` (`lib/sweep-status`)
- Produces: `<BudgetGauge />` — 인자 없음. 스스로 컨텍스트에서 읽는다

- [ ] **Step 1: `AiBudget` 타입에 실제로 어떤 필드가 있는지 확인한다**

```bash
cd onque-frontend && grep -n "AiBudget" -A 12 lib/api.ts | head -25
```

`used` `total` `resets_at` 말고 스윕 몫을 구분할 필드가 있는지 본다. 없으면 Step 2에서 자동 정리 몫을 옅게 칠하는 부분을 뺀다. **없는 값을 그리려 하지 않는다.** 필드명이 다르면 실제 이름으로 아래 코드를 고친다.

- [ ] **Step 2: 컴포넌트를 만든다**

```tsx
'use client';

import { useWorkspace } from '@/components/WorkspaceContext';
import { formatResetTime } from '@/lib/sweep-status';

/**
 * 오늘 쓴 AI 호출을 칸으로 그린다.
 *
 * "3/20" 숫자만 보여주면 얼마나 남았는지가 머리로 계산해야 알 수 있다.
 * 칸으로 그리면 남은 양이 눈에 바로 들어온다. 하루 20건이라 칸이 스무 개를
 * 넘지 않아 이 방식이 성립한다.
 */
export function BudgetGauge() {
  const { aiBudget } = useWorkspace();

  // null은 "아직 모른다"이지 "0을 썼다"가 아니다. 0칸을 그리면 잔량이 가득한
  // 것처럼 보여 실제와 어긋난다.
  if (!aiBudget) return null;

  const { used, total, resets_at } = aiBudget;
  const resetsAt = formatResetTime(resets_at);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">AI 사용량</p>
        <p className="font-mono text-[11px] tabular-nums text-ink-2">
          {used} / {total}
        </p>
      </div>

      <div
        className="mt-2 flex gap-[3px]"
        role="img"
        aria-label={`오늘 AI 호출 ${total}건 중 ${used}건 사용`}
      >
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-4 flex-1 rounded-[2px] ${i < used ? 'bg-blue' : 'bg-rule'}`}
          />
        ))}
      </div>

      {resetsAt && <p className="mt-1.5 text-[10px] text-ink-3">{resetsAt}에 초기화</p>}
    </div>
  );
}
```

- [ ] **Step 3: 타입 검사**

```bash
cd onque-frontend && npx tsc --noEmit
```

기대: 통과.

- [ ] **Step 4: 커밋**

```bash
git add components/dashboard/BudgetGauge.tsx
git commit -m "feat: AI 사용량을 숫자 대신 칸 눈금으로 표시"
```

---

### Task 7: 상세 패널과 오늘 개요를 만든다

두 단 구성의 오른쪽이다. 이 작업의 핵심 가치인 근거 원문이 여기 들어간다.

**Files:**
- Create: `components/dashboard/TodayOverview.tsx`
- Create: `components/dashboard/DetailPanel.tsx`

**Interfaces:**
- Consumes: `PriorityItem` (Task 3), `Surface` / `StatusChip` / `buttonClasses` (Task 2), `BudgetGauge` (Task 6), `ScheduleItem` · `DocumentRecord` (`lib/api`)
- Produces:
  - `<TodayOverview schedules documents />`
  - `<DetailPanel item schedules documents onCompleteTodo />` — `item`이 `null`이면 `TodayOverview`를 그린다

- [ ] **Step 1: `DocumentRecord`의 실제 필드명을 확인한다**

```bash
cd onque-frontend && grep -n "DocumentRecord" -A 12 lib/api.ts | head -20
```

아래 코드가 쓰는 `id`와 `title`이 실제 이름과 맞는지 본다. 다르면 실제 이름으로 고친다.

- [ ] **Step 2: `TodayOverview.tsx`를 만든다**

```tsx
'use client';

import Link from 'next/link';
import { BudgetGauge } from '@/components/dashboard/BudgetGauge';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';

type Props = {
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
};

/**
 * 아무것도 안 골랐을 때의 오른쪽.
 *
 * 빈 패널로 두지 않는 이유는 화면 절반이 노는 것이기 때문이고, 별도 탭으로
 * 빼지 않는 이유는 하루에 한 번 볼까 말까 한 자리가 되기 때문이다.
 */
export function TodayOverview({ schedules, documents }: Props) {
  return (
    <div className="space-y-6 p-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">
          다가오는 일정
        </p>
        {schedules.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">7일 안에 예정된 일정이 없습니다.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {schedules.map((schedule) => (
              <li key={schedule.id} className="flex items-baseline justify-between gap-3">
                <span className="truncate text-xs text-ink-2">{schedule.title}</span>
                <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-3">
                  {schedule.scheduled_date.slice(5)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-rule pt-5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">최근 요약</p>
        {documents.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">아직 만든 요약이 없습니다.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {documents.slice(0, 5).map((doc) => (
              <li key={doc.id}>
                <Link
                  href="/history"
                  className="block truncate text-xs text-ink-2 hover:text-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-card-2"
                >
                  {doc.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-rule pt-5">
        <BudgetGauge />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: `DetailPanel.tsx`를 만든다**

```tsx
'use client';

import { StatusChip } from '@/components/ui/StatusChip';
import { buttonClasses } from '@/components/ui/Button';
import { TodayOverview } from '@/components/dashboard/TodayOverview';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';
import type { PriorityItem } from '@/lib/priority';

const SOURCE_TEXT: Record<NonNullable<PriorityItem['sourceType']>, string> = {
  call: '통화 기록에서 뽑음',
  document: '문서에서 뽑음',
  chat: '채팅에서 뽑음',
};

type Props = {
  item: PriorityItem | null;
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
  onCompleteTodo: (id: number) => void;
};

export function DetailPanel({ item, schedules, documents, onCompleteTodo }: Props) {
  if (!item) return <TodayOverview schedules={schedules} documents={documents} />;

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusChip tone="neutral">{item.sourceLabel}</StatusChip>
        {item.daysPastDue !== null && (
          <StatusChip tone="late">{item.daysPastDue}일 지남</StatusChip>
        )}
        {item.daysPastDue === null && item.isDueSoon && <StatusChip tone="soon">임박</StatusChip>}
        {item.isUnconfirmed && <StatusChip tone="unconfirmed">확인 필요</StatusChip>}
      </div>

      <h2 className="mt-3 text-lg font-semibold leading-snug text-ink">{item.content}</h2>

      <dl className="mt-4 space-y-2 border-t border-rule pt-4 text-xs">
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-ink-3">기한</dt>
          <dd className="font-mono tabular-nums text-ink-2">{item.dueDate ?? '없음'}</dd>
        </div>
        {item.clientName && (
          <div className="flex gap-3">
            <dt className="w-16 shrink-0 text-ink-3">고객</dt>
            <dd className="text-ink-2">{item.clientName}</dd>
          </div>
        )}
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-ink-3">등록</dt>
          <dd className="font-mono tabular-nums text-ink-2">{item.createdAt.slice(0, 10)}</dd>
        </div>
      </dl>

      {/* 근거는 약속만 가진다. evidence가 null이면 그 종류에 근거라는 개념이
          아예 없다는 뜻이라 빈 상자를 그리지 않고 왜 없는지를 밝힌다. */}
      {item.evidence !== null ? (
        <div className="mt-5 border-t border-rule pt-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">
            {item.sourceType ? SOURCE_TEXT[item.sourceType] : '근거'}
          </p>
          <blockquote className="mt-2 border-l-2 border-blue bg-blue-wash px-3 py-2.5 text-xs leading-relaxed text-ink">
            {item.evidence || '근거 문장이 비어 있습니다.'}
          </blockquote>
        </div>
      ) : (
        <p className="mt-5 border-t border-rule pt-4 text-[11px] leading-relaxed text-ink-3">
          이 할 일은 어느 대화에서 나왔는지 기록이 남아 있지 않습니다.
        </p>
      )}

      {item.kind === 'todo' && (
        <button
          type="button"
          onClick={() => onCompleteTodo(item.id)}
          className={`mt-5 ${buttonClasses('primary', 'sm')}`}
        >
          완료로 표시
        </button>
      )}
    </div>
  );
}
```

`StatusChip`이 children이 아니라 `label` prop을 받는 형태면 Task 2 Step 1에서 확인한 실제 시그니처에 맞춘다. `buttonClasses`의 인자 순서도 마찬가지다.

- [ ] **Step 4: 타입 검사와 빌드**

```bash
cd onque-frontend && npx tsc --noEmit && npx next build 2>&1 | tail -20
```

기대: 통과.

- [ ] **Step 5: 커밋**

```bash
git add components/dashboard/DetailPanel.tsx components/dashboard/TodayOverview.tsx
git commit -m "feat: 상세 패널과 오늘 개요 추가. 약속은 근거 원문을 함께 보여줌"
```

---

### Task 8: 대시보드를 두 단으로 조립한다

**Files:**
- Modify: `components/dashboard/PriorityStream.tsx`
- Modify: `app/dashboard/page.tsx:186-272`
- Delete: `components/dashboard/SummaryColumn.tsx`
- Delete 검토: `lib/metrics.ts`

**Interfaces:**
- Consumes: `FilterBar` (5), `DetailPanel` (7), `applyFilter` · `countByFilter` · `FilterKey` (4), `buildPriorityStream` (3), `Surface` (2)
- Produces: 없음. 마지막 소비자다

- [ ] **Step 1: `PriorityStream`이 선택을 받게 고친다**

지금 props에 두 개를 더한다. 기존 `items` `isLoading` `onCompleteTodo`는 그대로 둔다.

```tsx
type Props = {
  items: PriorityItem[];
  isLoading: boolean;
  onCompleteTodo: (id: number) => void;
  /** 지금 고른 항목의 key. 아무것도 안 골랐으면 null */
  selectedKey: string | null;
  onSelect: (item: PriorityItem) => void;
};
```

행을 `<button type="button">`으로 감싸 클릭과 키보드 양쪽으로 고를 수 있게 한다. `<div onClick>`으로 만들면 Tab으로 닿지 않는다.

```tsx
<button
  type="button"
  onClick={() => onSelect(item)}
  aria-current={item.key === selectedKey ? 'true' : undefined}
  className={`w-full border-l-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue ${
    item.key === selectedKey
      ? 'border-l-blue bg-blue-wash'
      : 'border-l-transparent hover:bg-paper'
  }`}
>
```

목록 안의 "완료" 버튼이 남아 있으면 지운다. 버튼 안에 버튼은 못 넣는다 — 완료는 상세 패널로 옮겼다. `onCompleteTodo` prop은 다른 데서 쓰지 않으면 함께 지운다.

- [ ] **Step 2: `app/dashboard/page.tsx`를 고친다**

지우는 것:
- `metrics` 배열 (186-191행)
- `SummaryColumn` import와 사용
- `Metric` 타입 import
- `dueTodayCount` / `overdueCount` useMemo — 필터가 대신 센다
- `openTodos` useMemo — 위 두 개에만 쓰였으면 같이 지운다

더하는 것. 파일 상단 상수:

```tsx
const ZERO_COUNTS: Record<FilterKey, number> = {
  all: 0,
  overdue: 0,
  today: 0,
  week: 0,
  unconfirmed: 0,
};
```

컴포넌트 안:

```tsx
const [filter, setFilter] = useState<FilterKey>('all');
const [selectedKey, setSelectedKey] = useState<string | null>(null);

// slice(0, 8)을 뺀다. 두 단 구성에서는 목록이 세로로 스크롤되므로 자를 이유가
// 없고, 자르면 필터 버튼의 숫자와 실제 보이는 개수가 어긋난다.
const priorityStream = useMemo(() => {
  if (!todayKey) return [];
  return buildPriorityStream(commitments, todos, todayKey);
}, [commitments, todos, todayKey]);

const counts = useMemo(
  () => (todayKey ? countByFilter(priorityStream, todayKey) : ZERO_COUNTS),
  [priorityStream, todayKey],
);

const visibleItems = useMemo(
  () => (todayKey ? applyFilter(priorityStream, filter, todayKey) : []),
  [priorityStream, filter, todayKey],
);

// 고른 항목이 필터에 걸려 사라졌거나 완료 처리로 목록에서 빠지면 상세는
// 없는 것을 계속 보여준다. 목록에서 찾아 없으면 오늘 개요로 되돌린다.
const selectedItem = useMemo(
  () => visibleItems.find((i) => i.key === selectedKey) ?? null,
  [visibleItems, selectedKey],
);
```

본문 레이아웃:

```tsx
<div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
  <div className="min-w-0">
    <FilterBar counts={counts} value={filter} onChange={setFilter} />
    <Surface level="card" className="mt-3 overflow-hidden">
      <PriorityStream
        items={visibleItems}
        isLoading={isPriorityStreamLoading}
        selectedKey={selectedKey}
        onSelect={(item) => setSelectedKey(item.key)}
      />
    </Surface>
    {commitmentsTruncated && (
      <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
        오래된 약속 일부가 이 목록에 없습니다. 확인 필요에서 전체를 볼 수 있습니다.
      </p>
    )}
  </div>

  {/* 좁은 화면에서는 상세가 목록 아래로 내려간다. 두 단을 억지로 유지하면
      둘 다 못 읽을 폭이 된다. */}
  <Surface level="raised" className="self-start lg:sticky lg:top-6">
    <DetailPanel
      item={selectedItem}
      schedules={upcomingSchedules}
      documents={documents}
      onCompleteTodo={(id) => toggleTodo(id, true)}
    />
  </Surface>
</div>
```

에러 배너의 색도 이때 같이 고친다.

```tsx
className="mt-5 rounded-md border border-late/40 bg-late-wash px-4 py-3 text-sm text-late"
```

`MODULES` 링크 카드와 `CommitmentPanel`, `ClientPanel` 부분은 색만 토큰으로 바꾸고 구조는 그대로 둔다. `bg-surface` → `bg-card`, `bg-surface-hover` → `bg-blue-wash`, `text-foreground` → `text-ink`, `text-fg-dim` → `text-ink-3`, `ring-brand` → `ring-blue`, `ring-offset-background` → `ring-offset-paper`.

- [ ] **Step 3: `SummaryColumn`을 지운다**

```bash
cd onque-frontend
grep -rn "SummaryColumn" app components lib
```

기대: 아무것도 안 나온다. 나오면 그곳부터 정리한다.

```bash
rm components/dashboard/SummaryColumn.tsx
grep -rn "lib/metrics\|from './metrics'\|Metric\b" app components lib
```

`lib/metrics.ts`를 참조하는 곳이 없으면 함께 지운다. 남아 있으면 두고, 무엇이 쓰는지 커밋 메시지에 적는다.

- [ ] **Step 4: 타입 검사, 테스트, 빌드**

```bash
cd onque-frontend && npx tsc --noEmit && npm test && npx next build 2>&1 | tail -20
```

기대: 전부 통과.

- [ ] **Step 5: 눈으로 확인한다**

```bash
cd onque-frontend && npm run dev
```

`http://localhost:3000/dashboard`에서 확인할 것:

1. 필터 버튼 다섯 개가 보이고 각각 숫자가 붙어 있다
2. '지남'을 누르면 목록이 줄고, 줄어든 개수가 버튼의 숫자와 같다
3. 목록 행을 클릭하면 오른쪽이 그 항목 상세로 바뀌고, 고른 행에 파란 배경과 왼쪽 선이 생긴다
4. 약속을 고르면 근거 원문이 인용 상자로 나온다
5. 할 일을 고르면 "기록이 남아 있지 않습니다" 문장이 나온다 (빈 상자가 아니라)
6. 아무것도 안 고른 처음 상태에서 오른쪽에 다가오는 일정·최근 요약·AI 눈금이 보인다
7. Tab만으로 필터 → 목록 행 → 상세 버튼 순서로 이동되고, 지금 어디인지 파란 링으로 보인다
8. 지표 카드 네 장이 사라졌다

- [ ] **Step 6: 커밋**

```bash
git add app/dashboard components/dashboard lib
git commit -m "feat: 대시보드를 목록·상세 두 단 구성으로 교체"
```

---

### Task 9: 남은 하드코딩 색을 토큰으로 바꾼다

이 작업의 실제 분량이다. 화면이 12개고 그중 9개는 2026-08-11 개편을 안 거쳤다.

**Files:**
- Modify: `app/**/*.tsx`, `components/**/*.tsx` 중 아래 검색에 걸리는 전부

**Interfaces:**
- Consumes: Task 1의 토큰, Task 2의 공용 컴포넌트
- Produces: 없음

- [ ] **Step 1: 무엇이 얼마나 남았는지 센다**

```bash
cd onque-frontend
echo "--- 옛 토큰 ---"
grep -rnoE "(bg|text|border|ring|from|to)-(background|surface|surface-sunken|surface-hover|brand|brand-foreground|foreground|fg-muted|fg-dim|fg-disabled|hairline|border|accent|sidebar|sidebar-foreground|late-bg|late-fg|soon-bg|soon-fg)\b" app components | sed 's/.*://' | sort | uniq -c | sort -rn
echo "--- Tailwind 팔레트 직접 사용 ---"
grep -rnoE "(bg|text|border|ring|decoration|from|to)-(white|black|red|emerald|green|blue|indigo|slate|gray|zinc|neutral|amber|yellow|orange|violet|purple)-?[0-9]*" app components | sed 's/.*://' | sort | uniq -c | sort -rn
echo "--- 16진 색값 ---"
grep -rnE "#[0-9a-fA-F]{3,8}\b" app components | grep -v globals.css
echo "--- 파일별 ---"
grep -rlE "text-white|bg-white|text-red-|text-emerald-|bg-emerald-|border-emerald-|-foreground\b|-surface\b|-brand\b|-fg-" app components | sort
```

마지막 목록이 고칠 파일 목록이다. 개수를 적어둔다.

- [ ] **Step 2: 치환 규칙을 정한다**

한 번 정하고 끝까지 같은 규칙을 쓴다. 파일마다 다르게 판단하면 화면 간 불일치가 다시 생긴다.

| 옛것 | 새것 | 비고 |
|---|---|---|
| `bg-background` | `bg-paper` | |
| `bg-surface` | `bg-card` | |
| `bg-surface-sunken` | `bg-paper` | |
| `bg-surface-hover` | `bg-blue-wash` | |
| `bg-sidebar` | `bg-navy` | |
| `text-sidebar-foreground` | `text-paper` | 남색 위 글자 |
| `text-foreground` | `text-ink` | |
| `text-fg-muted` | `text-ink-2` | |
| `text-fg-dim` / `text-fg-disabled` | `text-ink-3` | |
| `text-white` | `text-card-2` | 파란·남색 면 위일 때만. 종이색 위면 `text-ink` |
| `bg-white` | `bg-card-2` | |
| `border-hairline` / `border-border` | `border-rule` | |
| `bg-brand` | `bg-blue` | |
| `text-brand` | `text-blue` | |
| `ring-brand` | `ring-blue` | |
| `ring-offset-background` | `ring-offset-paper` | 카드 위 요소는 `ring-offset-card` |
| `text-red-300` / `-400` / `-500` | `text-late` | |
| `bg-red-500/[0.08]` 류 | `bg-late-wash` | |
| `text-emerald-300` / `bg-emerald-500` / `border-emerald-400` | `text-blue` / `bg-blue` / `border-blue` | 성공·완료도 파랑으로 통일. 초록을 따로 두면 색이 하나 더 늘고 기조가 흐려진다 |
| `text-accent` / `bg-accent` | `text-soon` / `bg-soon-wash` | |
| `rounded-2xl` / `rounded-xl` | `rounded-md` | |
| `bg-white/[0.07]` 같은 흰색 투명도 | `bg-paper` | 어두운 배경 전제라 종이 위에서 안 보인다 |

**투명도가 붙은 색(`/[0.08]`, `/40`)은 기계적으로 바꾸지 않는다.** 어두운 배경 위 반투명 흰색은 밝은 배경에서 정반대로 동작한다. 하나씩 보고 불투명 토큰으로 바꾼다.

- [ ] **Step 3: 화면 하나씩 고친다**

한 번에 다 바꾸고 빌드하지 않는다. 화면 하나 고치고 → 브라우저에서 열어보고 → 다음. `sed`로 일괄 치환하면 위 표의 "면에 따라 다름" 항목이 전부 틀린다.

순서 (자주 보는 것부터):

1. `components/PageShell.tsx`, 사이드바 계열, `lib/navigation.tsx` — 모든 화면의 뼈대
2. `app/chat/**`
3. `app/login/**`, `app/signup/**` — 남색 면을 써서 첫 인상에 기조를 싣는다
4. `app/calls/**`, `app/documents/**`
5. `app/history/**`
6. `app/notices/**`, `app/groups/**`
7. `app/profile/**`
8. `components/CommitmentPanel.tsx`, `components/ClientPanel.tsx`, `components/ReceivedInvitations.tsx`

각 화면마다:

```bash
cd onque-frontend && npx tsc --noEmit
# 브라우저에서 해당 경로를 연다
```

- [ ] **Step 4: 0이 됐는지 확인한다**

```bash
cd onque-frontend
grep -rnE "text-white|bg-white|text-red-[0-9]|text-emerald-|bg-emerald-|border-emerald-|-foreground\b|-surface\b|-brand\b|-fg-(muted|dim|disabled)|border-hairline|bg-background|text-accent" app components
```

기대: 아무것도 안 나온다. 남았으면 왜 남겼는지 커밋 메시지에 적는다. 조용히 두지 않는다.

- [ ] **Step 5: 전체 검사**

```bash
cd onque-frontend && npx tsc --noEmit && npm test && npx next build 2>&1 | tail -20 && npx eslint . 2>&1 | tail -10
```

기대: 타입·테스트·빌드 통과. eslint 에러가 5건을 넘지 않는다. 넘으면 늘어난 것을 고친다.

- [ ] **Step 6: 커밋**

화면 묶음마다 나눠 커밋한다. 한 커밋에 12개 화면을 넣으면 되돌릴 때 통째로 되돌아간다.

```bash
git add components/PageShell.tsx lib/navigation.tsx
git commit -m "style: 뼈대 컴포넌트 색을 새 토큰으로 전환"
# 이하 화면 묶음마다 반복
```

---

### Task 10: 반응형과 접근성을 확인하고 마무리한다

**Files:**
- Modify: 아래 확인에서 문제가 나온 파일

**Interfaces:**
- Consumes: Task 1~9 전부
- Produces: 없음

- [ ] **Step 1: 네 폭에서 가로 스크롤이 없는지 본다**

```bash
cd onque-frontend && npm run dev
```

Chrome DevTools의 기기 툴바로 320 / 768 / 1024 / 1440에서 12개 화면을 연다. 확인할 것:

- 가로 스크롤바가 안 생긴다
- 1024 미만에서 대시보드가 한 단으로 접히고, 상세가 목록 아래로 내려간다
- 320에서 필터 버튼 다섯 개가 줄바꿈되어 잘리지 않는다
- 320에서 AI 눈금 20칸이 뭉개지지 않는다. 뭉개지면 `BudgetGauge`에 좁은 폭에서는 칸 대신 숫자만 남기는 분기를 넣는다

- [ ] **Step 2: 대비를 잰다**

DevTools의 색 선택기가 대비비를 표시한다. 잴 것:

| 조합 | 목표 |
|---|---|
| `--ink` on `--card` | 4.5:1 이상 |
| `--ink-2` on `--card` | 4.5:1 이상 |
| `--ink-3` on `--card` | 4.5:1 이상. 못 넘기면 읽어야 하는 글자에 쓰지 않는다 |
| `--late` on `--late-wash` | 4.5:1 이상 |
| `--soon` on `--soon-wash` | 4.5:1 이상 |
| `--card-2` on `--blue` | 4.5:1 이상 (주 버튼) |
| `--paper` on `--navy` | 4.5:1 이상 (메뉴 글자) |

못 넘기는 조합이 있으면 `globals.css`의 값을 조정한다. 조정하면 그 값을 스펙 표에도 반영한다.

- [ ] **Step 3: 키보드로만 훑는다**

마우스를 쓰지 않고 Tab / Shift+Tab / Enter만으로 확인:

- 로그인 → 대시보드 → 필터 → 목록 행 → 상세 → 메뉴 순으로 막히지 않고 이동된다
- 매 순간 지금 어디인지 파란 링으로 보인다. 링이 잘리는 곳(`overflow-hidden` 안)이 있으면 `ring-inset`으로 바꾼다
- 목록에서 Enter로 항목을 고를 수 있다

- [ ] **Step 4: 모션 최소화에서 확인한다**

DevTools > Rendering > Emulate CSS `prefers-reduced-motion: reduce`

- `.card-actions`와 `.hover-reveal`이 처음부터 펼쳐져 있다
- 기한 지난 점의 맥동이 멈춘다

- [ ] **Step 5: 마지막 전체 검사**

```bash
cd onque-frontend && npx tsc --noEmit && npm test && npx next build && npx eslint . 2>&1 | tail -10
```

기대: 타입 통과, 테스트 전부 PASS, 빌드 성공, eslint 에러 5건 이하.

- [ ] **Step 6: 커밋**

```bash
git add -A
git commit -m "fix: 반응형·대비·키보드 확인에서 나온 문제 정리"
```

- [ ] **Step 7: 스펙에 실제 결과를 반영한다**

Step 2에서 토큰 값을 조정했거나, Task 9에서 안 바꾸고 남긴 것이 있으면 스펙 문서에 적는다. 계획과 실제가 어긋난 채로 두지 않는다.

```bash
git add docs/specs/2026-08-18-ui-direction-design.md
git commit -m "docs: UI 개편 실제 결과를 스펙에 반영"
```

---

## 남는 것

이 계획이 안 푸는 것들이다. 끝난 뒤 별도로 다룬다.

| 항목 | 왜 여기서 안 하나 |
|---|---|
| `Todo`에 근거 컬럼 추가 | 백엔드 작업. 마이그레이션과 `_apply_extracted_actions` 수정이 필요하다. 할 일 중복 생성 문제와 같이 봐야 한다 |
| 컴포넌트 테스트 인프라 | jsdom + testing-library 도입은 그 자체가 별도 작업이다. 지금은 타입·빌드·눈으로 검증한다 |
| 다크 모드 | 토큰이 이미 갈라져 있어 나중에 값만 더하면 된다 |
| eslint 에러 5건 | 기준선. 이번 작업이 만든 게 아니다 |
