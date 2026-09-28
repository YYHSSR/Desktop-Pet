# Verification Before Completion

Read this before claiming that a feature is complete, a defect is fixed, or checks have passed. Verification supports specific conclusions; it is not a reason to rerun every command for each progress message.

## Choose Checks That Match the Requirements

Determine checks from the project's actual configuration, existing tests, and task acceptance criteria. Choose compilation, type checks, static checks, unit tests, integration tests, or manual operations according to the impact of the change; do not mechanically require every category for every task.

Tests should check observable behavior or key invariants, avoiding assertions only about how the code is written, internal call counts, or copied implementation logic. For low-risk, reversible changes with no behavior change, do not add tests of no value just to satisfy the process.

| Conclusion to report | Required basis |
|---|---|
| Compilation or build passed | Run the relevant command against the current changes; the exit status and output match expectations |
| Tests passed | Actually run the expected tests and check the count, failures, and skips; zero tests does not count as passing |
| Feature complete | Key acceptance requirements have corresponding evidence, and necessary interfaces and resources are integrated |
| Defect fixed | Evidence of the original symptoms, basis for the fix, and results of checks under the same conditions; clearly state limitations when reproduction under the same conditions is impossible |
| No issues of a certain type found | State the scope and method of the check, rather than expanding it into "the entire project has no issues" |

## Validity of Evidence

Record the command or manual steps performed, the code state they targeted, key results, and failure details. Check the exit status and relevant output; do not rely only on a success message at the end of a log.

When the current code and relevant environment have not changed, verification evidence already obtained in this task remains valid and need not be rerun for the next message. If relevant code, configuration, or dependencies change after verification, rerun affected checks; expand verification moderately when the affected scope is uncertain.

One successful run of a stable, deterministic check can provide evidence. Intermittent failures, races, or explicit stability requirements call for justified repeated runs, with their number and results reported accurately.

## Handle Failures and Blockers

1. Distinguish product implementation, the tests themselves, design assumptions, and environment issues, and record the actual failure.
2. Return to [Implementation](implementation.md), [Debugging](debugging.md), or [Design](design.md) to correct the corresponding issue.
3. After a correction, rerun affected checks; expand verification further only for a new failure or change in scope.
4. If progress is blocked, report what is complete, why work is blocked, and what remains unverified; do not treat skipped checks as passing.

Do not delete valid assertions, conceal command failures, or substitute unrelated checks for the original acceptance goal just to obtain a green result. Distinguish pre-existing repository failures from failures introduced by this task; state uncertainty when attribution cannot be determined.

## Final Review and Report

Read the final changes and map each important requirement to them, checking temporary files, unrelated modifications, and the user's existing work. When the user asked only for a review or proposal, verify citations, logic, and scope; do not carry out unauthorized product operations.

Briefly report four kinds of information:

- What was delivered and how user-observable behavior changed.
- Key change locations or entry points for use.
- Which checks were actually performed and what their results were.
- Anything still unverified, any remaining problems, or conditions the user must provide; there is no need to add such limitations artificially when none exist.

"Code written," "tests passed," and "goal achieved" are separate conclusions. Keep the report consistent with the evidence: do not overstate it, and do not deny proven results because unrelated checks were not run.
