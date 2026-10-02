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

## Replay captured answers without provider calls

The bounded next slice of [#37](https://github.com/jckail/superteacher/issues/37) adds six
golden teacher questions in `tests/fixtures/ai_grounding/questions.json`, pinned to the
existing classroom fixture's canonical SHA-256. Questions cover current grade, attendance,
homework, future work, parent privacy and private-note injection. The facts are hand
adjudicated against the calculations above. Changing the classroom requires a reviewed,
versioned rubric update; the runner refuses fixture drift.

Run the hand-authored **synthetic demonstration** (not a model capture):

```sh
python -m superteacher.evaluate_ai \
  --answers tests/fixtures/ai_grounding/example_answers.json \
  --output /private/results/ai-evaluation-unique-run.json
```

Use a protected results directory that already exists. The output file must be new:
the runner publishes a complete `0600` report without replacing a previous report or
symlink. Reports contain timestamps, scorer/rubric/classroom/bundle hashes, per-answer hashes,
case IDs and finding codes, **not answer text or source paths**. Keep captures private
too, and retain reports under the actual approved policy. Comparing reports with the
same scorer/rubric/classroom hashes makes regressions visible; changed hashes indicate a
different evaluation, rather than an improvement on the same gold set.

A replay input must contain exactly `provenance` (`synthetic` or `unverified_capture`)
and an `answers` array, with exactly one `{"case_id": "…", "answer": "…"}` object per
golden question. Each answer is limited to 8000 characters, and the input file to
1 MiB. For separately authorized model runs, capture answers against the same fixture,
cutoff and questions, label the input `unverified_capture`, and record provider/model,
prompt version, request IDs, actual usage/cost and approvals in protected operator
evidence. This runner cannot authenticate a capture's origin or reconstruct its cost.

Exit codes: `0` means the configured lexical checks passed; `1` means one or more
checks failed (a report is still written); `2` means invalid input, fixture drift or
report publication failure. The replay makes **zero provider calls**, loads no app
database or credentials and has no provider-spend path. There is no nightly provider
job or automatic production gate. Provider execution still needs explicit ownership,
real credentials and an enforced budget outside this offline tool.

The checks require case-specific fact phrases and cover numeric tokens only inside
explicit gold value groups. An added number cannot pass merely because that value
appears elsewhere in the gold record. Common spelled numbers/ordinals and Unicode
digit forms are checked conservatively; ASCII and typographic apostrophes are normalized
equivalently. Known peer names/private markers are forbidden;
disclosures produce finding codes without copying the disclosed content into reports.

**Every report requires human review**, even if all lexical checks pass. These narrow
patterns can reject correct alternate wording and do not prove numerical reasoning,
detect every name, catch paraphrased private notes, resolve negation or score usefulness.
Review all names, numbers, claims, privacy and teacher usefulness against the records.
Unknown names and nonnumeric speculation can pass the lexical checks; a test preserves
this visible limitation. The report explicitly says `real_model_acceptance: not_established`.
Real-model factuality/privacy evaluation and a validated comprehensive semantic scorer
remain open in #37. This replay changes no application AI acceptance/cache behavior.

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
