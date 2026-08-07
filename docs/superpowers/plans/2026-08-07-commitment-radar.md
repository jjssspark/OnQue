# 약속 레이더와 실시간 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 우측 패널의 "실시간"을 참으로 만들고(30초 폴링), 모든 화면에 떠 있는 그 패널에 약속 요약을 읽기 전용으로 노출한다.

**Architecture:** `WorkspaceContext`가 이미 하는 `Promise.all` 조회에 약속 두 건을 얹고 폴링을 건다. `SmartDashboardPanel`은 그 데이터를 그리기만 한다. **백엔드를 건드리지 않는다** — 필요한 API와 프론트 함수가 전부 이미 있다. 확정·기각 조작은 기존 `CommitmentPanel`(대시보드 페이지)이 계속 맡는다.

**Tech Stack:** Next.js App Router, TypeScript, Tailwind, React Context

**스펙:** `docs/superpowers/specs/2026-08-07-commitment-radar-design.md`

## Global Constraints

- **백엔드를 변경하지 않는다.** `routers/`, `models.py`, `scripts/`를 건드리지 마라. 마이그레이션 없음. 이 플랜은 `onque-frontend/` 안에서만 움직인다.
- **`components/CommitmentPanel.tsx`를 건드리지 마라.** 확정·기각은 그쪽 책임이다. 우측 패널은 읽기 전용 요약만 맡는다.
- **이모지를 아이콘으로 쓰지 않는다.** 아이콘이 필요하면 `components/Sidebar.tsx`가 쓰는 인라인 SVG 패턴을 따른다.
- 사용자 대면 문구는 한국어.
- 새 색·간격 체계를 만들지 않는다. `SmartDashboardPanel.tsx`와 `CommitmentPanel.tsx`의 기존 Tailwind 클래스를 그대로 쓴다.
- 애니메이션은 `transform`·`opacity`만. 레이아웃 속성(`width`, `height`, `top`, `margin`)은 애니메이션하지 않는다.
- 프론트 검증은 `cd onque-frontend && npx tsc --noEmit`과 `npx next build --webpack`. **`npm run build`(Turbopack)는 워크트리에서 `node_modules` 심링크 때문에 실패한다** (TS-026). `next.config.ts`를 고치지 마라.
- 백엔드 테스트는 이 플랜이 바꾸지 않지만, 각 태스크 끝에 `venv/bin/pytest tests/ -q`를 한 번 돌려 **190 passed / 0 failed**가 유지되는지 확인한다. 프론트만 고쳤는데 깨졌다면 뭔가 잘못 건드린 것이다.
- Bash 도구에서 `run_in_background`를 쓰지 않는다. `&`도 붙이지 않는다. 포그라운드로 돌리고 timeout을 넉넉히 준다.

---

### Task 1: `WorkspaceContext`에 약속 조회와 폴링

**Files:**
- Modify: `onque-frontend/components/WorkspaceContext.tsx`

**Interfaces:**
- Consumes: `lib/api.ts`의 `getCommitmentsPage(groupId, status, limit)`, `getCommitments(groupId, status, limit)`, 타입 `CommitmentRecord`
- Produces: 컨텍스트 값에 `proposedCount: number`, `dueSoon: CommitmentRecord[]`, `lastSyncedAt: number | null` 추가. 기존 키(`todos`, `schedules`, `loading`, `error`, `currentGroupId`, `setCurrentGroupId`, `refresh`, `applySnapshot`, `toggleTodo`, `removeTodo`, `removeSchedule`)는 **이름·타입 그대로 유지한다** — 다른 화면들이 이미 읽고 있다.

- [ ] **Step 1: 현재 구조를 확인한다**

`onque-frontend/components/WorkspaceContext.tsx`를 연다. 확인할 것:

- `WorkspaceContextValue` 타입에 어떤 키가 있는지
- `refresh`가 `Promise.all([getTodos(currentGroupId), getSchedules(currentGroupId)])` 형태인지
- `currentGroupId === null`일 때 조기 반환하는지
- `useEffect(() => { refresh(); }, [refresh])`로 마운트 조회를 하는지

`lib/api.ts`에서 `getCommitmentsPage`와 `CommitmentRecord`의 **실제 시그니처**를 확인한다. 알려진 모양:

