---
name: twbdoc-ci
description: Run twbdoc CI checks on the workbook open in Tableau Studio (unused calculated fields and parameters, unresolved references, invalid fields on sheets, duplicate formulas, default sheet names, placeholder calc names, uncommented complex formulas, extract row limits, inconsistent font sizes and fonts). Use after editing a workbook, when the user asks to "check", "lint", "CI", "review" or "clean up" the workbook, or before saving or publishing. Explains each finding, proposes a fix, and applies it only after the user approves.
---

# twbdoc CI for the open workbook

This skill checks the workbook that is open right now (unsaved edits included)
with twbdoc, then helps the user fix what it finds. It never changes the
workbook without the user's explicit approval.

## 1. Run the check

Run this command file. It starts twbdoc with the Python that was found when the
skill was installed (often the Python bundled with twbdoc, so do not call
`python` yourself: it may not be on PATH). It reads the open workbook through the
Tableau External Client API and prints a JSON report:

```
"<this skill folder>\scripts\run_ci.cmd"
```

- Exit code 0 or 5 means the check ran (5 = there are errors). Read the JSON on stdout.
- Exit code 6 means the External Client API is not reachable: ask the user to turn on
  Help > Settings & Performance > External Client API Access and restart Tableau.
- Exit code 3, or `run_ci.cmd` missing or failing to start Python, means the skill
  needs reinstalling: ask the user to double-click `install_skill.bat` in the twbdoc
  folder again.

The report has `summary` (error / warning / info counts) and `findings`. Each
finding has `id`, `rule`, `severity`, `target`, `message`, `fix_hint` and
`fix_tools` (Tableau MCP tools that can help fix it).

If the user also runs `python -m twbdoc watch`, the same findings are on the
live dashboard at http://127.0.0.1:8765/ — mention it once if it helps.

## 2. Report

Give a short summary first: counts by severity, then the errors and warnings as a
list of `target — what is wrong — proposed fix`. Group info items into one line
each per rule unless the user asks for detail. Do not dump the raw JSON.

## 3. Propose and apply fixes (only with approval)

For each fix, say exactly what will change and ask the user to approve it. Apply
one approved fix at a time, then run the check again and confirm the finding is
gone (its `id` no longer appears).

| rule | how to fix |
|---|---|
| `invalid-field` (error) | Find the sheet and shelf in the message. Replace the field or remove it with `remove-field` / `refine-worksheet`. |
| `broken-reference` | Use `search-workbook-fields` to find the intended field, check the new formula with `validate-calculated-field`, then update it with `author-calc`. |
| `unused-calc`, `unused-parameter` | The API cannot delete calculated fields or parameters. Confirm with `search-workbook-fields` that nothing uses it, then ask the user to delete it in the Data pane (right-click > Delete), or to keep it and add a comment explaining why. |
| `duplicate-formula` | Propose keeping one field. Repoint references with `author-calc`, then ask the user to delete the others by hand. |
| `default-sheet-name` | Suggest a descriptive name based on the sheet's content (`get-sheets`), and rename with `rename-sheet` after approval. |
| `placeholder-calc-name` | Suggest a meaningful name from the formula and rename it with `author-calc`. |
| `uncommented-complex-calc` | Draft a `//` comment that explains the intent, show it, and add it with `author-calc` (validate with `validate-calculated-field` first). |
| `orphan-worksheet` | Ask whether it is a scratch sheet (hide or delete it with `delete-sheet`) or should be placed on a dashboard. |
| `extract-row-limit` | Ask the user to remove the row limit in Edit Extract. |
| `inconsistent-font-size` | The message names the sheet, the role (title, tooltip, axis title…) and the size to match. Confirm the difference is not intended (a KPI title may be bigger on purpose), then set that sheet's size with `format-worksheets`. For many sheets, propose the change for all of them at once and apply after one approval. |
| `naming-convention`, `naming-kind-mismatch` | The message quotes the team rule. Propose a new name that follows it (for a mismatch, say which part of the name no longer matches the formula), then rename with `author-calc` or `rename-sheet` after approval. Renaming a calculated field does not break formulas that use it. Propose several renames together for one approval when there are many. |
| `naming-whitespace` | Propose the name without the extra spaces and rename after approval. |
| `inconsistent-font-family` | Propose one spelling or one allowed font and list the sheets that change; apply with `format-worksheets` after approval. |
| `deep-dependency`, `comment-coverage`, `unused-datasource` | Informational: explain and suggest, do not change anything unless asked. |

Rules:

- Never delete sheets, fields or data sources, and never rewrite formulas, without approval.
- Do not save the workbook unless the user asks.
- A user who wants to accept a finding permanently can add its `id` to
  `"ignore"` in a `.twbdoc.json` next to the workbook. Offer this when they say a
  finding is intentional.
