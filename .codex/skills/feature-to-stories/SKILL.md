---
name: feature-to-stories
description: Decompose one mapped Feature into concise, self-contained delivery Stories by compiling only relevant REQ, DES, UI, shared Feature, and optional FD evidence. Use with a FEAT ID; ask targeted questions for material ambiguity and do not require a complete Feature Design.
---

# Feature To Stories

Require one Feature ID with status `Mapped` or an explicitly accepted boundary.

## Inputs

Read the Feature routing manifest, exact referenced REQ/DES/UI anchors, relevant
confirmed shared rules, optional confirmed FD anchors, affected existing
Stories, and direct dependencies. Do not load full upstream documents when
anchor-level reads suffice.

## Workflow

1. Build an inventory of only the Feature's confirmed source items.
2. Slice by independently useful and testable outcomes.
3. Ask the user about ambiguities that change product behavior, acceptance,
   authority, data semantics, public contracts, or Story boundaries.
4. Put a Story-local answer in that Story. Put a confirmed cross-Story answer in
   the Feature shared rules or optional Feature Design. Route global changes
   upstream.
5. Create stable `S-###` IDs and preserve existing IDs.
6. Compile each Story with:
   - exact source IDs and anchors;
   - a concise snapshot of every inherited requirement and constraint needed by
     development;
   - exact relevant prototype route/file/selector/state references;
   - observable ACs and verification intent.
7. For every Story to which a confirmed `Visual Reference` applies:
   - map each applicable visual item to at least one observable AC, or explicitly
     account for it as out of scope;
   - add a `Visual Acceptance Matrix` that names the UI anchor, applicable
     viewport or responsive context, state, expected visual scope, and evidence;
   - require screenshot comparison evidence when layout or styling is part of
     acceptance.
8. Do not invent viewports, responsive behavior, tolerances, or allowed
   deviations. Ask a targeted question when missing information materially
   affects valid visual acceptance, and keep the Story at `Needs Confirmation`
   until it is resolved.
9. Set an unblocked, explicitly confirmed Story to `Confirmed`; otherwise use
   `Needs Confirmation` or `Blocked`.
10. Map every source item to a Story, shared rule, non-goal, or explicit later
   phase.

Read [story-template.md](references/story-template.md). The compiled Story is
the downstream product contract. Delivery agents do not load complete PRD,
Core Design, Feature, or Feature Design documents by default.

Do not write technical designs or code and do not invent missing behavior.