```ts
getCommitmentsPage(groupId: number, status?: CommitmentRecord['status'], limit?: number)
  : Promise<{ data: CommitmentRecord[]; meta: ListMeta | null }>
```

`CommitmentRecord`에 `id`, `content`, `due_date`, `status`, `is_overdue`, `is_due_soon`, 클라이언트 이름 필드가 있다. **실제 필드명을 파일에서 확인하고 그대로 쓴다.**

- [ ] **Step 2: 상수와 상태를 추가한다**

파일 상단 상수 구역:

```ts
// CommitmentPanel.tsx:19-21과 같은 이유. 서버 기본 limit(20)에 걸리면
// "확인 필요 N건"이 실제 개수가 아니라 20에서 멈춘다.
const COMMITMENT_LIMIT = 100;
const POLL_INTERVAL_MS = 30_000;
```

컴포넌트 상태:

```ts
  const [proposedCount, setProposedCount] = useState(0);
  const [dueSoon, setDueSoon] = useState<CommitmentRecord[]>([]);
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null);
```

- [ ] **Step 3: `refresh`를 확장한다**

`Promise.all`에 두 건을 얹는다. **기존 두 건의 처리 방식은 바꾸지 않는다.**

```ts
  const refresh = useCallback(async () => {
    if (currentGroupId === null) {
      setTodos([]);
      setSchedules([]);
      setProposedCount(0);
      setDueSoon([]);
      setLoading(false);
      return;
    }
    try {
      const [nextTodos, nextSchedules, proposed, confirmed] = await Promise.all([
        getTodos(currentGroupId),
        getSchedules(currentGroupId),
        getCommitmentsPage(currentGroupId, 'proposed', COMMITMENT_LIMIT),
        getCommitments(currentGroupId, 'confirmed', COMMITMENT_LIMIT),
      ]);
      setTodos(nextTodos);
      setSchedules(nextSchedules);
      setProposedCount(proposed.meta?.total ?? proposed.data.length);
      setDueSoon(
        confirmed
          .filter((c) => c.is_overdue || c.is_due_soon)
          .sort((a, b) => (a.due_date ?? '9999-12-31').localeCompare(b.due_date ?? '9999-12-31')),
      );
      setError(null);
      setLastSyncedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : '업무 데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [currentGroupId]);
```

**`catch`에서 목록을 비우지 않는다.** 지금 코드가 이미 그런지 확인하고, 실패 시 `setTodos([])` 같은 게 있으면 **제거한다** — 폴링이 붙으면 일시적 실패마다 화면이 깜빡이며 비었다 찬다.

마감 정렬에서 `due_date`가 `null`인 것은 `'9999-12-31'`로 취급해 뒤로 보낸다. 마감 없는 약속이 마감 임박보다 위에 오면 안 된다.

- [ ] **Step 4: 폴링을 건다**

기존 마운트 `useEffect` 아래에 추가한다.

```ts
  // 화면에 "실시간"이라고 쓰여 있는데 지금까지 마운트 시 1회 조회뿐이었다.
  useEffect(() => {
    if (currentGroupId === null) return;

    const tick = () => {
      // 탭이 숨어 있으면 돌지 않는다. Render 무료 티어를 백그라운드 탭이
      // 계속 두드리게 두지 않는다.
      if (document.visibilityState === 'visible') refresh();
    };

    const id = setInterval(tick, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [currentGroupId, refresh]);
```

`clearInterval`과 `removeEventListener`를 빠뜨리면 라우트를 옮길 때마다 타이머와 리스너가 쌓인다.

- [ ] **Step 5: 컨텍스트 값에 노출한다**

`WorkspaceContextValue` 타입과 `value={{ ... }}` 양쪽에 `proposedCount`, `dueSoon`, `lastSyncedAt`을 추가한다. **기존 키를 지우거나 이름을 바꾸지 마라.**

- [ ] **Step 6: 폴링 갱신에 스피너가 뜨지 않는지 확인한다**

`loading`이 `refresh` 안에서 `setLoading(true)`로 매번 켜지면 30초마다 화면이 흔들린다. 지금 코드를 확인하고, `refresh` 시작부에 `setLoading(true)`가 있으면 **최초 1회만 켜지도록** 고친다 — 예를 들어 `finally`의 `setLoading(false)`만 남기고 초기값 `true`에 의존한다.

