# decision-tables

A Claude Code skill that finds every edge case of a feature. Claude enumerates the
feature's conditions into an exhaustive decision table, asks you to rule on each
uncertain cell, then minimizes the finished table into a short ordered rule list
and verifies it cell by cell. Diffing two tables gives the behavior changelog and
the test plan.

`skills/decision-tables/table.py` does the combinatorial work (standard library only):
`expand`, `check`, `minimize`, `verify`, `diff`, `selftest`.

## Install

```
/plugin marketplace add valentinozegna/decision-tables
/plugin install decision-tables@decision-tables
```

To install it for everyone who clones a project, add this to the project's
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "decision-tables": {
      "source": { "source": "github", "repo": "valentinozegna/decision-tables" }
    }
  },
  "enabledPlugins": { "decision-tables@decision-tables": true }
}
```

Then ask Claude for a "decision table", "truth table" or "edge cases" of a feature.
