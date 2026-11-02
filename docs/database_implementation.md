# MediCode Database Implementation Guide

**Audience:** Backend contributors\
**Status:** Implementation handoff / proposed schema contract\
**Database:** PostgreSQL 15+\
**ORM:** SQLAlchemy 2.x\
**Migrations:** Alembic\
**Backend:** FastAPI\
**Last reviewed:** 2 November 2026

------------------------------------------------------------------------

## 1. Purpose

This document gives the backend team a shared plan for implementing
MediCode's database. It describes the entities, relationships,
constraints, implementation order, and engineering rules contributors
must follow.

MediCode is an educational coding and lab-assessment platform for
students, faculty, HODs, TPOs, and administrators. The expected
population is 2,000+ registered users. Users will practise independently
and participate in scheduled lab sessions.

This is a relational application. Use PostgreSQL as the system of
record. Do not use MongoDB as the primary database for users, academic
relationships, enrollments, attendance, grading, or submissions.

**Important:** This is an implementation guide, not a claim that every
listed feature is already implemented. Build in phases. Do not invent
fields or relationships without discussing them with the backend lead.

------------------------------------------------------------------------

## 2. Technology decisions

  -----------------------------------------------------------------------
  Concern                             Decision
  ----------------------------------- -----------------------------------
  Database                            PostgreSQL 15+ (use a currently
                                      supported stable release)

  ORM                                 SQLAlchemy 2.x

  Migrations                          Alembic

  API                                 FastAPI

  Database driver                     `asyncpg` for async SQLAlchemy, if
                                      the application uses async DB
                                      sessions

  Primary keys                        UUID for user-generated/domain
                                      entities; integer identity is
                                      acceptable for small static lookup
                                      tables such as `roles`

  Data model                          Relational, normalized; aim for 3NF
                                      where appropriate

  JSON                                PostgreSQL `JSONB` only for
                                      genuinely variable structured
                                      metadata, not as a substitute for
                                      relational tables

  File/object storage                 S3-compatible storage or MinIO for
                                      large files; store object
                                      keys/metadata in PostgreSQL

  Background processing               Redis + Celery in the phase that
                                      introduces asynchronous grading and
                                      other background jobs
  -----------------------------------------------------------------------

Do not use SQLite for shared development or production. It is acceptable
for isolated unit tests only if the test suite also runs integration
tests against PostgreSQL.

------------------------------------------------------------------------

## 3. Core modelling principles

1.  **Identity is not academic membership.** A login account, a person's
    profile, their role, their academic placement, and their course
    enrollments are different concepts.
2.  **A course is not a course offering.** A course is the reusable
    subject definition. An offering is that course delivered to a
    particular academic term, semester, section, or cohort.
3.  **Access is relationship-based.** A student sees an offering because
    they are enrolled in it. A faculty member manages it because they
    are assigned to it. A role alone does not grant access to every
    course.
4.  **Keep history.** Semester, section, faculty assignments, elective
    choices, attendance, and submissions can change or accumulate. Do
    not overwrite history when a new academic term begins.
5.  **Keep raw events.** Attendance records and submission/test results
    are the source records. Percentages, totals, streaks, and dashboard
    counters are derived values or caches.
6.  **Do not execute untrusted code in the API process.** The API
    records a submission and schedules execution through a queue/worker
    architecture.
7.  **The database is the source of truth.** Redis may cache or
    coordinate work, but it must not be the only place where durable
    academic records exist.

------------------------------------------------------------------------

## 4. Logical database modules

### 4.1 Identity and authorization

#### `roles`

Defines the platform role taxonomy.

Suggested roles from the backend architecture: - `SUPER_ADMIN` -
`INSTITUTE_ADMIN` - `FACULTY` - `STUDENT`

HOD and TPO responsibilities need a final permission decision. They may
be represented as separate roles or as scoped permissions/assignments,
depending on whether they have distinct platform-wide capabilities. Do
not add arbitrary role strings in application code.

