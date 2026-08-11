# OnQue 프론트엔드 개편 (R1) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드의 시각 위계를 밝기 3단·상태색·가로 요약 열로 다시 세우고, 그 규칙을 토큰과 공용 컴포넌트로 고정한다.

**Architecture:** `globals.css`의 CSS 커스텀 프로퍼티를 3단 표면 + 3등급 글자 + 상태색 체계로 교체한다. 각 화면에 흩어진 카드·버튼 클래스 문자열을 `components/ui/` 3개 컴포넌트로 모은다. 대시보드는 "약속과 할 일을 급한 순으로 섞은 본류 스트림"과 "숫자·일정·최근요약을 담은 오른쪽 침강면 열"로 재배치한다. 섞고 정렬하는 로직은 순수 함수(`lib/priority.ts`)로 빼서 단위 테스트한다.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind CSS 4 (`@theme inline`), TypeScript 5, Vitest(이 계획에서 신규 도입)

## Global Constraints

- 설계 근거는 `docs/superpowers/specs/2026-08-11-frontend-redesign-design.md`. 충돌하면 스펙이 우선한다.
- **백엔드를 건드리지 않는다.** API 응답 스키마 변경 금지. "며칠 지났는지"는 프론트에서 계산한다.
- **다크 단일 테마.** 라이트 테마를 추가하지 않는다.
- **이모지를 UI에 쓰지 않는다.** 아이콘은 기존 SVG path를 유지한다.
- **`--border` 토큰을 제거하지 않는다.** 대시보드 외 9개 화면이 의존 중이다. 값만 약화시킨다.
- **`--accent` 토큰을 제거하지 않는다.** `var(--soon)`의 별칭으로 남긴다.
- 읽어야 하는 글자에 `--fg-disabled`(#6f7590, 4.0:1)를 쓰지 않는다.
- 상태를 색만으로 표현하지 않는다. 항상 글자를 함께 넣는다.
- 애니메이션은 `transform` / `opacity` / `background-color`만. 레이아웃 속성을 애니메이션하지 않는다(`max-height` 예외는 Task 3에서 명시).
- 작업 디렉터리는 저장소 루트 `/Users/tina/Project/OnQue`. 프론트엔드 명령은 `onque-frontend/`에서 실행한다.
- 커밋 메시지는 한국어, `<type>: <설명>` 형식.

## 파일 구조

**신규 생성**

| 파일 | 책임 |
|---|---|
| `onque-frontend/vitest.config.ts` | 테스트 러너 설정 |
| `onque-frontend/lib/priority.ts` | 약속+할일 병합·정렬 순수 함수. DOM·React 의존 없음 |
| `onque-frontend/lib/priority.test.ts` | 위 함수의 단위 테스트 |
| `onque-frontend/components/ui/Surface.tsx` | 표면 층위(card/sunken)와 hover 반응 |
| `onque-frontend/components/ui/Button.tsx` | 버튼 변형과 포커스 링 |
| `onque-frontend/components/ui/StatusChip.tsx` | 상태 배지(색+글자) |
| `onque-frontend/components/dashboard/PriorityStream.tsx` | 본류 스트림 렌더 + 카드 액션 |
| `onque-frontend/components/dashboard/SummaryColumn.tsx` | 오른쪽 요약 열 |

**수정**

| 파일 | 무엇을 |
|---|---|
| `onque-frontend/package.json` | `test` 스크립트, vitest devDependencies |
| `onque-frontend/app/globals.css` | 토큰 교체, 카드 액션 노출 규칙 추가 |
| `onque-frontend/app/dashboard/page.tsx` | 레이아웃 재배치, 약속 조회 추가 |

`CommitmentPanel.tsx`와 `MetricStrip.tsx`는 **수정하지 않는다.** 승인 게이트(proposed 일괄 처리)와 카운트업 애니메이션이 그대로 필요하고, 대시보드에서의 역할만 바뀌기 때문이다. `CommitmentPanel`은 하단에 남고, `MetricStrip`은 `SummaryColumn`이 세로 형태로 대체한다.

---

## Task 1: 프론트엔드 테스트 러너 도입

정렬 로직은 조용히 틀리는 종류의 코드다. 지금 프론트엔드에는 테스트 러너가 없어 먼저 깐다. 이 태스크는 디자인과 무관하며, 실패해도 뒤 태스크의 설계를 바꾸지 않는다.

**Files:**
- Modify: `onque-frontend/package.json`
- Create: `onque-frontend/vitest.config.ts`
- Create: `onque-frontend/lib/smoke.test.ts` (검증 후 삭제)

**Interfaces:**
- Consumes: 없음
- Produces: `npm test`(= `vitest run`) 명령이 동작하는 상태. Task 4가 이걸 쓴다.

- [ ] **Step 1: vitest 설치**

```bash
cd onque-frontend
npm install -D vitest@^3 @vitejs/plugin-react
```

- [ ] **Step 2: 설정 파일 작성**

`onque-frontend/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // 앱 코드가 '@/lib/api' 형태로 import 한다. tsconfig의 paths와 맞춘다.
      '@': fileURLToPath(new URL('./', import.meta.url)),
    },
  },
  test: {
    // 순수 로직만 테스트한다. DOM이 필요해지면 그때 jsdom을 켠다.
    environment: 'node',
    include: ['lib/**/*.test.ts'],
  },
});
```

- [ ] **Step 3: `package.json`에 스크립트 추가**

`"scripts"` 안에 추가:

```json
"test": "vitest run"
```

- [ ] **Step 4: 스모크 테스트 작성**

`onque-frontend/lib/smoke.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

describe('테스트 러너', () => {
  it('동작한다', () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 5: 실행해서 통과 확인**

```bash
cd onque-frontend && npm test
```

Expected: `1 passed`

- [ ] **Step 6: 스모크 테스트 삭제**

```bash
rm onque-frontend/lib/smoke.test.ts
```

- [ ] **Step 7: 빌드가 깨지지 않았는지 확인**

```bash
cd onque-frontend && npm run build
```

Expected: 성공. vitest는 devDependency라 번들에 들어가지 않는다.

- [ ] **Step 8: 커밋**

```bash
git add onque-frontend/package.json onque-frontend/package-lock.json onque-frontend/vitest.config.ts
git commit -m "chore: 프론트엔드 테스트 러너(vitest) 도입 — 정렬 로직 검증용"
```

---

## Task 2: 디자인 토큰 교체

**Files:**
- Modify: `onque-frontend/app/globals.css:3-31` (`:root`와 `@theme inline` 블록)

**Interfaces:**
- Consumes: 없음
- Produces: Tailwind 유틸리티 클래스 `bg-surface-sunken`, `bg-surface-hover`, `text-fg-muted`, `text-fg-dim`, `text-fg-disabled`, `bg-late`, `text-late-fg`, `bg-late-bg`, `bg-soon`, `text-soon-fg`, `bg-soon-bg`, `border-hairline`. Task 3~7이 전부 이 클래스명을 쓴다.

- [ ] **Step 1: `:root` 블록 교체**

`onque-frontend/app/globals.css`에서 기존 `:root { ... }`를 통째로 아래로 바꾼다.

```css
:root {
  /* 표면 3단 — 선이 아니라 밝기 차로 구역을 나눈다. R1의 핵심. */
  --background: #07080e;
  --surface: #12151f;
  --surface-sunken: #0c0e16;
  --surface-hover: #171b28;
  --sidebar: #04050a;
  --sidebar-foreground: #c9cbd6;

  /* 글자 3등급. 모두 --surface 위에서 4.5:1을 넘긴다.
     --fg-disabled만 4.0:1이라 읽어야 하는 글자에 쓰지 않는다. */
  --foreground: #e8eaf4;
  --fg-muted: #a8aec5;
  --fg-dim: #868da8;
  --fg-disabled: #6f7590;

  --brand: #7c8cff;
  --brand-foreground: #06070d;

  /* 상태색. 색만으로 구분하지 않고 항상 글자를 함께 쓴다. */
  --late: #ff6b5e;
  --late-bg: #ff6b5e22;
  --late-fg: #ff9c92;
  --soon: #f5a623;
  --soon-bg: #f5a62322;
  --soon-fg: #f7c173;

  --hairline: #ffffff0d;

  /* 개편하지 않은 9개 화면이 border-border에 의존한다. 지우면 그 화면들이
     한 덩어리로 뭉개지므로, 값만 약화시켜 새 밝기 대비로 넘어가게 한다. */
  --border: #171a24;

  /* 기존 참조를 살리기 위한 별칭. 새 코드는 --soon을 쓴다. */
  --accent: var(--soon);
}
```

- [ ] **Step 2: `@theme inline` 블록 교체**

Tailwind 4는 `@theme inline`에 등록된 것만 유틸리티 클래스로 만든다. 기존 블록을 아래로 바꾼다.

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-surface: var(--surface);
  --color-surface-sunken: var(--surface-sunken);
  --color-surface-hover: var(--surface-hover);
  --color-border: var(--border);
  --color-hairline: var(--hairline);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-brand: var(--brand);
  --color-brand-foreground: var(--brand-foreground);
  --color-accent: var(--accent);
  --color-fg-muted: var(--fg-muted);
  --color-fg-dim: var(--fg-dim);
  --color-fg-disabled: var(--fg-disabled);
  --color-late: var(--late);
  --color-late-bg: var(--late-bg);
  --color-late-fg: var(--late-fg);
  --color-soon: var(--soon);
  --color-soon-bg: var(--soon-bg);
  --color-soon-fg: var(--soon-fg);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}
```

- [ ] **Step 3: 빌드 확인**

```bash
cd onque-frontend && npm run build
```

Expected: 성공, 타입 에러 0.

- [ ] **Step 4: 개편하지 않은 화면이 읽히는지 눈으로 확인**

```bash
cd onque-frontend && npm run dev
```

브라우저에서 `/login`, `/chat`, `/history`, `/groups`, `/profile`을 열어 확인한다.
확인 기준: **글자가 배경에 묻히지 않고, 카드 경계가 아예 사라지지 않았다.**
`--border`가 `#171a24`로 약해졌으므로 경계는 희미해야 정상이다. 안 보이는 게 아니라 희미한 것이면 통과.

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/app/globals.css
git commit -m "feat: 디자인 토큰을 밝기 3단·글자 3등급·상태색 체계로 교체

테두리가 아니라 밝기로 구역을 나누는 R1 방향에 맞춰 표면을 배경/카드/
침강면 3단으로 나눴다. 글자는 대비를 계산해 3등급으로 갈랐다 — 기존
목업이 캡션에 쓰던 #6f7590은 카드 배경 대비 4.01:1로 기준 미달이라
비활성 전용으로 내리고, 캡션은 5.5:1인 값으로 올렸다.

--border와 --accent는 지우지 않았다. 개편하지 않은 9개 화면이 쓰고
있어서, --border는 값만 약화시키고 --accent는 --soon 별칭으로 남겼다."
```

---

## Task 3: 공용 UI 컴포넌트 3개

**Files:**
- Create: `onque-frontend/components/ui/Surface.tsx`
- Create: `onque-frontend/components/ui/Button.tsx`
- Create: `onque-frontend/components/ui/StatusChip.tsx`
- Modify: `onque-frontend/app/globals.css` (파일 끝에 카드 액션 규칙 추가)

**Interfaces:**
- Consumes: Task 2의 색 유틸리티 클래스
- Produces:
  - `Surface({ level?: 'card' | 'sunken', interactive?: boolean, tone?: 'default' | 'late', className?: string, children })`
  - `Button({ variant?: 'primary' | 'ghost', size?: 'sm' | 'md', ...ButtonHTMLAttributes })`
  - `StatusChip({ tone: 'late' | 'soon' | 'neutral', children })`
  - CSS 클래스 `card-actions` (부모에 `group` 필요)

  Task 5·6·7이 이 세 컴포넌트와 `card-actions`를 쓴다.

- [ ] **Step 1: `Surface.tsx` 작성**

```tsx
import type { ReactNode } from 'react';

type Props = {
  /** card는 떠 있는 면, sunken은 뒤로 물러난 면. 밝기로 층위를 만든다. */
  level?: 'card' | 'sunken';
  /** hover·focus에서 떠오르게 한다. 클릭 가능한 카드에만 준다. */
  interactive?: boolean;
  /** 기한 지난 항목은 배경에 코랄 기미를 준다. */
  tone?: 'default' | 'late';
  className?: string;
  children: ReactNode;
};

const LEVEL: Record<NonNullable<Props['level']>, string> = {
  card: 'bg-surface',
  sunken: 'bg-surface-sunken',
};

export function Surface({
  level = 'card',
  interactive = false,
  tone = 'default',
  className = '',
  children,
}: Props) {
  const toneClass =
    tone === 'late' ? 'bg-[linear-gradient(101deg,#241318_0%,#12151f_58%)]' : LEVEL[level];
  const motion = interactive
    ? 'transition-[transform,background-color] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] hover:bg-surface-hover focus-within:-translate-y-[3px] focus-within:bg-surface-hover'
    : '';

  return <div className={`rounded-2xl ${toneClass} ${motion} ${className}`}>{children}</div>;
}
```

- [ ] **Step 2: `Button.tsx` 작성**

```tsx
import type { ButtonHTMLAttributes } from 'react';

type Props = {
  variant?: 'primary' | 'ghost';
  size?: 'sm' | 'md';
} & ButtonHTMLAttributes<HTMLButtonElement>;

const VARIANT = {
  primary: 'bg-brand text-brand-foreground hover:brightness-110',
  ghost: 'bg-white/10 text-fg-muted hover:bg-white/[0.16]',
} as const;

const SIZE = {
  sm: 'px-3 py-1.5 text-[11px]',
  md: 'px-4 py-2 text-xs',
} as const;

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      // focus-visible 링은 필수다. 기존 코드에는 포커스 표시가 아예 없어
      // 키보드 사용자가 지금 어디에 있는지 알 수 없었다.
      className={`inline-flex items-center rounded-lg font-bold transition-[transform,filter,background-color] duration-150 active:scale-[.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    />
  );
}
```

- [ ] **Step 3: `StatusChip.tsx` 작성**

```tsx
import type { ReactNode } from 'react';

type Props = {
  tone: 'late' | 'soon' | 'neutral';
  children: ReactNode;
};

const TONE = {
  late: 'bg-late-bg text-late-fg',
  soon: 'bg-soon-bg text-soon-fg',
  neutral: 'bg-white/[0.07] text-fg-dim',
} as const;

/**
 * 상태 배지. children에 항상 글자를 넣는다 — 색만으로 구분하면
 * 색각 이상 사용자와 흑백 출력에서 정보가 사라진다.
 */
export function StatusChip({ tone, children }: Props) {
  return (
    <span
      className={`inline-block shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-extrabold tracking-tight ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 4: 카드 액션 노출 규칙을 `globals.css` 끝에 추가**

Tailwind만으로는 `pointer: coarse`와 `prefers-reduced-motion`을 함께 다루기 번거로워 CSS로 쓴다.

```css
/* 카드 액션은 평소 접혀 있다가 마우스를 올리거나 포커스가 들어오면 펼쳐진다.
   세 갈래를 모두 처리해야 한다 — hover만 쓰면 터치와 키보드에서 아예 못 쓴다.
   max-height는 레이아웃 속성이지만 카드당 44px 고정이고 동시에 하나만
   열리므로 허용한다. */
.card-actions {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition:
    max-height 0.3s ease,
    opacity 0.25s,
    margin-top 0.3s;
}

.group:hover .card-actions,
.group:focus-within .card-actions {
  max-height: 44px;
  opacity: 1;
  margin-top: 0.7rem;
}

/* 터치 기기에는 hover가 없다. 항상 펼쳐 둔다. */
@media (pointer: coarse) {
  .card-actions {
    max-height: none;
    opacity: 1;
    margin-top: 0.7rem;
  }
}

/* 이 파일 위쪽의 전역 규칙이 모션 최소화 시 모든 transition을 0.01ms로
   죽인다. 펼침을 전환에만 맡기면 버튼이 깜빡이며 열리거나 안 열린다.
   그래서 이때는 처음부터 펼쳐 둔다. */
@media (prefers-reduced-motion: reduce) {
  .card-actions {
    max-height: none;
    opacity: 1;
    margin-top: 0.7rem;
  }
}
```

- [ ] **Step 5: 빌드 확인**

```bash
cd onque-frontend && npm run build
```

Expected: 성공, 타입 에러 0. (아직 어디서도 안 쓰므로 번들 크기 변화는 미미하다.)

- [ ] **Step 6: 커밋**

```bash
git add onque-frontend/components/ui onque-frontend/app/globals.css
git commit -m "feat: 공용 UI 컴포넌트 3개와 카드 액션 노출 규칙

카드·버튼 스타일이 각 화면 파일에 클래스 문자열로 흩어져 있어 한 번
바꾸려면 10곳을 고쳐야 했다. Surface·Button·StatusChip으로 모은다.

Button에 focus-visible 링을 넣었다 — 기존 코드에는 포커스 표시가 아예
없어 키보드 사용자가 위치를 알 수 없었다.

card-actions는 hover뿐 아니라 focus-within, pointer:coarse,
prefers-reduced-motion까지 처리한다. hover만 쓰면 터치와 키보드에서
액션 버튼을 아예 못 쓴다."
```

---

## Task 4: 우선순위 병합·정렬 순수 함수

**Files:**
- Create: `onque-frontend/lib/priority.ts`
- Create: `onque-frontend/lib/priority.test.ts`

**Interfaces:**
- Consumes: `CommitmentRecord`, `Todo` (기존 `lib/api.ts`)
- Produces:
  - `type PriorityItem`
  - `daysPastDue(dueDate: string | null, todayKey: string): number | null`
  - `buildPriorityStream(commitments: CommitmentRecord[], todos: Todo[], todayKey: string): PriorityItem[]`

  Task 5가 `PriorityItem`을 렌더하고, Task 7이 `buildPriorityStream`을 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`onque-frontend/lib/priority.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { buildPriorityStream, daysPastDue } from './priority';
import type { CommitmentRecord, Todo } from './api';

const TODAY = '2026-08-11';

function commitment(over: Partial<CommitmentRecord> & { id: number }): CommitmentRecord {
  return {
    content: '약속',
    client_id: null,
    client_name: null,
    due_date: null,
    status: 'proposed',
    source_type: 'call',
    source_id: null,
    evidence: '근거',
    is_overdue: false,
    is_due_soon: false,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  };
}

function todo(over: Partial<Todo> & { id: number }): Todo {
  return {
    content: '할 일',
    due_date: null,
    is_done: false,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  };
}

describe('daysPastDue', () => {
  it('기한이 지났으면 지난 일수를 센다', () => {
    expect(daysPastDue('2026-08-10', TODAY)).toBe(1);
    expect(daysPastDue('2026-08-04', TODAY)).toBe(7);
  });

  it('오늘이 기한이면 아직 안 지난 것이다', () => {
    expect(daysPastDue(TODAY, TODAY)).toBeNull();
  });

  it('기한이 남았거나 없으면 null이다', () => {
    expect(daysPastDue('2026-08-14', TODAY)).toBeNull();
    expect(daysPastDue(null, TODAY)).toBeNull();
  });
});

describe('buildPriorityStream', () => {
  it('기한 지난 것을 맨 앞에, 많이 지난 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [commitment({ id: 1, due_date: '2026-08-10' })],
      [todo({ id: 2, due_date: '2026-08-04' })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-2', 'commitment-1']);
    expect(stream[0].daysPastDue).toBe(7);
  });

  it('지난 것 다음에 임박한 것, 그다음 기한 있는 것을 기한 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [
        commitment({ id: 1, due_date: '2026-08-25' }),
        commitment({ id: 2, due_date: '2026-08-12' }),
      ],
      [todo({ id: 3, due_date: '2026-08-09' })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-3', 'commitment-2', 'commitment-1']);
    expect(stream[1].isDueSoon).toBe(true);
    expect(stream[2].isDueSoon).toBe(false);
  });

  it('기한 없는 것은 맨 뒤에, 최근 등록 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [],
      [
        todo({ id: 1, created_at: '2026-08-02T00:00:00Z' }),
        todo({ id: 2, created_at: '2026-08-09T00:00:00Z' }),
      ],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-2', 'todo-1']);
  });

  it('완료한 할 일과 종료된 약속은 넣지 않는다', () => {
    const stream = buildPriorityStream(
      [
        commitment({ id: 1, status: 'fulfilled' }),
        commitment({ id: 2, status: 'dismissed' }),
        commitment({ id: 3, status: 'confirmed' }),
      ],
      [todo({ id: 4, is_done: true })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['commitment-3']);
  });

  it('출처를 글자로 붙여 섞여도 무엇인지 알 수 있게 한다', () => {
    const stream = buildPriorityStream(
      [commitment({ id: 1, source_type: 'document' })],
      [todo({ id: 2 })],
      TODAY,
    );
    const byKey = Object.fromEntries(stream.map((i) => [i.key, i.sourceLabel]));
    expect(byKey['commitment-1']).toBe('약속 · 문서');
    expect(byKey['todo-2']).toBe('할 일');
  });

  it('빈 입력에 빈 배열을 돌려준다', () => {
    expect(buildPriorityStream([], [], TODAY)).toEqual([]);
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd onque-frontend && npm test
```

Expected: FAIL — `Failed to resolve import "./priority"`

- [ ] **Step 3: 구현 작성**

`onque-frontend/lib/priority.ts`:

```ts
import type { CommitmentRecord, Todo } from './api';

/** 기한이 이 일수 안으로 남았으면 임박으로 본다. 백엔드 DUE_SOON_DAYS와 같은 값. */
const DUE_SOON_DAYS = 2;

const MS_PER_DAY = 86_400_000;

const SOURCE_LABEL: Record<CommitmentRecord['source_type'], string> = {
  call: '통화',
  document: '문서',
  chat: '채팅',
};

/** 아직 처리 중인 약속만 스트림에 올린다. */
const OPEN_STATUSES: ReadonlySet<CommitmentRecord['status']> = new Set(['proposed', 'confirmed']);

export type PriorityItem = {
  /** React key. 종류가 다른 두 목록을 섞으므로 id만으로는 충돌한다. */
  key: string;
  kind: 'commitment' | 'todo';
  id: number;
  content: string;
  dueDate: string | null;
  /** 기한이 지났으면 지난 일수, 아니면 null */
  daysPastDue: number | null;
  isDueSoon: boolean;
  /** '약속 · 통화' 또는 '할 일' */
  sourceLabel: string;
  /** 정렬 최후 기준. ISO 8601 문자열 */
  createdAt: string;
  /** 약속만 가진다. 화면에 "아직 확정 안 됨"을 표시할지 판단한다. */
  isUnconfirmed: boolean;
};

function dayDiff(fromKey: string, toKey: string): number {
  return Math.round(
    (Date.parse(`${toKey}T00:00:00Z`) - Date.parse(`${fromKey}T00:00:00Z`)) / MS_PER_DAY,
  );
}

/**
 * 기한이 며칠 지났는지. 안 지났거나 기한이 없으면 null.
 *
 * 오늘이 기한인 것은 "지난" 것으로 세지 않는다 — 아직 하루가 남아 있다.
 */
export function daysPastDue(dueDate: string | null, todayKey: string): number | null {
  if (!dueDate || dueDate >= todayKey) return null;
  return dayDiff(dueDate, todayKey);
}

function isDueSoon(dueDate: string | null, todayKey: string): boolean {
  if (!dueDate || dueDate < todayKey) return false;
  return dayDiff(todayKey, dueDate) <= DUE_SOON_DAYS;
}

/** 급한 정도의 등급. 낮을수록 위. */
function rank(item: PriorityItem): number {
  if (item.daysPastDue !== null) return 0;
  if (item.isDueSoon) return 1;
  if (item.dueDate) return 2;
  return 3;
}

function compare(a: PriorityItem, b: PriorityItem): number {
  const rankDiff = rank(a) - rank(b);
  if (rankDiff !== 0) return rankDiff;

  // 많이 지난 것이 위
  if (a.daysPastDue !== null && b.daysPastDue !== null) return b.daysPastDue - a.daysPastDue;
  // 기한이 가까운 것이 위
  if (a.dueDate && b.dueDate) return a.dueDate.localeCompare(b.dueDate);
  // 기한이 없으면 최근 등록이 위
  return b.createdAt.localeCompare(a.createdAt);
}

/**
 * 약속과 할 일을 종류가 아니라 급한 순으로 하나의 목록에 섞는다.
 *
 * 종류별로 카드를 나누면 "지금 뭐가 급한가"를 알려고 여러 카드를 훑어야 한다.
 * 대신 각 항목에 출처를 글자로 붙여 섞여도 무엇인지 알 수 있게 한다.
 */
export function buildPriorityStream(
  commitments: CommitmentRecord[],
  todos: Todo[],
  todayKey: string,
): PriorityItem[] {
  const items: PriorityItem[] = [];

  for (const c of commitments) {
    if (!OPEN_STATUSES.has(c.status)) continue;
    items.push({
      key: `commitment-${c.id}`,
      kind: 'commitment',
      id: c.id,
      content: c.content,
      dueDate: c.due_date,
      daysPastDue: daysPastDue(c.due_date, todayKey),
      isDueSoon: isDueSoon(c.due_date, todayKey),
      sourceLabel: `약속 · ${SOURCE_LABEL[c.source_type]}`,
      createdAt: c.created_at,
      isUnconfirmed: c.status === 'proposed',
    });
  }

  for (const t of todos) {
    if (t.is_done) continue;
    items.push({
      key: `todo-${t.id}`,
      kind: 'todo',
      id: t.id,
      content: t.content,
      dueDate: t.due_date,
      daysPastDue: daysPastDue(t.due_date, todayKey),
      isDueSoon: isDueSoon(t.due_date, todayKey),
      sourceLabel: '할 일',
      createdAt: t.created_at,
      isUnconfirmed: false,
    });
  }

  return items.sort(compare);
}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd onque-frontend && npm test
```

Expected: `9 passed`

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/lib/priority.ts onque-frontend/lib/priority.test.ts
git commit -m "feat: 약속과 할 일을 급한 순으로 섞는 순수 함수

종류별로 카드를 나누면 '지금 뭐가 급한가'를 알려고 여러 카드를 훑어야
한다. 하나의 스트림으로 합치되 출처를 글자로 붙여 무엇인지 알 수 있게
한다.

며칠 지났는지는 프론트에서 센다 — GET /commitments 응답에 없고, 이
개편에서 백엔드를 건드리지 않기로 했다. 오늘이 기한인 것은 지난 것으로
세지 않는다."
```

---

## Task 5: 본류 스트림 컴포넌트

**Files:**
- Create: `onque-frontend/components/dashboard/PriorityStream.tsx`
- Modify: `onque-frontend/app/globals.css` (파일 끝에 맥동 키프레임 추가)

**Interfaces:**
- Consumes: `PriorityItem` (Task 4), `Surface`·`Button`·`StatusChip` (Task 3), `card-actions` 클래스 (Task 3)
- Produces: `PriorityStream({ items, onCompleteTodo }: { items: PriorityItem[]; onCompleteTodo: (id: number) => void })`

  Task 7이 대시보드에서 이걸 렌더한다.

- [ ] **Step 1: 컴포넌트 작성**

```tsx
'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
import { Button } from '@/components/ui/Button';
import { StatusChip } from '@/components/ui/StatusChip';
import type { PriorityItem } from '@/lib/priority';

type Props = {
  items: PriorityItem[];
  onCompleteTodo: (id: number) => void;
};

function dueText(item: PriorityItem): string {
  if (item.daysPastDue !== null) return `기한 ${item.dueDate}`;
  if (item.dueDate) return `${item.dueDate}까지`;
  return '기한 없음';
}

export function PriorityStream({ items, onCompleteTodo }: Props) {
  if (items.length === 0) {
    return (
      <Surface level="sunken" className="p-10 text-center">
        <p className="text-sm text-fg-dim">지금 처리할 것이 없습니다.</p>
      </Surface>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.key}>
          <Surface
            interactive
            tone={item.daysPastDue !== null ? 'late' : 'default'}
            className="group p-4"
          >
            <div className="flex items-start gap-2.5">
              {item.daysPastDue !== null && (
                <span
                  aria-hidden
                  className="mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full bg-late [animation:pulse-late_2.2s_ease-in-out_infinite]"
                />
              )}
              <p className="min-w-0 flex-1 text-sm font-semibold leading-snug text-foreground">
                {item.content}
              </p>
              {item.daysPastDue !== null && (
                <StatusChip tone="late">{item.daysPastDue}일 지남</StatusChip>
              )}
              {item.daysPastDue === null && item.isDueSoon && (
                <StatusChip tone="soon">마감 임박</StatusChip>
              )}
            </div>

            <p className="mt-1 text-[11px] text-fg-dim">
              {item.sourceLabel} · {dueText(item)}
              {item.isUnconfirmed && ' · 아직 확정 안 됨'}
            </p>

            <div className="card-actions">
              {item.kind === 'todo' ? (
                <Button size="sm" onClick={() => onCompleteTodo(item.id)}>
                  완료
                </Button>
              ) : (
                <Link href="/dashboard#commitments">
                  <Button size="sm">약속 확인하기</Button>
                </Link>
              )}
            </div>
          </Surface>
        </li>
      ))}
    </ul>
  );
}
```

약속의 상태 변경은 하단 `CommitmentPanel`의 승인 게이트가 담당한다. 스트림에서 직접 바꾸면 일괄 승인 흐름과 두 갈래가 되므로, 여기서는 그쪽으로 보내기만 한다.

- [ ] **Step 2: 맥동 키프레임을 `globals.css` 끝에 추가**

```css
/* 기한 지난 항목의 점. 색만으로 알리지 않고 옆에 "N일 지남" 글자가 함께 있다. */
@keyframes pulse-late {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(255, 107, 94, 0.53);
  }
  60% {
    box-shadow: 0 0 0 7px rgba(255, 107, 94, 0);
  }
}
```

- [ ] **Step 3: 빌드 확인**

```bash
cd onque-frontend && npm run build
```

Expected: 성공, 타입 에러 0.

- [ ] **Step 4: 커밋**

```bash
git add onque-frontend/components/dashboard/PriorityStream.tsx onque-frontend/app/globals.css
git commit -m "feat: 본류 스트림 컴포넌트 — 급한 순 카드 목록

