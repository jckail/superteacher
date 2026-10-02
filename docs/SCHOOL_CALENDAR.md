# School calendar

Set `SCHOOL_TIMEZONE` to an IANA timezone, for example `America/Los_Angeles`.
The default is `UTC`. Unknown zones fail settings validation at startup. The
bounded `tzdata` dependency provides timezone data when the container operating
system does not include it. Changing the setting requires restarting the app.

Authenticated `GET /api/calendar` returns the configured `timezone` and the
school's current ISO `today`. The browser uses this date for attendance and new
assignment defaults. School dates are calendar dates, with no conversion through
the browser's timezone. The server timezone and the teacher's device timezone do
not control academic cutoffs.

Each HTTP operation captures one school date. Attendance records dated after it
are excluded from current rates and absence/tardy counts. Work due after it is
excluded from current averages, missing counts, homework completion and risk.
Due dates equal to the school date count as due. Future scores remain visible as
raw records; ungraded future work is labeled as not yet due. Class summary
assessment statistics can show recorded future scores, but future missing
percentages remain null. Explicit historical dates passed to metrics and reports
remain authoritative, including prompt labels derived from those metrics.

`StudentDetail.as_of` and class-summary `as_of` identify the date underlying their
numbers. AI snapshots capture the same school clock, and insight fingerprints
include the metric date so yesterday's cached insight is invalidated. Notes,
cache generation timestamps and authentication timestamps remain UTC.

The calendar context is isolated per app instance and propagates to async tasks
and worker threads. Websocket connections retain the app timezone, while each
snapshot obtains a fresh date so a connection can continue across midnight.