Suggested fields: - `id` --- integer primary key - `name` --- unique,
not null - `description` --- nullable - `created_at`

#### `logins`

Authentication credentials and account status only.

Suggested fields: - `id` --- UUID primary key - `email` --- unique, not
null, normalized to lowercase - `password_hash` --- nullable only if an
approved external SSO flow requires passwordless accounts - `is_active`
--- not null, default true - `created_at`, `updated_at`, `last_login_at`

Never store plaintext passwords. Do not put profile or academic details
in this table.

#### `profiles`

One-to-one person record linked to a login.

Suggested fields: - `id` --- UUID primary key - `login_id` --- unique FK
to `logins.id` - `role_id` --- FK to `roles.id` - `department_id` --- FK
to `departments.id`, nullable where appropriate - `full_name` - `phone`
--- nullable, only if required - `created_at`, `updated_at`

Do not put a mutable `current_semester` in `profiles` as the
authoritative source. Do not put a faculty's course list or a student's
elective list in this table.

#### `departments`

Institutional departments such as CSE.

Suggested fields: - `id` UUID PK - `name` not null - `code` unique, not
null - timestamps

If multiple institutes/tenants are supported, department uniqueness must
be scoped to the tenant.

#### Optional role-specific detail tables

Add `student_details` and `faculty_details` only for attributes
genuinely specific to those user types.

`student_details` may contain: - `profile_id` PK/FK to `profiles.id` -
`enrollment_number` / roll number, unique within the correct
institutional scope - `admission_year` - `program_id` - other stable
student-specific identifiers

`faculty_details` may contain: - `profile_id` PK/FK - employee/staff
identifier - designation - other stable faculty-specific details

Do not create separate student and faculty identity systems. Keep
`profiles` as the common FK target for activity and authorization.

------------------------------------------------------------------------

### 4.2 Academic organization

#### `programs`

Degree/program definitions, such as B.Tech Computer Science.

Suggested fields: - `id` UUID PK - `department_id` FK - `name` -
`code` - `duration_semesters` - `is_active`

#### `academic_terms`

Represents an academic period, not a student's permanent batch.

Suggested fields: - `id` UUID PK - `name` (e.g. `2026-27 Odd`) -
`academic_year_start` - `academic_year_end` - `term_type` (ODD / EVEN /
SUMMER, or an agreed enum/check constraint) - `starts_on`, `ends_on` -
`is_active`

#### `student_term_enrollments`

Records a student's academic placement for a particular term. This is
how the system knows the student's semester and section at that point in
time.

Suggested fields: - `id` UUID PK - `student_profile_id` FK to
`profiles.id` - `academic_term_id` FK to `academic_terms.id` -
`program_id` FK to `programs.id` - `semester_number` - `section` -
`status` (ACTIVE / COMPLETED / WITHDRAWN / REPEATING, as approved) -
timestamps

Constraints: - Unique student + academic term, unless the institution
explicitly supports multiple program placements in one term. -
`semester_number` must be within the program's allowed range. - Preserve
previous term rows; do not update the previous row to the new
semester. - A backlog/repeat policy must be agreed before deciding
whether a student can have multiple active term placements.

Admission year identifies the student's cohort; it does **not** reliably
determine their current semester. Academic progression records are
authoritative.

------------------------------------------------------------------------

### 4.3 Courses, offerings, faculty assignment and student access

This is a critical part of the schema.

#### `courses`

Reusable subject/catalogue record.

Suggested fields: - `id` UUID PK - `department_id` FK - `course_code` -
`title` - `description` - `credits` (nullable if not needed) -
`is_active` - timestamps

A course does not permanently belong to one semester, section, or
faculty member.

#### `course_offerings`

A specific delivery of a course during an academic term.

Suggested fields: - `id` UUID PK - `course_id` FK to `courses.id` -
`academic_term_id` FK to `academic_terms.id` - `program_id` FK to
`programs.id` - `semester_number` - `section` (nullable if offering is
not section-specific) - `offering_code` or cohort identifier if needed -
`status` (DRAFT / OPEN / ACTIVE / COMPLETED / CANCELLED) - timestamps

