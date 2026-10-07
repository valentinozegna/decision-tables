"""Decision-table tool: expand, check, minimize, verify, diff.

A spec (JSON) names the dimensions and their values. A table (CSV) holds one
row per cell of their cross product, with the outcome a human signed off on.
Rules (JSON) are the minimized, priority-ordered form of that table.

Run `python table.py selftest` to check the algorithms.
"""

import argparse
import csv
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

NA = "n/a"
SAME = "same"
META = ["outcome", "next", "status", "note"]
OPEN_STATUSES = {"", "todo", "flag"}


def load_spec(path):
    spec = json.loads(Path(path).read_text())
    spec["dims"] = list(spec["dimensions"])
    return spec


def all_keys(spec):
    return list(itertools.product(*(spec["dimensions"][d] for d in spec["dims"])))


def load_table(spec, path):
    rows = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[d] for d in spec["dims"])
            rows[key] = {m: (row.get(m) or "").strip() for m in META}
    return rows


def save_table(spec, rows, path):
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(spec["dims"] + META)
        for key in all_keys(spec):
            writer.writerow(list(key) + [rows[key][m] for m in META])


def result_of(row):
    return (row["outcome"], row["next"])


def problems(spec, rows):
    found = []
    valid = set(all_keys(spec))
    for key in valid - set(rows):
        found.append(("missing", key, ""))
    for key in set(rows) - valid:
        found.append(("not in spec", key, ""))
    for key in sorted(valid & set(rows)):
        row = rows[key]
        if not row["outcome"]:
            found.append(("no outcome", key, row["note"]))
        elif row["status"] in OPEN_STATUSES:
            found.append((row["status"] or "no status", key, row["note"]))
        elif spec.get("state") and row["outcome"] != NA:
            if row["next"] not in spec["dimensions"][spec["state"]] + [SAME]:
                found.append(("next is not a state", key, row["next"]))
    return found


def cube_cells(cube):
    return itertools.product(*cube)


def grow(seed, domains, allowed):
    """Espresso EXPAND on one cell: widen each dimension while every cell stays allowed."""
    best = None
    count = len(domains)
    for shift in range(count):
        cube = [[value] for value in seed]
        for dim in [(shift + i) % count for i in range(count)]:
            full = cube[:dim] + [domains[dim]] + cube[dim + 1 :]
            if all(allowed(cell) for cell in cube_cells(full)):
                cube = full
                continue
            for value in domains[dim]:
                if value in cube[dim]:
                    continue
                wider = cube[:dim] + [cube[dim] + [value]] + cube[dim + 1 :]
                if all(allowed(cell) for cell in cube_cells(wider)):
                    cube = wider
        size = sum(1 for _ in cube_cells(cube))
        if best is None or size > best[0]:
            best = (size, cube)
    return [sorted(values, key=domains[i].index) for i, values in enumerate(best[1])]


def minimize(spec, results, default=None):
    """Greedy ordered cover. Returns (default, rules); rule order is priority.

    `results` maps every cell to its result; cells whose outcome is n/a are
    don't-cares. A rule may overlap cells an earlier rule already decided,
    and may never touch an undecided cell with a different result. The winning
    cube is then shrunk to the cells it newly decides (Espresso REDUCE), so
    each rule reads true on its own.
    """
    domains = [spec["dimensions"][d] for d in spec["dims"]]
    cares = {k: r for k, r in results.items() if r[0] != NA}
    if default is None:
        default = Counter(cares.values()).most_common(1)[0][0] if cares else (NA, "")
    remaining = {k for k, r in cares.items() if r != default}
    decided = set()
    rules = []
    while remaining:
        best = None
        for seed in sorted(remaining):
            target = cares[seed]

            def allowed(cell, target=target):
                return cell not in cares or cell in decided or cares[cell] == target

            cube = grow(seed, domains, allowed)
            gain = sum(1 for cell in cube_cells(cube) if cell in remaining)
            free = sum(1 for i, values in enumerate(cube) if len(values) == len(domains[i]))
            if best is None or (gain, free) > best[0]:
                best = ((gain, free), cube, target)
        (gain, _), cube, target = best
        won = [cell for cell in cube_cells(cube) if cell in remaining]
        cube = [
            [v for v in domains[i] if any(cell[i] == v for cell in won)]
            for i in range(len(domains))
        ]
        for i in range(len(domains)):
            full = cube[:i] + [domains[i]] + cube[i + 1 :]
            if all(cares.get(cell, target) == target for cell in cube_cells(full)):
                cube = full
        when = {
            spec["dims"][i]: values
            for i, values in enumerate(cube)
            if len(values) < len(domains[i])
        }
        rules.append({"when": when, "outcome": target[0], "next": target[1], "cells": gain})
        for cell in cube_cells(cube):
            if cell in cares:
                decided.add(cell)
                remaining.discard(cell)
    return default, rules


