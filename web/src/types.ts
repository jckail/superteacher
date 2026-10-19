/** API DTOs mirror the FastAPI response schemas. Dates are ISO strings on the wire. */
export type Risk = 'unknown' | 'on_track' | 'watch' | 'at_risk';
export type AssessmentKind = 'test' | 'quiz' | 'homework' | 'project';
export type AttendanceStatus = 'present' | 'absent' | 'tardy' | 'excused';
export interface SectionOut { id: string; name: string; course_id: string }
export interface CourseOut { id: string; name: string; sections: SectionOut[] }
export type Course = CourseOut;
export type Section = SectionOut;
export interface StudentSummary {
  id: string; name: string; grade_level: number; section_id: string; section: string;
  course_id: string; course: string; average: number | null; letter: string | null;
  gpa: number | null; trend: number | null; attendance_rate: number | null;
  homework_rate: number | null; missing: number; risk: Risk; risk_reasons: string[];
}
export type RosterSort = 'name' | 'section' | 'average' | 'trend' | 'attendance_rate' | 'homework_rate' | 'risk';
export type RosterDirection = 'asc' | 'desc';
export interface StudentPage {
  items: StudentSummary[]; next_cursor: string | null; as_of: string;
  total_matches: number; total_scoped: number;
}
export interface ScoreOut { assessment_id: string; title: string; kind: AssessmentKind; due_date: string; max_points: number; points: number | null; pct: number | null }
export interface GradeHistorySection { section_id: string; section: string; course_id: string; course: string; scores: ScoreOut[] }
export interface GradeHistoryOut { student_id: string; active_section_id: string; sections: GradeHistorySection[] }
export interface AttendanceOut { day: string; status: AttendanceStatus }
export interface NoteOut { id: string; body: string; created_at: string }
export interface StudentDetail extends StudentSummary { as_of: string; scores: ScoreOut[]; attendance: AttendanceOut[]; absences: number; tardies: number; notes: NoteOut[] }
export interface AssessmentOut { id: string; section_id: string; title: string; kind: AssessmentKind; max_points: number; due_date: string }
export interface GradebookRow { student_id: string; name: string; average: number | null; letter: string | null; points: Record<string, number | null> }
export interface Gradebook { as_of: string; section: SectionOut; assessments: AssessmentOut[]; rows: GradebookRow[] }
export interface ScoreEntry { student_id: string; points: number | null }
export interface AttendanceMark { student_id: string; status: AttendanceStatus }
export interface AttendanceSheetRow { student_id: string; name: string; status: AttendanceStatus | null }
export interface AttendanceSheet { section: SectionOut; day: string; rows: AttendanceSheetRow[] }
export interface Overview { as_of: string; students: number; average: number | null; attendance_rate: number | null; homework_rate: number | null; at_risk: number; watch: number; on_track: number; unknown: number; distribution: Record<string, number>; attention: StudentSummary[] }
export interface Insight { as_of?: string; headline: string; strengths: string[]; concerns: string[]; actions: string[]; source: 'ai' | 'rules'; model: string | null; generated_at: string | null }
export interface ImportResult { created: number; skipped: string[] }
export type AuthMode = 'passcode' | 'accounts' | 'public_demo';
export interface AuthConfig { auth_mode: AuthMode }
export interface AuthMe { authenticated: true; auth_required: boolean; email?: string | null }
export interface AssessmentStat { id: string; title: string; kind: AssessmentKind; due_date: string; max_points: number; graded: number; average: number | null; median: number | null; min: number | null; max: number | null; missing_pct: number | null }
export interface AttendanceDay { day: string; rate: number | null; marked: number; absent: number }
export interface AttentionItem { id: string; name: string; risk: Risk; average: number | null; reasons: string[] }
export interface ClassSummary { as_of: string; section_id: string; section: string; course: string; students: number; unknown: number; on_track: number; watch: number; at_risk: number; average: number | null; distribution: Record<string, number>; assessments: AssessmentStat[]; attention: AttentionItem[]; attendance: AttendanceDay[]; attendance_rate: number | null }
export type Tone = 'warm' | 'neutral' | 'concerned';
export interface ParentUpdateOut { subject: string; body: string; source: 'ai' | 'template' }

/** Request DTOs. Optional fields have backend defaults; null is never a patch omission. */
export interface CourseIn { name: string }
export interface SectionIn { course_id: string; name: string }
export interface StudentIn { name: string; grade_level: number; section_id: string }
export type StudentPatch = Partial<StudentIn>;
export interface NoteIn { body: string }
export interface AssessmentIn {
  title: string;
  kind?: AssessmentKind;
  max_points?: number;
  due_date?: string;
}
export type AssessmentPatch = Partial<Required<AssessmentIn>>;
export interface ScoresIn { scores: ScoreEntry[] }
export interface AttendanceIn { day?: string; marks: AttendanceMark[] }
export interface ImportIn { csv: string }
export interface ParentUpdateIn { tone?: Tone; expected_section_id?: string | null }
export interface LoginIn { password: string }
export interface LogoutOut { authenticated: false }
export interface HealthOut { status: 'healthy' | 'unhealthy'; database: string; ai: boolean }
export interface VersionOut { version: string }

/** WebSocket frames, independent from messages displayed in the conversation. */
export interface ChatMessage { role: 'user' | 'assistant'; text: string }
export type ChatClientEvent =
  | { content: string; student_id?: string; tool_events?: boolean }
  | { type: 'reset' };
export type ChatServerEvent =
  | { type: 'delta'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

/** Conventional names for page consumers; the Out names match Python schemas. */
export type RosterStudent = StudentSummary;
export type OverviewResponse = Overview;
export type InsightResponse = Insight;

export interface SchoolCalendar { timezone: string; today: string }
