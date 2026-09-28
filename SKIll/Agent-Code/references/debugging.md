# Defect Investigation and Repair

Read this when a defect, build failure, test failure, or unexpected behavior occurs. The core approach is to obtain evidence first, then verify hypotheses about the root cause, avoiding unsupported layers of patches.

## 1. Record the Original Symptoms

Read the complete relevant error and stack trace, and record the inputs, steps taken, expected and actual results, runtime environment, and relevant versions. Check recent changes and environmental differences.

Before making changes, reproduce the issue in the unmodified state when possible, and preserve the failure output or verifiable results of the steps taken. An existing failing test, manual reproduction, or minimal one-off script are all acceptable; creating a formal failing test first is not required.

If the issue cannot be reproduced reliably, record the conditions tried and the frequency observed, collect necessary logs, or construct a minimal case. Historical logs can prove historical symptoms, but must not be presented as a current reproduction. When evidence is insufficient, make clear which conclusions remain hypotheses.

## 2. Trace the Evidence

Trace inputs and callers back from the failure point, comparing the normal and abnormal paths. Read enough of the implementation and contracts around relevant components; there is no need to read the entire codebase indiscriminately.

For an issue spanning components, first locate the boundary where the abnormal behavior occurs, then investigate that component. Add only the diagnostics needed to resolve the current uncertainty; do not log all environment variables, request contents, or credentials.

The environment, external services, and timing may also be causes; do not conclude that the investigation failed merely because the cause is outside business logic.

## 3. Verify the Hypothesis

Write a specific hypothesis: which factor causes which behavior, what evidence supports it, and what check can distinguish it from other explanations.

Verify one main causal hypothesis at a time. Keep experiments as small and reversible as possible. When results do not support a hypothesis, stop adding patches in that direction and revise your judgment using the new evidence. Preserve the user's existing changes; when reverting, touch only your own experimental changes.

"One hypothesis" does not mean that only one file can be changed. Interfaces, callers, and configuration with a shared root cause may be corrected together.

## 4. Fix and Check for Regression

Make the smallest sufficient fix for a supported root cause, avoiding opportunistic refactoring. Rerun the original check with the same inputs and conditions, and compare the results before and after the fix.

Add a regression test for defects at risk of recurring, then run affected existing checks. Put formal tests in the repository's existing structure; there is no need to turn every temporary diagnostic script into a permanent test.

If the fix fails, return to the evidence and hypothesis. After multiple attempts without progress, summarize explanations ruled out, evidence still missing, and feasible next steps; do not conclude that the architecture is wrong solely because there have been "three failures." Ask the user to decide when the scope must expand or a new product decision is needed.

## Special Cases

- **Intermittent failures:** Record the reproduction frequency and conditions for repeated checks; one passing run does not prove a stable fix. Prefer observable conditions with explicit timeouts for asynchronous waits; use a justified fixed delay only when verifying timing itself.
- **Path and file issues:** Check resolved targets and permitted boundaries; do not determine directory membership from string prefixes alone. Handle symbolic links and platform differences according to the specific risk.
- **Production incidents:** Describe service restoration and the permanent fix separately. Perform evidence-based rollback, isolation, or mitigation only within existing authorization and operational constraints; restoring service does not mean the root cause has been eliminated.
- **Issues that cannot be reproduced but can be corrected:** Explain the basis for the fix, locally verifiable invariants, and the original symptoms that remain unconfirmed; do not claim end-to-end verification of the original issue.

Follow [Verification](verification.md) for the final conclusion: report only what the evidence supports.