def evaluate(spec, ruleset, key):
    cell = dict(zip(spec["dims"], key))
    for rule in ruleset["rules"]:
        if all(cell[d] in values for d, values in rule["when"].items()):
            return (rule["outcome"], rule["next"])
    return (ruleset["default"]["outcome"], ruleset["default"]["next"])


def mismatches(spec, results, ruleset):
    return [
        (key, expected, evaluate(spec, ruleset, key))
        for key, expected in sorted(results.items())
        if expected[0] != NA and evaluate(spec, ruleset, key) != expected
    ]


def equivalent_values(spec, results, dim, blocks):
    """Group values of `dim` that behave the same in every other coordinate."""
    index = spec["dims"].index(dim)
    others = [spec["dimensions"][d] for i, d in enumerate(spec["dims"]) if i != index]

    def signature(value):
        sig = []
        for rest in itertools.product(*others):
            key = rest[:index] + (value,) + rest[index:]
            outcome, nxt = results[key]
            if nxt == SAME and dim == spec.get("state"):
                nxt = value
            sig.append(None if outcome == NA else (outcome, blocks.get(nxt, nxt)))
        return sig

    def compatible(a, b):
        return all(x is None or y is None or x == y for x, y in zip(a, b))

    groups = []
    for value in spec["dimensions"][dim]:
        sig = signature(value)
        for group in groups:
            if all(compatible(sig, other) for _, other in group):
                group.append((value, sig))
                break
        else:
            groups.append([(value, sig)])
    return [[value for value, _ in group] for group in groups]


def merge_report(spec, results):
    """DFA minimization on the state dimension, then plain equivalence on the rest."""
    blocks = {}
    state = spec.get("state")
    if state:
        blocks = {value: 0 for value in spec["dimensions"][state]}
        while True:
            groups = equivalent_values(spec, results, state, blocks)
            refined = {value: i for i, group in enumerate(groups) for value in group}
            if len(set(refined.values())) == len(set(blocks.values())):
                break
            blocks = refined
    report = {}
    for dim in spec["dims"]:
        merged = [g for g in equivalent_values(spec, results, dim, blocks) if len(g) > 1]
        if merged:
            report[dim] = merged
    return report


def markdown(spec, ruleset):
    lines = ["| # | When | Outcome | Next | Cells |", "|---|---|---|---|---|"]
    for number, rule in enumerate(ruleset["rules"], 1):
        when = "; ".join(f"{d} = {' / '.join(v)}" for d, v in rule["when"].items()) or "always"
        lines.append(
            f"| {number} | {when} | {rule['outcome']} | {rule['next']} | {rule['cells']} |"
        )
    default = ruleset["default"]
    lines.append(f"| else | everything else | {default['outcome']} | {default['next']} | |")
    return "\n".join(lines)


def build_ruleset(spec, results, default=None):
    default, rules = minimize(spec, results, default)
    ruleset = {
        "name": spec.get("name", ""),
        "rules": rules,
        "default": {"outcome": default[0], "next": default[1]},
    }
    wrong = mismatches(spec, results, ruleset)
    if wrong:
        raise SystemExit(f"BUG: minimized rules disagree with the table on {len(wrong)} cells")
    return ruleset


def cmd_expand(args):
    spec = load_spec(args.spec)
    old = load_table(spec, args.table) if Path(args.table).exists() else {}
    keys = all_keys(spec)
    blank = {"outcome": "", "next": "", "status": "todo", "note": ""}
    save_table(spec, {key: old.get(key, dict(blank)) for key in keys}, args.table)
    kept = sum(1 for key in keys if key in old)
    print(f"{len(keys)} cells: {kept} kept, {len(keys) - kept} new, {len(old) - kept} dropped")


