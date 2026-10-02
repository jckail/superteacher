import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

/** Console messages we expect and tolerate. Everything else fails the test. */
const ALLOWED: RegExp[] = [
  // The login gate probes /api/auth/me before a session exists; the 401 is the designed signal.
];

type Fixtures = {
  /** Push extra allowed console-error patterns for this test (e.g. a deliberate 401 on /api/auth/login). */
  allowConsole: (re: RegExp) => void;
  api: Api;
};

export const test = base.extend<Fixtures>({
  allowConsole: async ({}, use) => {
    // value is filled by the auto fixture below through closure on a shared array
    await use((re) => extra.push(re));
  },
  api: async ({ request }, use) => use(new Api(request)),
  page: async ({ page }, use, info) => {
    const errors: string[] = [];
    extra.length = 0;
    page.on('console', (m) => {
      if (m.type() !== 'error') return;
      const url = m.location().url ?? '';
      const text = m.text();
      // expected: the pre-login /auth/me probe answers 401 and Chrome logs the failed resource load
      if (/status of 401/.test(text) && /\/api\/auth\/me/.test(url)) return;
      if ([...ALLOWED, ...extra].some((re) => re.test(text) || re.test(url))) return;
      errors.push(`${text} (${url})`);
    });
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    await use(page);
    expect(errors, `unexpected console errors in "${info.title}"`).toEqual([]);
  },
});
const extra: RegExp[] = [];
export { expect };

let counter = 0;
/** Unique suffix so tests never collide on names inside the shared DB. */
export const uid = (p = 'x') => `${p}${Date.now().toString(36)}${(counter++).toString(36)}`;

const H = { 'X-Requested-With': 'superteacher' };

export interface Classroom {
  courseId: string;
  courseName: string;
  sectionId: string;
  sectionName: string;
  students: { id: string; name: string }[];
}

/** Thin typed wrapper over the REST API for arranging test data (the UI is what the tests then exercise). */
export class Api {
  constructor(private r: APIRequestContext) {}

  private async json<T = any>(res: Awaited<ReturnType<APIRequestContext['post']>>): Promise<T> {
    if (!res.ok()) throw new Error(`${res.url()} -> ${res.status()} ${await res.text()}`);
    return (await res.json()) as T;
  }

  async classroom(opts: { studentNames?: string[]; course?: string; section?: string } = {}): Promise<Classroom> {
    const courseName = opts.course ?? uid('Course ');
    const sectionName = opts.section ?? 'Period 1';
    const course = await this.json(await this.r.post('/api/courses', { data: { name: courseName }, headers: H }));
    const section = await this.json(await this.r.post('/api/sections', { data: { course_id: course.id, name: sectionName }, headers: H }));
    const students = [];
    for (const name of opts.studentNames ?? []) {
      const s = await this.json(await this.r.post('/api/students', { data: { name, grade_level: 9, section_id: section.id }, headers: H }));
      students.push({ id: s.id as string, name });
    }
    return { courseId: course.id, courseName, sectionId: section.id, sectionName, students };
  }

  async assessment(sectionId: string, title: string, max = 10, kind = 'homework') {
    return this.json(await this.r.post(`/api/sections/${sectionId}/assessments`, { data: { title, kind, max_points: max, due_date: new Date().toISOString().slice(0, 10) }, headers: H }));
  }

  async gradebook(sectionId: string) {
    return this.json(await this.r.get(`/api/sections/${sectionId}/gradebook`));
  }

  async attendance(sectionId: string, day: string) {
    return this.json(await this.r.get(`/api/sections/${sectionId}/attendance?day=${day}`));
  }

  async students(params = '') {
    return this.json<any[]>(await this.r.get(`/api/students${params}`));
  }
  async courses() {
    return this.json<any[]>(await this.r.get('/api/courses'));
  }
}

/** Make the app open on this course/section (the UI persists its scope in localStorage). */
export async function useClassroom(page: Page, c: Pick<Classroom, 'courseId' | 'sectionId'>) {
  await page.addInitScript((sel) => {
    try { localStorage.setItem('st-scope', JSON.stringify(sel)); } catch { /* ignore */ }
  }, { courseId: c.courseId, sectionId: c.sectionId });
}

export async function setTheme(page: Page, theme: 'light' | 'dark') {
  await page.addInitScript((t) => {
    try { localStorage.setItem('st-theme', t); } catch { /* ignore */ }
  }, theme);
}

export const utcToday = () => new Date().toISOString().slice(0, 10);
export const utcDaysAgo = (n: number) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);

/** Wait until the SPA has finished its initial data loading (no busy skeletons left). */
export async function settled(page: Page) {
  await expect(page.locator('[aria-busy="true"][role="status"]')).toHaveCount(0);
}
