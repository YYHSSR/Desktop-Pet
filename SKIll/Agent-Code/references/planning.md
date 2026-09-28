# Implementation Plan

Read this for multi-step work, changes spanning files, or work with execution dependencies. A plan records necessary decisions and acceptance methods; it does not transcribe the entire code in advance.

## When to Save a Plan

Short tasks can list steps in the conversation. When work needs handoff across stages, will take longer to execute, or the user requests a written plan, follow the repository's path convention first; if there is none, save it as `AI/docs/<feature>-plan.md`. Clearly distinguish a design document from an execution plan.

When the user asks only for a plan, stop after delivering the plan. When the user has already authorized implementation, review the plan yourself and execute it directly; wait only at approval points explicitly set by the user.

## Plan Contents

Include the following useful information as appropriate to the task:

- The goal, scope, and observable acceptance criteria.
- The design or conversation basis for the approach, and compatibility and dependency constraints that must be followed.
- Files to be modified or created and their responsibilities; clearly mark paths that still need investigation as unverified, rather than inventing paths.
- Implementation tasks ordered by dependency, key interfaces, and specified values.
- Verification mapping: which check proves each important acceptance requirement, which command to run, and how to determine success.
- Risks, unresolved questions, and necessary paths for returning to earlier work.

Fix only decisions that affect behavior, interfaces, or collaboration. Allow implementers to choose equivalent internal implementations; do not require each step to lead to a single possible function body.

## Work Order

1. **Preliminary confirmation.** Understand the current state and verification entry points. For defect tasks, first obtain evidence of the original symptoms and investigate the root cause according to [Debugging](debugging.md), then determine the repair tasks.
2. **Implementation.** Complete production code, necessary configuration, and resources for the current independently deliverable scope; compilation, type checks, existing tests, and diagnostic commands may be run to find problems early.
3. **Add tests and verify.** Add valuable tests according to risk and acceptance requirements, and check the final implementation.
4. **Handle failures.** Distinguish implementation errors, design problems, test errors, and environment problems; return to the appropriate step to correct them, then reverify the affected scope.
5. **Deliver.** Check requirements and the final diff, and report evidence and limitations.

Larger projects may be divided into increments that can be accepted independently, each following this order. There is no need to wait until all project code is written to get the first feedback. Do not reduce the entire task to the first increment without authorization.

## Test Location

Place formal tests according to the project's framework, directories, naming, and discovery rules. Put one-off diagnostic scripts in a temporary directory permitted by the project; when there is no convention, `work/<task>/` may be used, with their retention or cleanup explained at the end. Do not create a separate formal test directory that existing test commands cannot discover.

## Review and Update

Confirm that requirements map to tasks, dependency order is executable, interface names are consistent, and verification commands have a basis in the project. Do not use "handle all edge cases" as an acceptance criterion; specify the boundaries relevant to the current requirements.

If facts change during execution, promptly update affected tasks and the reasons, preserving valid results from completed work. Pause dependent parts only when new scope or a major choice requires a user decision; ordinary implementation adjustments do not restart the entire approval process.
