# Offline AI grounding evaluation

Run from the repository root:

```sh
python -m pytest tests/test_ai_grounding.py -q
```

The synthetic classroom in `tests/fixtures/ai_grounding/classroom.json` contains no real student data. All grading calculations are anchored to October 1, 2026, so future work remains future when the suite runs later. The tests exercise current ORM rows, context builders, actual tool dispatch, the chat tool loop, insight generation and parent draft generation. They make no provider requests and require no API credentials.

The expected average is hand calculated: `(0.40 × 80 + 0.20 × 50 + 0.25 × 100) / 0.85 = 78.823529…%`. Missing homework is excluded from the graded average under the application's policy, but counts in completion: one submitted of two due homework assignments gives 50%. Attendance is two attended (present and tardy) of three counted sessions; excused attendance is excluded, giving 66.666667%. Exactly one assignment is overdue and missing. The early submitted project and upcoming homework are excluded from present grade, trend and completion calculations. No trend is available with only three graded, due assessments.

| Evaluation | Evidence checked |
| --- | --- |
| Exact tool claims | Hand-calculated average, letter, attendance, completion and missing count |
| Fallback drafts and insight cards | Supported numeric claims, absence of unsupported excellence or improvement claims, all draft tones |
| Missing versus future work | Upcoming ungraded homework must be labeled as not yet due; overdue homework remains missing |
| Record isolation | Focus record and exact student lookup exclude the other student's detailed record; teacher chat intentionally retains the class roster |
| Malicious student, course, section, title and note text | Rendered context remains parseable with no forged system elements; injected text remains data; chat tool results remain tool-result messages |
| Parent privacy | Confidential teacher notes and another student's identifying text are absent from the actual request sent to the model |
| Structured output | Malformed parent and insight shapes fall back to evidence-based rules; malformed insights are never cached; valid fenced JSON is accepted |
| Empty evidence | Drafts acknowledge insufficient graded work without inventing grades or excellent attendance |

These checks validate the application's data and transport boundaries. Scripted model responses only inspect the application's handling of messages and validation. They **do not establish that a real model will resist prompt injection, avoid speculation, obey privacy instructions, or produce factually correct prose**. Structurally valid generated JSON currently receives shape validation, not semantic fact checking. A fabricated but well-formed claim can still be accepted and cached. Real model evaluation would require separate, explicitly approved provider calls and adjudicated outputs.

Absent score rows are not treated as missing assignments by the application's metrics. Normal enrollment and assessment creation explicitly create null score rows for assigned work, which the fixture uses for missing work. Attendance includes recorded sessions through the evaluation date and excludes future entries. It is not restricted to a recent attendance window. Missing-work policy should be reconsidered explicitly if imports or enrollment history introduce different meanings.

## Provider configuration review (2026-10-01)

The native default model IDs `claude-sonnet-5-5` and
`claude-haiku-4-5-20251001` appear in the current official
[Anthropic model overview](https://platform.claude.com/docs/en/models/overview).
No default-model change was needed. Documentation establishes supported IDs,
not successful application calls or measured output quality. The native settings
check found no configured AI provider credential (only its presence was checked;
no secret values were displayed). Real-provider grounding, tool and injection
acceptance therefore remain unexecuted. Existing fake-provider and offline
fixture results must not be presented as real-provider evaluation.