Examples: - DBMS Lab, 2026-27 Odd, B.Tech CSE, Semester 5, Section A -
DBMS Lab, 2026-27 Odd, B.Tech CSE, Semester 5, Section B

The same course can have many offerings over time and across sections.

#### `offering_faculty`

Many-to-many assignment between faculty profiles and course offerings.

Suggested fields: - `id` UUID PK, or composite key if the team chooses
that convention - `offering_id` FK to `course_offerings.id` -
`faculty_profile_id` FK to `profiles.id` - `assignment_role` (INSTRUCTOR
/ COORDINATOR, if required) - `assigned_at`, `ended_at` - `is_active`

Constraint: prevent duplicate active assignment of the same faculty
member to the same offering.

Do not use `courses.faculty_id` as the only assignment model if an
offering may have multiple instructors or the same course may be taught
by different faculty in different sections.

#### `course_enrollments`

Links students to specific offerings and controls course access.

Suggested fields: - `id` UUID PK - `offering_id` FK to
`course_offerings.id` - `student_profile_id` FK to `profiles.id` -
`enrollment_status` (PENDING / ACTIVE / DROPPED / COMPLETED) -
`enrolled_at` - grading fields only where they truly belong to this
offering relationship, such as approved viva marks, remarks, and
approval state - timestamps

Constraints: - Unique `(offering_id, student_profile_id)`. - Enforce
that the linked profile has the STUDENT role. - Do not allow enrollment
into a cancelled/closed offering without an authorized override. -
Preserve dropped/completed enrollments for history; do not hard-delete
academic records.

**Access rule:** A student's course access is checked against an active
`course_enrollments` record. A faculty member's management access is
checked against an active `offering_faculty` assignment. HOD/admin
access is governed by explicit scoped permissions.

------------------------------------------------------------------------

### 4.4 Electives

Electives change by term and students may select different options. Do
not hardcode elective choices in `profiles`.

Recommended entities:

#### `elective_groups`

Defines a choice requirement for a program/term,
e.g. `Professional Elective 1`.

Fields may include: - `id` - `academic_term_id` - `program_id` -
`semester_number` - `name` - `min_selections`, `max_selections` -
selection open/close dates - approval requirement

#### `elective_options`

Links eligible courses or offerings to an elective group.

Fields: - `id` - `elective_group_id` - `course_id` or `offering_id`
(choose based on whether students select a subject before offerings are
created) - eligibility/capacity metadata if needed

#### `elective_selections`

Records each student's choice and its state.

Fields: - `id` - `elective_group_id` - `student_profile_id` - selected
option FK - `status` (DRAFT / SUBMITTED / APPROVED / REJECTED /
CANCELLED) - selected_at, approved_by, approved_at

After approval, create or activate the corresponding
`course_enrollments` row. Do not treat an unapproved selection as course
access.

The exact elective workflow must be confirmed with the academic team
before implementation. For a very small first release, a simpler
selection table may be enough; do not overbuild a generic rules engine
prematurely.

------------------------------------------------------------------------

### 4.5 Learning content

Preserve the existing academic content hierarchy:

`courses → labs → experiments → problems → test_cases`

With the new offering model, content should normally attach to the
reusable `course` so it can be reused across offerings. If a lab or
problem is specific to one term/offering, model that explicitly rather
than duplicating the course catalogue.

#### `labs`

-   `id` UUID PK
-   `course_id` FK
-   `title`
-   `description`
-   `sort_order`
-   `is_published`
-   timestamps

#### `experiments`

-   `id` UUID PK
-   `lab_id` FK
-   `title`
-   `description`
-   `sort_order`
-   `is_published`
-   timestamps

#### `problems`

