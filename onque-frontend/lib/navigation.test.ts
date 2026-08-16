import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { NAV_ITEMS } from './navigation';

// vitest는 프로젝트 루트(onque-frontend/)를 cwd로 실행한다.
const APP_DIR = join(process.cwd(), 'app');

describe('NAV_ITEMS', () => {
  it('모든 href가 실제 라우트를 가리킨다', () => {
    for (const item of NAV_ITEMS) {
      const segment = item.href.replace(/^\//, '');
      expect(
        existsSync(join(APP_DIR, segment, 'page.tsx')),
        `${item.href} 에 해당하는 app/${segment}/page.tsx 가 없다`,
      ).toBe(true);
    }
  });

  it('href가 중복되지 않는다', () => {
    const hrefs = NAV_ITEMS.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it('label·shortLabel·description이 모두 비어 있지 않다', () => {
    for (const item of NAV_ITEMS) {
      expect(item.label.length, `${item.href} label`).toBeGreaterThan(0);
      expect(item.shortLabel.length, `${item.href} shortLabel`).toBeGreaterThan(0);
      expect(item.description.length, `${item.href} description`).toBeGreaterThan(0);
    }
  });

  it('내용 메뉴만 담는다 — 계정 동작(/profile)은 여기 없다', () => {
    expect(NAV_ITEMS.map((i) => i.href)).not.toContain('/profile');
  });
});
