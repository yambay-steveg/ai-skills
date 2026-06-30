---
name: card-model
description: >
  Govern and curate Steve's session-card store: load the card-model rules, audit
  cards for drift (the linter), and apply the decision rules to a question. Use when
  Steve says "curate the cards", "audit the cards", "check the card model for drift",
  "lint the cards", "tidy the card store", or asks a model-decision question like
  "is this a card or a checkbox", "should this be a card or a program note", "where
  should X live", "card or forum". NOT for launching/resuming cards (that's cardctl
  launch via the board) — this is governance, not day-to-day use.
allowed-tools: Bash, Read, Edit, AskUserQuestion
---

# Card-model skill (/card-model)

A repeatable, on-demand governance pass over the session-card store. Two jobs over the
same model:

1. **Decision-harness** — apply the card-model rules to a question Steve brings.
2. **Linter** — the integrity check the no-schema markdown card store needs (drift detection).

This skill is a **thin reasoning layer**. The deterministic work lives in `cardctl`
(`cardctl lint` = the facts; `cardctl set` / `set-status` = the validated writer). The
skill never parses or edits card frontmatter itself — it reasons over facts and routes
every mutation through cardctl (the single writer; it re-reads before write — ai-skills#10).

## Always do first: load the model

Read both, every time — they are the source of truth and the live backlog:

1. `~/Source/work/yambay-steveg/work-knowledge/Procedures/session-card-system.md`
   → "How it works (the model)" — the canonical rules.
2. `~/Source/work/yambay-steveg/work-knowledge/Programs/managing-ai-activities/managing-ai-activities.md`
   → rationale, worked examples, and "Open design questions" (the live design backlog).

If a decision in this session resolves or shifts something, that's where it gets recorded
(see *Record outcomes*).

## The rules (cheat-sheet for the decision-harness)

- **Card = project. There is no separate project layer.** Layers: Area → Program → Card → Session.
- **A Session is a working slice of one card** (subtask, context reset, new day, parallel branch),
  logged under `## Sessions`. **Never its own card.** It never spans cards.
- **Standing things are vault *notes*, never cards.** Areas, Programs, and Forums are each a folder
  + a same-name folder note. A Forum is a recurring meeting / provenance hub (e.g. `[[e-and-a]]`) —
  not a card, not a hierarchy parent.
- **Hierarchy via wikilinks; facets via tags.** `program: "[[…]]"` is the card's home (a link-
  property — whole value is the wikilink, so it rename-updates; a YAML list gives multi-membership).
  `area/*`, `kind/*`, `jira/*` are facet tags (multi-valued).
- **Provenance ≠ membership.** "Raised at the E&A meeting" is `raised-at: "[[<forum>]]"` — a separate
  edge from `program:`. A card can live in one program yet trace back to a forum.
- **Structural links only in link-properties, never in prose** (`latest:`/`summary:` wikilinks don't
  rename-update). **Basenames unique vault-wide.** **Rename notes only in Obsidian** (GUI/API),
  never shell/git.
- **Checkbox vs card test:** "will I open sessions to work on this, producing something — or is it a
  step I tick off within other work?" Most todos are `- [ ]` checkboxes; a card is its own stream of
  work. A follow-on deliverable → its own card, not a reopen of the finished one.

## Audit flow ("curate / lint the cards")

1. Run the linter:
   ```bash
   cardctl lint --json
   ```
   (Use the human form `cardctl lint` if Steve just wants to eyeball it.)
2. **Interpret.** Group by severity. The `STANDING-LANGUAGE` finding is a *heuristic candidate*,
   not a verdict — apply the rules and your judgement (and ask Steve) before calling a card a
   mis-modelled Program/Forum note. The deterministic codes (NO-AREA, DANGLING-LINK, BAD-STATUS,
   BASENAME-COLLISION, LINK-IN-PROSE, EMPTY-PROGRAM, STALE-PATH, MISSING-PLANID) are facts — but you
   still decide the *right fix* (e.g. which area a NO-AREA card belongs to).
3. **Classify each finding into a fix tier** (below) and present a short report: what's wrong, the
   fix you propose, and the tier.
4. **Act:**
   - *Apply-on-confirm* findings → show the `cardctl` command + the resulting change, apply on
     Steve's "yes" (`AskUserQuestion` if batching several).
   - *Advise-only* findings → print the exact command for Steve to run; don't mutate.
   - *Never-auto* → report only.
5. Offer to **record outcomes** if any decision was made.

## Decision flow ("is this a card or…?", "where should X live?")

Apply the cheat-sheet to the question, give a clear recommendation with the reason, then act via
cardctl (create a card, set a field) or advise the structural change. If it resolves an open design
question, record it.

## Fix tiers (the apply allowlist)

**Apply on confirm** — additive/corrective metadata, reversible, via `cardctl set` / `set-status`:
- add a missing `area/` (`cardctl set <c> --area area/<x>`)
- add/repoint `program:` (`--program <name>`) or `raised-at:` (`--raised-at <forum>`)
- add/remove facet tags (`--add-tag` / `--remove-tag`)
- fix a `BAD-STATUS` to the correct controlled value (`cardctl set-status <c> <status>`) — **but
  never to `done`/`archived`** (see below)

**Advise only** — structural / hard-to-reverse; print the command, Steve runs it:
- promoting a card → a Program/Forum note, or retiring a card
- anything that renames/moves a note (must route through the Obsidian API — link-rewrite cascade);
  this includes resolving a `BASENAME-COLLISION`
- bulk changes across many cards

**Never auto, ever:**
- `status` → `done` or `archived` (Steve's standing rule — never without his explicit say-so)
- deleting a card or folder

Everything applied goes **through cardctl**. Never hand-edit card frontmatter.

## Record outcomes

When a decision resolves or shifts the model:
- update `session-card-system.md` ("How it works") for a convention change, and/or
- update the "Open design questions" list in `managing-ai-activities.md` (strike/close the resolved
  one, note the call).

Card-data changes go via cardctl; only these two docs are edited directly (with `Edit`).

## Notes

- `cardctl lint` and `cardctl set` are documented in `ai-skills/session-cards/cardctl.md`.
- After editing `cardctl`, re-copy to PATH: `cp ~/Source/work/yambay-steveg/ai-skills/session-cards/cardctl ~/bin/cardctl`.
- Headless / no-GUI context: link-affecting *note* renames can't run (Obsidian-API only) — keep
  those advise-only and say so; never hang waiting on Obsidian.