-   `id` UUID PK
-   `experiment_id` FK
-   `title`, `statement`
-   `difficulty`
-   `time_limit_ms` or agreed unit
-   `memory_limit_mb`
-   supported language metadata
-   `is_published`
-   timestamps

#### `test_cases`

-   `id` UUID PK
-   `problem_id` FK
-   `is_hidden`
-   small inline input/expected output fields, nullable
-   object-storage keys for large input/output payloads, nullable
-   points/weight if required
-   sort order

Never return hidden test inputs or expected outputs to student-facing
API responses. Keep hidden test access restricted to the grading
worker/service.

------------------------------------------------------------------------

### 4.6 Submissions and grading

#### `submissions`

An append-only attempt record for a student's attempt at a problem.

Suggested fields: - `id` UUID PK - `student_profile_id` FK -
`problem_id` FK - `course_enrollment_id` FK where the attempt is
associated with a course offering - `source_code` - `language` -
`status` (QUEUED / RUNNING / ACCEPTED / WRONG_ANSWER / TLE / MLE /
RUNTIME_ERROR / COMPILE_ERROR / INTERNAL_ERROR, final enum to be
agreed) - `created_at`, `started_at`, `finished_at` - aggregate
execution time and memory usage, nullable until evaluation finishes -
idempotency key or request identifier if needed

Apply a database constraint on source-code size (the architecture
specification proposes a 64 KiB limit; confirm this with the product
requirement).

#### `submission_test_results`

One row per test case evaluated for a submission.

Suggested fields: - `id` UUID PK - `submission_id` FK - `test_case_id`
FK - `status` - `execution_time_ms` - `memory_used_mb` - stdout/stderr
fields with strict output limits, or object-storage keys for larger
diagnostic logs - `created_at`

Use a uniqueness rule for `(submission_id, test_case_id)` if each test
case is executed only once per attempt. If retries/re-runs are
supported, include an attempt number instead.

Submission records should not be overwritten with a new attempt. Each
attempt is a separate record.

#### Grade aggregation

Raw submissions and assessment records are the evidence. A total score
may be cached on an enrollment or materialized separately, but it must
be recalculable from source records. Avoid synchronously updating the
same aggregate row for every concurrent submission.

------------------------------------------------------------------------

### 4.7 Attendance and engagement

Attendance and coding streaks are separate concepts.

#### `lab_sessions`

Represents a scheduled lab meeting for a course offering.

Suggested fields: - `id` UUID PK - `offering_id` FK - `starts_at`,
`ends_at` - `session_type` - `created_by` - `status` (SCHEDULED / OPEN /
COMPLETED / CANCELLED) - attendance window settings if required

#### `attendance_records`

One student's attendance result for one session.

Suggested fields: - `id` UUID PK - `lab_session_id` FK -
`student_profile_id` or `course_enrollment_id` FK - `status` (PRESENT /
ABSENT / LATE / EXCUSED) - `marked_by` - `marked_at` - source/method if
QR or other check-in methods are introduced

Constraint: one attendance record per student per session, unless the
policy explicitly supports multiple check-in events. Attendance
percentages should be calculated from session and attendance records,
with cancelled sessions excluded according to policy.

#### `daily_activity` (optional; add when streaks are implemented)

One qualifying activity summary per student per local calendar date.

Suggested fields: - `id` UUID PK - `student_profile_id` FK -
`activity_date` - `qualifying_submission_count` - `qualifying_minutes`
if meaningful and reliably measured - `created_at`, `updated_at`

Constraint: unique `(student_profile_id, activity_date)`.

Define what counts as a qualifying activity before implementing streaks.
A login should not automatically count. A submission may count only if
it meets the product's agreed rule. Store dates using the institution's
chosen timezone policy. Current and longest streak can be calculated
from daily activity; cache them only if needed.

------------------------------------------------------------------------

### 4.8 Exams and proctoring

The existing database specification includes `exams` and
`proctoring_events`. Keep these in a later implementation phase unless
exam functionality is part of the initial release.

