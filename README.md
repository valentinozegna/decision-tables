# decision-tables

An agent skill for Claude Code and Codex that finds every edge case of a feature.
The agent enumerates the feature's conditions into an exhaustive decision table,
asks you to rule on each uncertain cell, then minimizes the finished table into a
short ordered rule list and verifies it cell by cell. Diffing two tables gives the
behavior changelog and the test plan.

`skills/decision-tables/table.py` does the combinatorial work (standard library only):
`expand`, `check`, `minimize`, `verify`, `diff`, `selftest`.

## Install

Claude Code:

```
/plugin marketplace add valentinozegna/decision-tables
/plugin install decision-tables@decision-tables
```

Codex:

```
codex plugin marketplace add valentinozegna/decision-tables
codex plugin add decision-tables@decision-tables
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

and this to the project's `.codex/config.toml`:

```toml
[marketplaces.decision-tables]
source_type = "git"
source = "https://github.com/valentinozegna/decision-tables.git"

[plugins."decision-tables@decision-tables"]
enabled = true
```

Then ask the agent for a "decision table", "truth table" or "edge cases" of a feature.
