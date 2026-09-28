# Design and Scope Confirmation

Read this when the user's goal, interfaces, or architecture involve significant trade-offs. Small changes with clear requirements do not need an additional design ceremony.

## Establish a Shared Understanding

Use the conversation and project materials to confirm the intended users, behavior to change, constraints, and success criteria. Do not ask again for answers already given. Briefly share the key understanding with the user, making clear which points are requirements and which are assumptions.

When important missing information would change the approach, ask focused questions; related questions may be combined, rather than mechanically limiting each exchange to one question. While waiting for an answer, continue read-only exploration that does not depend on it.

## Choose Design Depth According to the Task

| Type | Output | Conditions for starting implementation |
|---|---|---|
| Feasibility investigation | The question to answer, the lowest-cost way to investigate, conclusions, and limitations | Stop at the conclusion when the user wants only a conclusion; conduct investigation under existing authorization |
| Bounded change | State the target behavior, affected boundaries, and verification method in the conversation | Key requirements are clear and implementation is authorized |
| Architectural change | Written design: goals, scope, architecture, interfaces, risks, and acceptance criteria | Significant trade-offs are resolved and implementation is authorized; continue with a plan when needed |

A new project does not automatically require the heaviest process. Decide based on business complexity, interface impact, and uncertainty. Before turning temporary exploratory code into a formal implementation, check that it falls within the user's request and meets quality and verification requirements.

## Choosing an Approach

- Where real trade-offs exist, present a small number of feasible approaches, their respective effects, and the reason for your recommendation; do not invent options when the approach is obvious or the user has already chosen one.
- In an existing repository, prefer the existing architecture, dependencies, and naming. Propose local structural changes only when the current goal genuinely requires them.
- When starting from scratch, prefer the selected framework's standard project structure; if no framework applies, choose the smallest structure that meets the requirements and explain responsibilities and dependencies.
- Do not label arbitrary layering "official." When framework documentation is needed, check authoritative material that matches the project's version; state assumptions if this cannot be verified.
- Describe key data flows, interface inputs and outputs, error behavior, compatibility, and necessary migration effects. Add a corresponding recovery plan only when persistent data or deployment changes are involved.
- Avoid adding complex abstractions or unrelated components in advance for needs that may arise in the future.

## Design Documents and Approval

Follow the user's and repository's conventions for document paths first; when there is no convention, use `AI/docs/<topic>-design.md`. Do not create a document just for recordkeeping for a simple change.

A design document should give implementers enough to understand the goals and out-of-scope items, key decisions and rationale, components and interfaces, exceptional cases, acceptance criteria, and unresolved questions. Adapt its organization to the task.

After writing it, check coverage of requirements, contradictions, and ambiguities that would change implementation. Decide ordinary implementation details yourself; do not silently resolve important business ambiguities by guessing.

When the user requests "design first, then proceed after approval," deliver a complete, reviewable design and wait. When the user has explicitly authorized end-to-end implementation, continue within that scope; do not repeatedly request approval for each section or document. Ask only about a new trade-off beyond the existing authorization.

## Handoff

For multi-step work, pass the design's acceptance requirements, constraints, and unresolved items to [Planning](planning.md). For simple work, proceed directly to [Implementation](implementation.md). When a key question remains unresolved, do not present implementation dependent on it as a settled step.
