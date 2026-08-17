import { describe, expect, it } from 'vitest';
import { buildSweepStatus, formatElapsed, formatResetTime } from './sweep-status';
import type { SweepMeta } from './api';

const NOW = Date.parse('2026-08-16T12:00:00Z');

function meta(overrides: Partial<SweepMeta> = {}): SweepMeta {
  return {
    last_at: '2026-08-16T11:48:00Z',
    scanned: 34,
    found: 2,
    ...overrides,
  };
}

describe('formatElapsed', () => {
  it('1분 미만은 "방금"으로 뭉갠다', () => {
    expect(formatElapsed('2026-08-16T11:59:30Z', NOW)).toBe('방금');
  });

  it('서버 시계가 앞서 음수가 되어도 "방금"이다', () => {
    expect(formatElapsed('2026-08-16T12:05:00Z', NOW)).toBe('방금');
  });

  it('분·시간·일 단위로 올라간다', () => {
    expect(formatElapsed('2026-08-16T11:48:00Z', NOW)).toBe('12분 전');
    expect(formatElapsed('2026-08-16T09:00:00Z', NOW)).toBe('3시간 전');
    expect(formatElapsed('2026-08-14T12:00:00Z', NOW)).toBe('2일 전');
  });

  it('파싱할 수 없는 값은 null이다 — 엉뚱한 시각을 지어내지 않는다', () => {
    expect(formatElapsed('언젠가', NOW)).toBeNull();
  });
});

describe('buildSweepStatus', () => {
  it('찾은 게 있으면 시각과 성과를 한 줄로 붙인다', () => {
    expect(buildSweepStatus(meta(), NOW).line).toBe('12분 전 · 대화 34개에서 2건 찾음');
  });

  it('훑었지만 못 찾았으면 그 사실을 말한다', () => {
    expect(buildSweepStatus(meta({ found: 0 }), NOW).line).toBe(
      '12분 전 · 대화 34개 확인, 새 약속 없음',
    );
  });

  it('한 번도 안 훑었으면 보여줄 줄이 없다', () => {
    expect(buildSweepStatus(meta({ last_at: null }), NOW).line).toBeNull();
  });

  it('메타가 없으면 보여줄 줄이 없다', () => {
    expect(buildSweepStatus(null, NOW)).toEqual({ line: null });
  });

  it('개수가 비면 시각만 말한다 — 없는 숫자를 지어내지 않는다', () => {
    expect(buildSweepStatus(meta({ scanned: null, found: null }), NOW).line).toBe('12분 전 확인함');
  });
});

describe('formatResetTime', () => {
  it('ISO 문자열을 사람이 읽는 시각으로 바꾼다', () => {
    // 2026-08-18T00:00:00Z = KST 오전 9시
    expect(formatResetTime('2026-08-18T00:00:00Z')).toBe('8월 18일 오전 9시');
  });

  it('파싱할 수 없으면 null이다 — 엉뚱한 시각을 지어내지 않는다', () => {
    expect(formatResetTime('언젠가')).toBeNull();
  });
});
