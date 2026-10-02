import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, type TestInfo } from '@playwright/test';
import { appendFileSync, mkdirSync } from 'node:fs';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];

export const VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 },
} as const;

/** Run axe on the current page state, log every violation to test-results/axe.jsonl, fail on serious/critical. */
export async function auditA11y(page: Page, label: string, info: TestInfo, exclude: string[] = []) {
  await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
  await page.evaluate(() => document.fonts?.ready);
  let b = new AxeBuilder({ page }).withTags(TAGS);
  for (const sel of exclude) b = b.exclude(sel);
  const { violations } = await b.analyze();
  mkdirSync('test-results', { recursive: true });
  for (const v of violations) {
    appendFileSync(
      'test-results/axe.jsonl',
      JSON.stringify({ label, id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => ({ target: n.target, html: n.html.slice(0, 160), summary: n.failureSummary?.split('\n').slice(0, 3).join(' | ') })) }) + '\n',
    );
  }
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  await info.attach(`axe-${label}`, { body: JSON.stringify(violations, null, 2), contentType: 'application/json' });
  expect(
    blocking.map((v) => `${v.id} [${v.impact}] x${v.nodes.length}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' ; ')}`),
    `serious/critical axe violations on ${label}`,
  ).toEqual([]);
}