Before implementation, define: - exam ownership and offering/course
scope - exam schedule and allowed attempts - problem selection and
visibility - proctoring event types and retention policy - who can
access proctoring data - whether snapshots are stored in object storage
rather than PostgreSQL

Proctoring events should reference the relevant exam and, where
multi-tenancy is enabled, the tenant. Avoid storing large image/video
payloads directly in relational rows.

------------------------------------------------------------------------

## 5. Relationship overview

``` text
roles 1 ─── many profiles
logins 1 ─── 1 profiles
departments 1 ─── many profiles
departments 1 ─── many programs

profiles (student) 1 ─── many student_term_enrollments
academic_terms 1 ─── many student_term_enrollments
programs 1 ─── many student_term_enrollments

courses 1 ─── many course_offerings
academic_terms 1 ─── many course_offerings
programs 1 ─── many course_offerings

course_offerings many ─── many profiles (faculty)
    through offering_faculty

course_offerings many ─── many profiles (students)
    through course_enrollments

elective_groups 1 ─── many elective_options
profiles (student) 1 ─── many elective_selections

courses 1 ─── many labs
labs 1 ─── many experiments
experiments 1 ─── many problems
problems 1 ─── many test_cases

profiles (student) 1 ─── many submissions
problems 1 ─── many submissions
submissions 1 ─── many submission_test_results

course_offerings 1 ─── many lab_sessions
lab_sessions 1 ─── many attendance_records
profiles (student) 1 ─── many attendance_records
```

This is a logical relationship map. Implement actual foreign keys and
constraints in SQLAlchemy/Alembic migrations.

------------------------------------------------------------------------

## 6. Tenant / institution scope --- decision required

The backend architecture document describes a multi-tenant design with
`tenants`, `tenant_id` columns, and PostgreSQL Row-Level Security (RLS).
The database specification's earlier DDL is primarily written around the
Medicaps institutional domain and does not consistently include tenant
columns.

The project lead must make and document this decision before the first
production migration:

-   **Single-institution deployment:** If MediCode will only serve
    Medicaps, a tenant abstraction may be unnecessary for the first
    release. Keep department/program scoping and object-level
    authorization. Do not claim multi-tenant isolation if it is not
    implemented.
-   **Multi-institution deployment planned/required:** Create `tenants`
    and add `tenant_id` to every tenant-owned table. Scope unique
    constraints by tenant where appropriate. Implement and test RLS
    policies, including transaction-scoped tenant context. Do not rely
    only on application filters.

Do not add half-implemented RLS. A policy that is enabled but not
correctly configured can cause either data leaks or unexpected failures.
Cross-tenant isolation tests are mandatory if multi-tenancy is selected.

------------------------------------------------------------------------

## 7. Integrity, indexes and security rules

### Required constraints

-   Unique normalized login email.
-   One profile per login.
-   Valid role and department foreign keys.
-   Unique student enrollment number within the agreed scope.
-   Unique student academic placement per term, unless an approved
    exception exists.
-   Unique offering enrollment per student.
-   Unique faculty assignment per offering.
-   Unique attendance record per student/session.
-   Unique daily activity row per student/date.
-   Valid numeric ranges for semester, marks, execution limits, and
    attendance states.
-   Explicit `NOT NULL` only for genuinely required fields.

### Indexing

Create indexes based on real query paths. At minimum, evaluate indexes
for: - `profiles.login_id`, `profiles.role_id`,
`profiles.department_id` -
`student_term_enrollments.student_profile_id`, `academic_term_id` -
`course_offerings.course_id`, `academic_term_id` -
`offering_faculty.offering_id`, `faculty_profile_id` -
`course_enrollments.offering_id`, `student_profile_id` -
`labs.course_id`, `experiments.lab_id`, `problems.experiment_id` -
`test_cases.problem_id` - `submissions.student_profile_id`,
`problem_id`, `created_at` - `submission_test_results.submission_id` -
`lab_sessions.offering_id`, `starts_at` -
`attendance_records.lab_session_id`, `student_profile_id` -
`daily_activity.student_profile_id`, `activity_date`