- [ ] **Step 7: 검증**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건. 포그라운드, timeout 300000ms.

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공. 포그라운드, timeout 600000ms.

Run: 워크트리 루트에서 `venv/bin/pytest tests/ -q`
Expected: 190 passed / 0 failed. 포그라운드, timeout 500000ms. 프론트만 고쳤으므로 그대로여야 한다.

- [ ] **Step 8: 커밋**

```bash
git add onque-frontend/components/WorkspaceContext.tsx
git commit -m "feat: 업무 데이터를 30초 폴링하고 약속 요약을 컨텍스트에 노출"
```

---

### Task 2: 우측 패널에 약속 요약과 시간 기반 표시

**Files:**
- Modify: `onque-frontend/components/SmartDashboardPanel.tsx`

**Interfaces:**
- Consumes: Task 1의 `proposedCount`, `dueSoon`, `lastSyncedAt`
- Produces: 없음 (말단 컴포넌트)

- [ ] **Step 1: 마감 문구 헬퍼를 만든다**

파일 상단, `formatDate` 옆에 둔다.

```ts
/** 마감까지 남은 날을 사람 말로. 서버 호출 없이 시간만으로 계산한다. */
function dueLabel(dueDate: string | null): string {
  if (!dueDate) return '기한 없음';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${dueDate}T00:00:00`);
  const days = Math.round((due.getTime() - today.getTime()) / 86_400_000);
  if (days === 0) return '오늘 마감';
  if (days > 0) return `${days}일 남음`;
  return `${-days}일 지남`;
}
```

- [ ] **Step 2: "N초 전 갱신"을 만든다**

같은 파일에 훅으로 둔다. 1초마다 다시 그리되 API를 호출하지 않는다.

```ts
/** lastSyncedAt 이후 흐른 시간을 1초마다 다시 계산한다. API 호출은 없다. */
function useElapsedLabel(lastSyncedAt: number | null): string | null {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (lastSyncedAt === null) return null;
  const secs = Math.floor((Date.now() - lastSyncedAt) / 1000);
  if (secs < 5) return '방금 갱신';
  if (secs < 60) return `${secs}초 전 갱신`;
  return `${Math.floor(secs / 60)}분 전 갱신`;
}
```

`useState`와 `useEffect`를 `react`에서 import한다.

- [ ] **Step 3: 헤더에 갱신 표시를 붙인다**

`SmartDashboardPanel.tsx`의 헤더 구역(`Smart Dashboard` / `실시간 업무 현황`이 있는 곳) 아래에 한 줄 추가한다. 기존 클래스 계열을 따른다.

```tsx
        {elapsed && (
          <p className="mt-1 font-mono text-[10px] text-foreground/30">{elapsed}</p>
        )}