약속 상태 변경은 넣지 않았다. 하단 CommitmentPanel의 일괄 승인 게이트가
담당하고, 여기서 직접 바꾸면 승인 흐름이 두 갈래가 된다."
```

---

## Task 6: 요약 열 컴포넌트

**Files:**
- Create: `onque-frontend/components/dashboard/SummaryColumn.tsx`

**Interfaces:**
- Consumes: `Metric` (기존 `components/MetricStrip.tsx`), `ScheduleItem`·`DocumentRecord` (기존 `lib/api.ts`), `Surface` (Task 3)
- Produces: `SummaryColumn({ metrics, schedules, documents }: { metrics: Metric[]; schedules: ScheduleItem[]; documents: DocumentRecord[] })`

  Task 7이 대시보드 오른쪽 열에 렌더한다.

- [ ] **Step 1: 컴포넌트 작성**

`metrics`는 대시보드가 넘기는 배열을 **개수 그대로** 세로로 쌓는다. 지표가 늘거나 줄어도 레이아웃이 안 깨진다.

```tsx
'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
import type { Metric } from '@/components/MetricStrip';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';

type Props = {
  metrics: Metric[];
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
};

export function SummaryColumn({ metrics, schedules, documents }: Props) {
  return (
    <Surface level="sunken" className="p-4">
      {/* 1024px 미만에서는 본류 위로 올라가 가로로 눕는다. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-1 lg:gap-0">
        {metrics.map((metric, index) => (
          <div
            key={metric.label}
            className={index > 0 ? 'lg:mt-3 lg:border-t lg:border-hairline lg:pt-3' : ''}
          >
            <p
              className={`text-2xl font-bold leading-none tracking-tight tabular-nums ${
                metric.alert && metric.value > 0 ? 'text-late' : 'text-foreground'
              }`}
            >
              {metric.value}
            </p>
            <p className="mt-1 text-[10px] font-semibold text-fg-dim">{metric.hint}</p>
          </div>
        ))}
      </div>

      {/* 768px 미만에서는 숫자만 남기고 접는다. */}
      <div className="hidden md:block">
        <div className="mt-4 border-t border-hairline pt-4">
          <p className="text-[10px] font-semibold text-fg-dim">다가오는 일정</p>
          {schedules.length === 0 ? (
            <p className="mt-2 text-[11px] text-fg-dim">7일 안에 예정된 일정이 없습니다.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {schedules.map((schedule) => (
                <li key={schedule.id} className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[11px] text-fg-muted">{schedule.title}</span>
                  <span className="shrink-0 text-[10px] tabular-nums text-fg-dim">
                    {schedule.scheduled_date.slice(5)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-4 border-t border-hairline pt-4">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-[10px] font-semibold text-fg-dim">최근 요약</p>
            <Link
              href="/history"
              className="rounded text-[10px] text-fg-dim transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              전체 보기
            </Link>
          </div>
          {documents.length === 0 ? (
            <p className="mt-2 text-[11px] text-fg-dim">아직 요약한 통화·문서가 없습니다.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {documents.slice(0, 3).map((doc) => (
                <li key={doc.id} className="truncate text-[11px] text-fg-muted">
                  {doc.filename}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Surface>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd onque-frontend && npm run build
```

Expected: 성공, 타입 에러 0.

- [ ] **Step 3: 커밋**

```bash
git add onque-frontend/components/dashboard/SummaryColumn.tsx
git commit -m "feat: 요약 열 컴포넌트 — 숫자·일정·최근요약을 오른쪽에 모음

metrics 배열을 개수 그대로 세로로 쌓는다. 지표가 늘거나 줄어도
레이아웃이 안 깨진다. 768px 미만에서는 숫자만 남기고 일정·최근요약을
접는다."
```

---

## Task 7: 대시보드 조립

**Files:**
- Modify: `onque-frontend/app/dashboard/page.tsx`

**Interfaces:**
- Consumes: `buildPriorityStream` (Task 4), `PriorityStream` (Task 5), `SummaryColumn` (Task 6)
- Produces: 없음 (최종 화면)

- [ ] **Step 1: import 교체**

기존 `import { MetricStrip, type Metric } from '@/components/MetricStrip';` 와
`import { getDocuments, type DocumentRecord } from '@/lib/api';` 두 줄을 지우고 아래를 넣는다.

```tsx
import { type Metric } from '@/components/MetricStrip';
import { PriorityStream } from '@/components/dashboard/PriorityStream';
import { SummaryColumn } from '@/components/dashboard/SummaryColumn';
import { buildPriorityStream } from '@/lib/priority';
import {
  getCommitments,
  getDocuments,
  type CommitmentRecord,
  type DocumentRecord,
} from '@/lib/api';
```

`MetricStrip` 컴포넌트 자체는 더 이상 대시보드에서 렌더하지 않지만 `Metric` 타입은 계속 쓴다.

- [ ] **Step 2: 약속 상태와 조회 effect 추가**

`const [documentsError, setDocumentsError] = useState<string | null>(null);` 아래에 넣는다.

```tsx
  const [commitments, setCommitments] = useState<CommitmentRecord[]>([]);
  const [commitmentsError, setCommitmentsError] = useState<string | null>(null);
```

`getDocuments` effect 아래에 새 effect를 넣는다. 서버 기본 limit이 20이라 명시적으로 100을 요청한다.

```tsx
  useEffect(() => {
    if (currentGroupId === null) {
      setCommitments([]);
      setCommitmentsError(null);
      return;
    }
    Promise.all([
      getCommitments(currentGroupId, 'proposed', 100),
      getCommitments(currentGroupId, 'confirmed', 100),
    ])
      .then(([proposed, confirmed]) => {
        setCommitments([...proposed, ...confirmed]);
        setCommitmentsError(null);
      })
      .catch((err: unknown) => {
        setCommitments([]);
        setCommitmentsError(err instanceof Error ? err.message : '약속을 불러오지 못했습니다.');
      });
  }, [currentGroupId]);
```

- [ ] **Step 3: 스트림 계산으로 교체**

`priorityTodos` useMemo 블록을 통째로 삭제하고 그 자리에 넣는다. 본류 스트림이 대체한다.

```tsx
  const priorityStream = useMemo(() => {
    if (!todayKey) return [];
    return buildPriorityStream(commitments, todos, todayKey).slice(0, 8);
  }, [commitments, todos, todayKey]);
```

- [ ] **Step 4: 에러 배너에 약속 실패 추가**

배너 조건을 바꾼다.

```tsx
      {(workspaceError || documentsError || commitmentsError) && (
```

`{workspaceError && <li>할 일·일정: {workspaceError}</li>}` 아래에 넣는다.

```tsx
            {commitmentsError && <li>약속: {commitmentsError}</li>}
```

- [ ] **Step 5: 본문 레이아웃 교체**

`<div className="mt-6"><MetricStrip metrics={metrics} /></div>` 부터 모듈 바로가기 블록의 닫는 `</div>`까지를 통째로 아래로 바꾼다.

```tsx
      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_260px] xl:grid-cols-[1fr_280px]">
        {/* 좁은 화면에서는 요약이 본류 위로 올라간다. */}
        <div className="order-2 lg:order-1">
          <PriorityStream items={priorityStream} onCompleteTodo={(id) => toggleTodo(id, true)} />
        </div>
        <div className="order-1 lg:order-2">
          <SummaryColumn metrics={metrics} schedules={upcomingSchedules} documents={documents} />
        </div>
      </div>

      <div id="commitments" className="mt-8 scroll-mt-6">
        <CommitmentPanel groupId={currentGroupId} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_280px]">
        <div className="grid gap-3 sm:grid-cols-2">
          {MODULES.map((mod) => (
            <Link
              key={mod.href}
              href={mod.href}
              className="group rounded-xl bg-surface px-4 py-3.5 transition-[transform,background-color] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <p className="text-xs font-bold text-foreground group-hover:text-brand">{mod.title}</p>
              <p className="mt-0.5 text-[11px] text-fg-dim">{mod.description}</p>
            </Link>
          ))}
        </div>
        <ClientPanel groupId={currentGroupId} />
      </div>
```

- [ ] **Step 6: 폭과 헤더 색 조정**

`<div className="mx-auto max-w-5xl px-6 py-10">` 를 바꾼다. 요약 열이 붙으므로 폭을 넓힌다.

```tsx
    <div className="mx-auto max-w-6xl px-6 py-10">
```

헤더의 `text-foreground/40` 을 `text-fg-dim` 으로 바꾼다. `/40` 은 대비 계산 밖이라 4.5:1을 보장하지 않는다.

- [ ] **Step 7: 죽은 코드 제거**

`dueLabel` 함수는 `priorityTodos`와 함께 참조가 사라지므로 지운다.
`shiftDays`·`UPCOMING_WINDOW_DAYS`는 `upcomingSchedules`가 계속 쓰므로 **남긴다.**

```bash
cd onque-frontend && grep -n "dueLabel\|shiftDays\|UPCOMING_WINDOW_DAYS\|MetricStrip" app/dashboard/page.tsx
```

Expected: `dueLabel` 0건, `MetricStrip`은 타입 import 1건만, 나머지는 정의 + 사용처가 함께 나온다.

- [ ] **Step 8: 빌드와 테스트 확인**

```bash
cd onque-frontend && npm run build && npm test
```

Expected: 빌드 성공, 타입 에러 0, 테스트 9 passed.

- [ ] **Step 9: 커밋**

```bash
git add onque-frontend/app/dashboard/page.tsx
git commit -m "feat: 대시보드를 본류 스트림 + 요약 열로 재배치

기존 6블록(약속·클라이언트·우선처리할일·다가오는일정·최근요약·모듈)이
같은 크기 카드로 세로로만 쌓여 있어 시선이 갈 데가 없었다.

약속과 할 일을 급한 순으로 섞은 본류를 왼쪽에, 숫자·일정·최근요약을
오른쪽 침강면 열에 모아 가로를 쓴다. 1024px 미만에서는 요약이 본류
위로 올라간다.

ClientPanel은 지우지 않고 하단으로 내렸다 — 조회 빈도가 낮은 것이지
데이터가 필요 없는 게 아니다. CommitmentPanel의 승인 게이트도 그대로
두고, 스트림의 약속 카드가 그쪽으로 링크한다."
```

---

## Task 8: 접근성·반응형 검증

이 태스크는 코드를 거의 안 쓴다. 앞선 태스크가 만든 것이 실제로 동작하는지 확인하고, 안 되면 고친다.

**Files:**
- Modify: 검증에서 문제가 나온 파일만

**Interfaces:**
- Consumes: Task 1~7 전부
- Produces: 없음

- [ ] **Step 1: 개발 서버 기동**

```bash
cd onque-frontend && npm run dev
```

- [ ] **Step 2: 키보드만으로 액션에 도달하는지 확인**

`/dashboard`에서 마우스를 쓰지 않고 Tab만 누른다.

확인 기준:
- 카드에 포커스가 들어가는 순간 액션 버튼이 **펼쳐진다**(`:focus-within`)
- 버튼에 포커스가 가면 **인디고 링이 보인다**
- Tab을 계속 눌러 모든 카드의 버튼에 도달할 수 있다

실패하면 `globals.css`의 `.group:focus-within .card-actions` 규칙과, `Surface`에 `group` 클래스가 실제로 붙었는지 확인한다.

- [ ] **Step 3: 터치 기기에서 버튼이 보이는지 확인**

Chrome DevTools → Device Toolbar(⌘⇧M) → iPhone 선택 → 새로고침.

확인 기준: **액션 버튼이 처음부터 보인다.** `@media (pointer: coarse)`가 적용되기 때문이다.

- [ ] **Step 4: 모션 최소화에서 버튼이 보이는지 확인**

DevTools → Rendering 패널 → `Emulate CSS media feature prefers-reduced-motion` → `reduce`.

확인 기준: 맥동이 멈추고, **액션 버튼은 처음부터 보인다.** 안 보이면 그게 스펙이 경고한 바로 그 함정이다.

- [ ] **Step 5: 폭별 가로 스크롤 확인**

DevTools에서 폭을 320 / 768 / 1024 / 1440으로 바꿔가며 본다.

확인 기준:
- 가로 스크롤바가 생기지 않는다
- 1024 미만에서 요약이 본류 **위로** 올라간다
- 768 미만에서 요약에 숫자만 남는다
- 320에서 카드 안 글자가 잘리지 않는다

- [ ] **Step 6: 대비 확인**

DevTools → Elements → 텍스트 선택 → Styles의 색상 견본 클릭 → Contrast ratio.

확인 대상과 기대값:
- 카드 제목(`text-foreground` on `bg-surface`) ≥ 14:1
- 카드 부제(`text-fg-dim` on `bg-surface`) ≥ 5.5:1
- 요약 열 캡션(`text-fg-dim` on `bg-surface-sunken`) ≥ 4.5:1

마지막 항목은 스펙의 계산이 `--surface` 기준이라 침강면에서는 값이 다르다. **4.5:1 미만이면 그 자리만 `text-fg-muted`로 올린다.**

- [ ] **Step 7: 개편하지 않은 화면 회귀 확인**

`/login`, `/chat`, `/history`, `/groups`, `/profile`, `/announcements`, `/calls`, `/documents`를 열어본다.

확인 기준: 글자가 배경에 묻히지 않고, 카드 경계가 희미하게라도 보인다.

- [ ] **Step 8: 백엔드 회귀 확인**

```bash
cd /Users/tina/Project/OnQue && venv/bin/python -m pytest -q
```

Expected: `241 passed`

- [ ] **Step 9: 고친 게 있으면 커밋**

```bash
git add -A
git commit -m "fix: 개편 검증에서 나온 문제 수정"
```

고친 게 없으면 이 단계를 건너뛴다.

- [ ] **Step 10: 트러블슈팅 기록 판단**

`~/Project/OnQue/CLAUDE.md`의 기준에 해당하는 일이 있었는지 본다 — 원인 찾는 데 도구 호출 3회 이상, 가설이 틀려 방향을 바꿈, 에러와 원인이 직관적으로 안 이어짐 등.
해당하면 `TROUBLESHOOTING.md`에 `TS-034`로 기록하고, 없으면 기록하지 않는다.

---

## 자체 검토

**스펙 커버리지**

| 스펙 항목 | 태스크 |
|---|---|
| 토큰 3단 표면·3등급 글자·상태색 | Task 2 |
| `--border` 약화 (제거 아님) | Task 2 Step 1 |
| `--accent` 별칭 유지 | Task 2 Step 1 |
| `Surface` / `Button` / `StatusChip` | Task 3 |
| `focus-visible` 링 | Task 3 Step 2, Task 8 Step 2 |
| 색만으로 상태 구분 금지 | Task 3 Step 3, Task 5 Step 1 (점 옆에 글자) |
| 본류 스트림 병합·정렬 | Task 4 |
| 정렬 4단 규칙 | Task 4 Step 3 (`rank`, `compare`) |
| 출처 라벨 | Task 4 Step 3 (`SOURCE_LABEL`) |
| 며칠 지났는지 프론트 계산 | Task 4 Step 3 (`daysPastDue`) |
| `metrics` 배열 개수 그대로 | Task 6 Step 1 |
| `ClientPanel` 하단 이동 | Task 7 Step 5 |
| 반응형 4구간 | Task 6 Step 1, Task 7 Step 5, Task 8 Step 5 |
| `focus-within` / `pointer:coarse` / `reduced-motion` | Task 3 Step 4, Task 8 Step 2~4 |
| 완료 기준 8개 | Task 8 |

빠진 스펙 항목 없음.

**해결한 불일치**

- 스펙은 `MetricStrip`을 "요약 열 상단으로 이동"이라고만 적었다. 계획에서는 `MetricStrip` 컴포넌트를 수정하지 않고 `SummaryColumn`이 `Metric` 타입만 재사용해 세로로 다시 그리는 것으로 확정했다. 카운트업 애니메이션이 있는 가로 스트립을 세로 열에 그대로 넣으면 폭이 안 맞는다.
- 스펙의 대비 계산은 `--surface`(#12151f) 기준인데 요약 열은 `--surface-sunken`(#0c0e16)이라 값이 다르다. Task 8 Step 6에서 실측하고 미달이면 한 등급 올리도록 했다.
- 스펙은 본류 카드의 액션을 정하지 않았다. 약속은 `CommitmentPanel`의 일괄 승인 게이트가 담당하므로 스트림에서는 링크만 걸도록 Task 5에서 확정했다. 승인 흐름이 두 갈래가 되는 것을 막는다.
- 스펙에 없던 것을 하나 추가했다 — **Task 1의 테스트 러너 도입.** 프론트엔드에 테스트 러너가 아예 없어 정렬 로직을 검증할 방법이 없었다. 독립 태스크로 분리해, 도구 설치가 막혀도 디자인 태스크의 설계가 바뀌지 않게 했다.

**타입 일관성**

`PriorityItem`의 필드명(`key`, `kind`, `id`, `content`, `dueDate`, `daysPastDue`, `isDueSoon`, `sourceLabel`, `createdAt`, `isUnconfirmed`)이 Task 4 정의와 Task 5 사용에서 일치한다. `Metric`(`label`, `value`, `hint`, `alert`)은 기존 `MetricStrip.tsx`의 export와 일치한다. `CommitmentRecord`·`Todo`·`ScheduleItem`·`DocumentRecord`는 기존 `lib/api.ts` 정의를 그대로 쓴다.