Use composite indexes that match actual filters and sort orders.
PostgreSQL does not automatically create an index on every referencing
foreign-key column. Avoid adding every possible index blindly; indexes
increase write and storage cost.

### Authorization

-   Check role permissions and object-level access on the backend.
-   A faculty role does not imply access to every course.
-   A student role does not imply access to every course.
-   Verify active enrollment/assignment for every protected resource
    request.
-   Never expose hidden test cases in API responses.
-   Use least-privilege database credentials. The application must not
    connect as a superuser.
-   Keep secrets out of source control.
-   If using RLS, test policies using the actual non-owner application
    DB role. Table owners and privileged roles can bypass policies
    unless configured appropriately.

### Deletion and history

Academic records should generally be soft-deactivated or retained, not
cascade-deleted indiscriminately. Use `RESTRICT` for important
historical references and `CASCADE` only where deleting a parent should
genuinely delete dependent, non-historical data. Define retention and
anonymization rules with the institution.

------------------------------------------------------------------------

## 8. Implementation order for contributors

### Phase A --- Database foundation

1.  Confirm single-institution vs multi-tenant decision.
2.  Agree naming conventions, UUID strategy, timestamp/timezone policy
    and enum strategy.
3.  Create SQLAlchemy base, naming conventions, async session setup and
    Alembic configuration.
4.  Add `roles`, `logins`, `departments`, `profiles`.
5.  Add seed data for approved roles.
6.  Add tests for uniqueness, foreign keys and profile/login
    relationships.

### Phase B --- Academic structure

1.  Add `programs` and `academic_terms`.
2.  Add `student_details` and`student_term_enrollments`.
3.  Add `courses` and `course_offerings`.
4.  Add `offering_faculty` and `course_enrollments`.
5.  Add tests for semester history, faculty assignment, student
    enrollment and access rules.

### Phase C --- Electives and learning content

1.  Add elective groups/options/selections after confirming the
    university workflow.
2.  Add labs, experiments, problems and test cases.
3.  Add publication and visibility rules.
4.  Test that students cannot access unassigned offerings or hidden test
    data.

### Phase D --- Submission and assessment

1.  Add submissions and per-test results.
2.  Add status transitions and idempotency.
3.  Add background job integration when execution is introduced.
4.  Test concurrent submissions and recalculation of aggregate grades.

### Phase E --- Attendance and engagement

1.  Add lab sessions and attendance records.
2.  Confirm attendance marking and correction policy.
3.  Add daily activity only after defining qualifying activity.
4.  Test duplicate events, timezone boundaries and streak recalculation.

### Phase F --- Exams and advanced features

Implement exams, proctoring, plagiarism, reporting and analytics only
when their product requirements and retention/access policies are
approved.

------------------------------------------------------------------------

## 9. Team contribution rules

Every contributor must follow these rules:

1.  Never edit the production database manually as a substitute for a
    migration.
2.  Every schema change must be an Alembic migration committed with the
    code.
3.  Never rewrite an already-shared migration that may have been applied
    by another developer; create a new migration.
4.  Do not run `alembic revision --autogenerate` and commit without
    reviewing the generated migration.
5.  Do not create duplicate models or duplicate enum definitions across
    modules.
6.  Do not access another module's tables through ad-hoc queries when a
    service/interface is defined.
7.  Add tests for foreign keys, unique constraints, deletion behavior
    and authorization.
8.  Use synthetic seed data. Never commit real student personal data.
9.  Never commit `.env`, database URLs containing passwords, or
    production credentials.
10. Coordinate migration order and merge conflicts with the backend
    lead.

### Suggested pull-request checklist

