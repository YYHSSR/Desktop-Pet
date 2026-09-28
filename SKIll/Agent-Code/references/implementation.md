# Coding and Integration

Read this before creating, modifying, or refactoring project code.

## Establish Project Facts

- Check the working directory and project rules; read the entry points, callers, configuration, tests, and build instructions relevant to the goal.
- If it is a Git repository, inspect existing differences and workspace status, distinguishing the user's existing work from changes made for this task; do not initialize a non-Git repository automatically just to follow the process.
- Confirm the language, framework version, dependency management, and verification commands from configuration and actual usage, rather than guessing based on general practice.
- Before changing code, confirm call relationships and interface constraints; look for existing reusable logic before creating a similar mechanism.

## Control the Scope of Changes

Implement the behavior the user needs, including configuration, resources, and interface wiring necessary for it. Follow existing naming, error handling, and code style.

Do not overwrite or revert the user's existing changes, or use a repository-wide rollback or cleanup to resolve a local problem. If there is a conflict in one place that cannot be safely merged, describe the specific conflict and wait for a decision; other independent work can continue.

Refactor only to support the current goal. A file being long is not by itself a reason to split it; when responsibilities or dependencies genuinely obstruct the current change, make the smallest necessary adjustment and explain why.

Avoid adding extension points, frameworks, and dependencies that are not currently needed. When a new dependency has real value, follow the project's version and lockfile conventions, and explain why it was added.

## Coding Process

By default, complete the production code for the current delivery scope first, then add necessary tests; writing a failing test first is not mandatory. Follow test-driven development when the user or project requires it.

During implementation, use compilation, static checks, and existing tests at any time to confirm key assumptions. Address failed checks promptly; do not wait until all code has been written before investigating known errors.

Pay attention to input boundaries, error paths, resource cleanup, and asynchronous behavior relevant to the goal. Validate at real trust boundaries or critical invariants, rather than mechanically repeating the same validation at every layer.

Record only necessary information in diagnostic output, avoiding credentials or complete sensitive data. Do not leave temporary logs, exploratory code, or placeholder implementations in the final delivery without explanation.

## Integration and Verification Failures

When unexpected behavior appears, turn to [Debugging](debugging.md): gather evidence first, then decide what to change. When test expectations conflict with requirements, return to the basis for the requirements; do not weaken assertions or delete valid tests merely to make checks pass.

When the environment is incomplete, external services are unavailable, or command permissions are limited, continue checks that can be completed and record what is blocked. Do not describe substitute checks as complete verification, or change unrelated global configuration without authorization just to pass checks.

## Checks Before Completion

Read the final diff and check for unrelated files, unintended formatting, missing wiring, temporary diagnostics, and the user's existing changes. Check the final version against [Verification](verification.md) before delivery.

The delivery should explain behavior changes, key files or entry points, checks performed, and their results. Do not commit, push, or publish automatically without the corresponding authorization.