def cmd_check(args):
    spec = load_spec(args.spec)
    rows = load_table(spec, args.table)
    found = problems(spec, rows)
    structural = [p for p in found if p[0] in ("missing", "not in spec")]
    for kind, key, note in structural:
        print(f"{kind}: {', '.join(key)}")
    if found and not structural:
        open_keys = {key: f"{kind}: {note}" for kind, key, note in found}
        regions = {
            k: (open_keys.get(k, NA if rows[k]["outcome"] == NA else "settled"), "")
            for k in all_keys(spec)
        }
        ruleset = build_ruleset(spec, regions, default=("settled", ""))
        questions = {}
        for rule in ruleset["rules"]:
            when = "; ".join(f"{d} = {' / '.join(v)}" for d, v in rule["when"].items())
            questions.setdefault(rule["outcome"], []).append(f"{when} ({rule['cells']} cells)")
        for number, (question, regions) in enumerate(questions.items(), 1):
            print(f"{number}. {question}")
            for region in regions:
                print(f"   where {region}")
        print()
    print(f"{len(rows)} cells, {len(found)} need a decision")
    sys.exit(1 if found else 0)


def cmd_minimize(args):
    spec = load_spec(args.spec)
    rows = load_table(spec, args.table)
    found = problems(spec, rows)
    blocking = [p for p in found if p[0] in ("missing", "not in spec", "no outcome")]
    if blocking:
        raise SystemExit(f"{len(blocking)} cells have no outcome; run check")
    if found:
        print(f"WARNING: {len(found)} cells are undecided; these rules are provisional\n")
    results = {key: result_of(row) for key, row in rows.items()}
    ruleset = build_ruleset(spec, results)
    Path(args.rules).write_text(json.dumps(ruleset, indent=2) + "\n")
    print(markdown(spec, ruleset))
    print(f"\n{len(results)} cells became {len(ruleset['rules'])} rules plus a default")
    for dim, groups in merge_report(spec, results).items():
        for group in groups:
            print(f"equivalent values of {dim}: {' = '.join(group)}")


def cmd_verify(args):
    spec = load_spec(args.spec)
    results = {k: result_of(r) for k, r in load_table(spec, args.table).items()}
    wrong = mismatches(spec, results, json.loads(Path(args.rules).read_text()))
    for key, expected, actual in wrong:
        print(f"{', '.join(key)}: table says {expected}, rules say {actual}")
    print(f"{len(results)} cells checked, {len(wrong)} mismatches")
    sys.exit(1 if wrong else 0)


def cmd_diff(args):
    spec = load_spec(args.spec)
    old = load_table(spec, args.old)
    new = load_table(spec, args.new)
    same = ("same", "")
    changes = {}
    for key in all_keys(spec):
        before = result_of(old[key]) if key in old else ("(new cell)", "")
        after = result_of(new[key])
        if after[0] == NA:
            changes[key] = (NA, "")
        elif before == after:
            changes[key] = same
        else:
            changes[key] = (" ".join(before).strip() + " -> " + " ".join(after).strip(), "")
    ruleset = build_ruleset(spec, changes, default=same)
    changed = sum(1 for value in changes.values() if value != same and value[0] != NA)
    print(markdown(spec, ruleset))
    print(f"\n{changed} of {len(changes)} cells changed")


def cmd_selftest(_):
    spec = {
        "dimensions": {"state": ["a", "b", "c"], "event": ["x", "y"], "flag": ["0", "1"]},
        "dims": ["state", "event", "flag"],
        "state": "state",
    }
    results = {}
    for state, event, flag in all_keys(spec):
        if event == "x":
            results[(state, event, flag)] = ("go", "c")
        elif state == "c":
            results[(state, event, flag)] = (NA, "")
        else:
            results[(state, event, flag)] = ("stay", "b" if state == "a" else "a")
    ruleset = build_ruleset(spec, results)
    assert len(ruleset["rules"]) == 2, ruleset
    assert not mismatches(spec, results, ruleset)
    assert merge_report(spec, results)["state"] == [["a", "b", "c"]], merge_report(spec, results)
    assert merge_report(spec, results)["flag"] == [["0", "1"]]
    broken = dict(results)
    broken[("a", "x", "0")] = ("refuse", "a")
    assert len(mismatches(spec, broken, ruleset)) == 1
    assert len(build_ruleset(spec, broken)["rules"]) == 3
    stays = {k: (r[0], SAME if r[0] == "stay" else r[1]) for k, r in results.items()}
    assert merge_report(spec, stays)["state"] == [["a", "b", "c"]]
    print("selftest passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler, names in [
        ("expand", cmd_expand, ["spec", "table"]),
        ("check", cmd_check, ["spec", "table"]),
        ("minimize", cmd_minimize, ["spec", "table", "rules"]),
        ("verify", cmd_verify, ["spec", "table", "rules"]),
        ("diff", cmd_diff, ["spec", "old", "new"]),
        ("selftest", cmd_selftest, []),
    ]:
        sub = commands.add_parser(name)
        for argument in names:
            sub.add_argument(argument)
        sub.set_defaults(handler=handler)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