-   [ ] Requirement and table ownership are clear.
-   [ ] SQLAlchemy model and Alembic migration are both included.
-   [ ] Foreign keys and uniqueness constraints are present.
-   [ ] Indexes match the expected query paths.
-   [ ] Authorization checks are implemented in the service layer.
-   [ ] Tests cover valid and invalid relationships.
-   [ ] No secrets or real personal data are included.
-   [ ] Migration was tested against a clean PostgreSQL database.

------------------------------------------------------------------------

## 10. Hosting recommendation

### Development

Run PostgreSQL locally through Docker Compose. Each contributor should
use their own local database and apply migrations from the repository.

### Shared staging

Use a managed PostgreSQL instance in a region close to the application
and users. Supabase offers a PostgreSQL database and lists Mumbai
(`ap-south-1`) as an available specific region. It is a convenient
option for a student team that wants a managed database without
operating PostgreSQL servers.

Use a paid plan for a shared staging environment that contains important
test data; confirm backup and recovery options for the selected plan.

### Production

For a university deployment, prefer a managed PostgreSQL service in an
institution-approved Indian region, such as **Amazon RDS for PostgreSQL
in Mumbai (`ap-south-1`)**. This provides control over networking,
database access, backups, monitoring and deployment configuration. It
does require more cloud setup and operational ownership.

Supabase in Mumbai is also a viable production candidate if the
institution approves the vendor, contract, data processing, access
controls, backups and operational model. Do not choose a provider solely
because it is easy to set up.

Before production, confirm with the university/IT team: - who owns the
cloud account and billing - institutional data-hosting and residency
requirements - backup retention and restore testing - database private
networking and firewall rules - credential rotation and audit access -
recovery objectives (RPO/RTO) - whether student records may be hosted
with the chosen provider

**Do not expose PostgreSQL publicly to the frontend.** Only the backend
should connect to the database over a secured connection. Keep database
credentials in backend environment secrets.

Useful provider documentation: - Supabase regions:
https://supabase.com/docs/guides/platform/regions - Supabase PostgreSQL
overview and backups:
https://supabase.com/docs/guides/database/overview - Supabase connection
methods/pooling:
https://supabase.com/docs/guides/database/connecting-to-postgres - AWS
RDS PostgreSQL: https://aws.amazon.com/rds/postgresql/

------------------------------------------------------------------------

## 11. Decisions that must be confirmed by the project lead

Do not silently decide these in an individual PR:

1.  Is the first deployment Medicaps-only, or must multi-institution
    tenancy be implemented now?
2.  Are HOD and TPO separate roles, scoped permissions, or both?
3.  Can a course offering have multiple faculty members?
4.  Are students assigned to sections automatically, manually, or both?
5.  Can students repeat a semester or have multiple active academic
    placements?
6.  Are elective choices made against a course catalogue or a
    term-specific offering?
7.  Are labs and problems reusable across offerings, or can they be
    offering-specific?
8.  What exactly counts as attendance and what correction/approval
    workflow applies?
9.  What exactly counts as a qualifying coding-streak day?
10. Which marks/approval states are required, and who can lock or
    approve them?
11. What is the institution's approved database host, region, backup
    policy and data-retention policy?

------------------------------------------------------------------------

## 12. Definition of done for the database foundation

The database foundation is ready for feature development when:

-   [ ] PostgreSQL works locally through the documented setup.
-   [ ] SQLAlchemy models and Alembic migrations are in source control.
-   [ ] A clean database can be created entirely from migrations.
-   [ ] Seed data creates the approved role taxonomy.
-   [ ] Identity and academic foreign-key constraints work.
-   [ ] Course offering, faculty assignment and student enrollment flows
    are tested.
-   [ ] Authorization tests prove that students and faculty cannot
    access unrelated offerings.
-   [ ] Test data is synthetic.
-   [ ] Backup and restore procedure is documented for the shared
    environment.
-   [ ] The project lead has resolved the decisions in Section 11.

**Final instruction:** Build the database from migrations, not from
manual dashboard edits. Treat this guide as the shared contract; if
implementation reveals a missing requirement or contradiction, raise it
for review before changing the schema.