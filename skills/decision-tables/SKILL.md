---
name: decision-tables
description: Find every edge case of a feature by enumerating its conditions into an exhaustive decision table, getting a human decision on each uncertain cell, then minimizing the table into a short ordered rule list that is verified cell by cell. Use when defining or changing a feature with interacting conditions (bookings, capacity and waitlists, notifications, permissions, pricing, workflows), when auditing existing behavior for gaps or client/server disagreement, when the user says "decision table", "edge cases", "truth table", "state table" or "what happens when", or before writing the test plan for such a feature.
---

# Decision Tables

A decision table lists every combination of a feature's conditions and gives
each combination exactly one outcome. Filling every cell is what surfaces the
edge cases. Minimizing the finished table gives the rules to implement, and
diffing two tables gives the behavior changelog and the test plan.

A golden table is the official specification of the feature's behavior.
Code and tests follow it, and a behavior change starts with a table change.
Tables live in the project's repo, one folder per feature
(`docs/decision-tables/<feature>/` unless the project's own instructions name
another place). The tool is `table.py` beside this file
(standard library only); set `T` to its path.

```bash
T=<this skill's folder>/table.py
python3 $T expand   <spec.json> <table.csv>
python3 $T check    <spec.json> <table.csv>
python3 $T minimize <spec.json> <table.csv> <rules.json>
python3 $T verify   <spec.json> <table.csv> <rules.json>
python3 $T diff     <spec.json> <old.csv> <new.csv>
python3 $T selftest
```

## Who decides what

You do the combinatorial work: enumerating, drafting, minimizing,
verifying. The user owns every product decision. A cell whose outcome you
inferred with any doubt gets `status = flag` and a question in `note`; the
user answers it and the cell becomes `decided`. Present flagged regions with
a recommendation and wait for the answer.

## The files

| File | Content |
|---|---|
| `<name>.spec.json` | `name`, `assumes` (preconditions kept out of the grid), `dimensions` (name to list of values), optional `state` (the dimension that is the state of a state machine) |
| `<name>.csv` | One row per cell: the dimension columns, then `outcome`, `next`, `status`, `note` |
| `<name>.rules.json` | The minimized ordered rules plus the default |
| `<name>.rules.md` | The same rules as a readable table |

Cell fields:

- `outcome`: what the user observes, in a short fixed phrase. Identical
  behavior must use the identical phrase, because minimization groups by it.
  `n/a` marks a combination that cannot occur; it is a don't-care.
- `next`: the resulting state, a value of the `state` dimension, or `same`.
  Empty when the spec has no `state`.
- `status`: `todo` (empty cell), `draft` (you are confident and cite
  evidence), `flag` (needs the user), `decided` (the user ruled).
- `note`: evidence as `file:line` for a draft, the question for a flag, the
  reason for an `n/a`.

## The pipeline

### 1. Enumerate

Read the code or the feature brief and list every state variable, event and
condition with its values. Pick values by behavior: `seats = unlimited /
open / full`, never raw numbers. Write the spec.

Keep a table to four dimensions and a few hundred cells. A condition that
switches the whole feature off (event ended, user signed out) goes in
`assumes`. A larger feature splits into sub-tables with a narrow interface,
where one table's outcome is another table's event. A booking flow splits
into the user's choice (`self-booking`) and the server's reaction
(`waitlist-promotion`); the interface is "a seat was freed".

### 2. Expand

`expand` writes the full cross product. Draft every cell. For an existing
feature, derive the outcome from the code of every layer that takes part
(UI, client state, services, database rules, backend) and cite it. For a
new feature, derive it from the brief.

Drafting with a short throwaway script (one function from cell to outcome) is
fine for large tables. The CSV is the artifact; the script is scratch.

Flag a cell when any of these holds:

- Two layers disagree (the app counts one way, the server another).
- The outcome breaks an invariant (more people than capacity, a duplicate
  notification, a state with no way out).
- The code has no answer, or the answer is an accident of ordering.
- The answer in the code looks deliberate but surprising to a user.
- You would have to guess the product intent.

Prove a suspected defect before flagging it as one: a temporary test against
the real function, run and then deleted. Put
the reproduction in the note.

### 3. Adjudicate

`check` groups open cells into regions, so one question covers many cells.
Present each question with the region, the current behavior, and a
recommendation. Record each answer in the table as `decided`. A table with
zero open cells is the golden table; `check` exits 0.

### 4. Minimize

`minimize` runs four steps and writes the rules:

- **Default extraction.** The most common outcome becomes the final
  else-branch. Only the exceptions need rules.
- **Don't-care expansion** (Espresso EXPAND). Each exception cell grows into
  a cube: a dimension widens to more values, or to "any", while every cell
  inside still has the same outcome, is `n/a`, or belongs to an earlier rule.
- **Set cover.** The cube that settles the most remaining cells becomes the
  next rule, repeated until no exception is left. The winning cube is then
  shrunk to the cells it settles (Espresso REDUCE) so each rule reads true
  on its own.
- **Equivalent values.** Values of a dimension that behave identically
  everywhere are reported. For the `state` dimension this is DFA
  minimization by partition refinement, iterated to a fixpoint, so states
  that lead to equivalent states also merge.

Read the report as findings. A dimension where every value is equivalent has
no effect on behavior. A rule that the user finds surprising is an edge case
to take back to step 3.

### 5. Emit

The rules are an ordered list; the first rule that matches wins, and the
default catches the rest. Implement them in that order, in one place, and
write one test per rule plus one for the default.

The strongest form: the rule list becomes one pure function, and a test
replays the golden CSV against it, one test per cell. Then the table and the
code cannot drift apart.

### 6. Verify

`verify` expands the rules back over every cell and compares with the table.
It must report zero mismatches. `minimize` runs the same check before it
writes anything.

### 7. Regress

When the feature changes, edit the spec, run `expand` (existing cells keep
their outcome, new cells arrive as `todo`), draft and adjudicate the new
region, then `minimize` and `verify` again. `diff old.csv new.csv` prints the
changed cells as minimized rules. That output is the behavior changelog for
the PR and the list of cases to test. Get `old.csv` from git:

```bash
git show main:docs/decision-tables/<feature>/<name>.csv > /tmp/old.csv
```

### 8. Attach the table to the PR

Every PR that adds or changes logic covered by a table includes the table
evidence in its description. Paste the command output in fenced code blocks.

- **New feature:** link the golden table and its `rules.md`, and paste the
  `verify` output (zero mismatches).
- **Behavior change:** paste the `diff` output against `main` and the `verify`
  output. List each changed cell that the user decided, with the decision.
- **Refactor:** paste the `diff` output against `main`, which must report no
  changed cells, and the `verify` output. Run the test that replays the golden
  CSV against the code and paste its result. These three together show the
  refactor kept the behavior.
- **Bug fix:** paste the reproduction (the failing input and the wrong
  outcome), the cell that covers it, and its correct outcome. If no cell covers
  the bug, the table is missing a dimension or a value: add it, adjudicate the
  new cells, and treat the PR as a behavior change.

A reviewer checks the PR against the pasted output, so paste it unedited.