```

`const elapsed = useElapsedLabel(lastSyncedAt);`를 컴포넌트 본문 최상단(다른 훅들과 같은 위치)에서 부른다.

- [ ] **Step 4: 약속 구역을 맨 위에 추가한다**

`error` 블록 아래, **`할 일` 구역보다 위**에 넣는다.

```tsx
      {(proposedCount > 0 || dueSoon.length > 0) && (
        <section className="border-b border-border px-5 py-4">
          {proposedCount > 0 && (
            <Link
              href="/dashboard"
              className="mb-3 flex items-center justify-between rounded-lg border border-accent/30 bg-accent/[0.06] px-3 py-2 transition hover:bg-accent/[0.12]"
            >
              <span className="text-xs font-bold text-foreground">확인 필요</span>
              <span className="font-mono text-xs text-accent">{proposedCount}건</span>
            </Link>
          )}

          {dueSoon.length > 0 && (
            <>
              <h3 className="mb-2 text-xs font-bold text-foreground/70">기한 주의 {dueSoon.length}</h3>
              <ul className="space-y-2">
                {dueSoon.slice(0, 5).map((c) => (
                  <li key={c.id} className="min-w-0">
                    <p className="truncate text-xs leading-relaxed text-foreground/90">{c.content}</p>
                    <p
                      className={`font-mono text-[10px] ${
                        c.is_overdue ? 'text-red-400' : 'text-accent'
                      }`}
                    >
                      {dueLabel(c.due_date)}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
```

`import Link from 'next/link';`를 추가한다.

**두 값이 모두 0이면 이 구역 전체가 렌더되지 않는다.** 빈 카드를 그리면 지금 화면이 바뀐다 — 그러면 안 된다.

클래스에 쓴 `accent`·`border`·`surface` 등이 이 프로젝트의 실제 토큰인지 `SmartDashboardPanel.tsx`와 `CommitmentPanel.tsx`에서 확인하고, 다르면 실제 이름으로 맞춘다. `text-accent`는 `CommitmentPanel.tsx:119`가 쓰는 것과 같은 계열이어야 한다.

- [ ] **Step 5: 컨텍스트에서 새 값을 꺼낸다**

```tsx
  const { todos, schedules, loading, error, toggleTodo, removeTodo, removeSchedule,
          proposedCount, dueSoon, lastSyncedAt } = useWorkspace();
```

기존 구조분해에 세 개만 더한다.

- [ ] **Step 6: 검증**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건. 포그라운드, timeout 300000ms.

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공. 포그라운드, timeout 600000ms.

Run: `cd onque-frontend && grep -rn "CommitmentPanel" components/SmartDashboardPanel.tsx`
Expected: 결과 없음 — 우측 패널이 대시보드 패널을 재사용하거나 복제하지 않았음을 확인한다.

Run: 워크트리 루트에서 `venv/bin/pytest tests/ -q`
Expected: 190 passed / 0 failed.

- [ ] **Step 7: 커밋**

```bash
git add onque-frontend/components/SmartDashboardPanel.tsx
git commit -m "feat: 우측 패널에 약속 요약과 마감 카운트다운, 갱신 시각 표시"
```

---

## 배포 절차

**마이그레이션 없음. 백엔드 변경 없음.** 프론트 전용이라 Vercel 배포만 의미가 있다.

1. `venv/bin/pytest tests/ -q` — 190 passed / 0 failed 확인
2. `cd onque-frontend && npx next build --webpack` — 성공 확인
3. `git push origin main` — Vercel이 배포

백엔드가 안 바뀌므로 배포 순서 문제가 없다.

4. 배포 확인 (로그인 필요):
   - 우측 패널 헤더에 "N초 전 갱신"이 1초마다 올라간다
   - 확인 필요 약속이 있으면 패널 맨 위에 건수가 뜨고, 누르면 `/dashboard`로 간다
   - 약속이 하나도 없는 그룹에서는 그 구역이 아예 안 보인다

## 검증 기준

1. 확인 필요·기한 임박이 둘 다 0건이면 약속 구역이 **렌더되지 않는다** (빈 카드가 아니라 없음)
2. `proposed`가 있으면 "확인 필요 N건"이 뜨고, N이 `meta.total`(20 상한이 아니라 전체)이다
3. 그 구역을 누르면 `/dashboard`로 이동한다
4. 대시보드에서 약속을 확정하면 30초 안에 우측 패널 숫자가 줄어든다
5. 탭을 숨기면 네트워크 요청이 멈추고, 돌아오면 즉시 한 번 갱신된다
6. 폴링이 실패해도 화면의 기존 목록이 비지 않는다
7. "N초 전 갱신"이 1초마다 올라가고 갱신 성공 시 리셋된다
8. 그룹을 바꾸면 약속·할 일·일정이 모두 그 그룹 것으로 바뀐다

**1번과 6번이 회귀 위험이 가장 크다.** 지금 화면을 바꾸지 않는 것과, 폴링이 조용히 화면을 비우지 않는 것.

## 범위 밖

| 항목 | 이유 |
|---|---|
| 우측 패널에서 확정·기각 | `CommitmentPanel`이 이미 한다. 두 벌로 갈라진다 |
| `GET /commitments`에 `sort` 추가 | `MAX_LIMIT=100` 우회로 충분. 100건을 넘기면 그때 |
| SSE / WebSocket | 폴링으로 부족한 것이 확인된 뒤에 |
| 할 일·일정·약속 통합 타임라인 | 별도 건 |
| 새 항목 진입 하이라이트 | 이전 목록과 diff를 들고 있어야 해서 상태가 늘어난다. 카운트다운·갱신 표시로 "살아 있음"은 이미 전달된다 |
