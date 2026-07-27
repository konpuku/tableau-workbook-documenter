# twb_doc_generator — Tableau Workbook Documentation Generator

*[日本語](README.md)*

Analyses a Tableau workbook (.twbx / .twb) and generates documentation
(HTML / Markdown) automatically.

- **Fully local**: no generative AI, no internet connection and no third-party
  libraries (Python standard library only)
- **Built for corporate Windows environments**: runs with just bat / PowerShell /
  Python, and can be distributed with Python bundled for PCs without it
- **Japanese / English**: the output language is detected from the environment,
  and the terminology follows the official Tableau Help wording

## Requirements

- Windows 10/11
- Python 3.10 or later — **PCs without Python can still run it** if you use the
  bundled Python (see below)

## Usage

### 1. Drag and drop (recommended)

Drag a `.twbx` or `.twb` file onto **`generate_doc.bat`**.
The following is created next to the input file (`yyyymmdd` is the run date):

```text
<name>_Documentation_yyyymmdd\
├── <name>_Documentation.html   # open this in a browser (diagrams, links, tooltips)
├── <name>_Documentation.md     # Markdown version (for VS Code / GitHub)
└── images\
    ├── <dashboard>.png          # preview image (thumbnail stored in the workbook)
    └── layout_<dashboard>.svg   # layout diagram (positions and sizes reproduced)
```

**The HTML version opens in any browser**, so Mermaid diagrams, images, table of
contents links and formula tooltips all work without VS Code (mermaid.js is
bundled, everything works offline). Images are embedded in the HTML, so the
single HTML file can be shared on its own.

### 2. Double-click (batch)

Double-click `generate_doc.bat` to process every `.twbx` / `.twb` in that folder
and its parent folder.

### 3. Command line

```powershell
cd twb_doc_generator\app
python -m twbdoc "C:\path\to\workbook.twbx"
python -m twbdoc book1.twbx book2.twb --output C:\docs   # several files, custom output
python -m twbdoc book.twbx --lang en                     # force English
python -m twbdoc book.twbx --no-sample                   # skip reading sample values
```

Exit codes: `0` success / `1` parse error / `2` input error /
`3` Python not found (bat/ps1) / `4` the bundled Python's standard library
cannot be loaded (see "File encryption software" below).

## Output language

The language is detected from the Windows display language (Japanese on a
Japanese system, English otherwise). To override it:

```powershell
python -m twbdoc book.twbx --lang en
$env:TWBDOC_LANG = 'en'    # environment variable (also applies to the bat/ps1 messages)
```

Folder and file names are always in English so that they are safe on any system.

## Distributing to PCs without Python

### Option 1: download a prebuilt zip (easiest)

Download a bundled zip from
[Releases](https://github.com/konpuku/tableau-workbook-documenter/releases),
extract it and distribute it. Users need no installation and no admin rights.

| Asset | Contents | Size |
| --- | --- | --- |
| `...-with-python-hyperapi-win64.zip` | Python + tableauhyperapi (sample values from .hyper extracts) | approx. 84MB |
| `...-with-python-win64.zip` | Python only | approx. 13MB |

### Option 2: set it up yourself

Run this once on a PC with internet access; an installation-free Python
(the python.org embeddable package) is placed in `app\python`:

```powershell
cd twb_doc_generator\app
.\setup_python.ps1                  # Python only
.\setup_python.ps1 -WithHyperApi    # + sample values from .hyper (approx. +225MB)
```

Then simply copy the whole tool folder. To build a zip yourself, run
`.\build_distribution.ps1 [-WithHyperApi]` and it is written to `dist\`.

Redistribution is permitted in both cases (Python is under the PSF License,
tableauhyperapi under Apache-2.0).

### File encryption software

If corporate data-loss-prevention software encrypts `.zip` or `.txt` files, the
bundled Python may fail to start with
`Fatal Python error: Failed to import encodings module`.

To avoid this, the bundled Python contains no file types that such tools
typically target:

- the standard library is extracted into `python\Lib\` instead of `pythonXXX.zip`
- licence and metadata `.txt` files are renamed to `.dat` (still plain text)

If it still fails (exit code `4`), `.pyc` or `.dll` files may also be encrypted.
**Ask your IT administrator to exclude the tool folder from encryption/DRM.**

## What the documentation contains

| Chapter | Contents |
| --- | --- |
| Contents | Table of contents linking to every chapter and section |
| 1. Workbook Overview | Version, build, and counts of each element |
| 2. Data Sources and Preparation | Connections, data model diagram (one Mermaid diagram: box = logical table, dotted line = relationship, solid line = join, inner box = union, keys shown with data types), relationship/join/union tables, field changes (rename, data type, hidden, geographic role), data source and extract filters, live or extract. Workbooks with no relationship/join definitions (extract-only, etc.) show the tables and their fields instead |
| 3. Dashboards | Preview image (workbook thumbnail), size, layout (indented list + layout diagram SVG). Fixed-size dashboards use the same pixel notation as Tableau's Position/Size pane |
| 4. Dashboard Actions | Filter / Highlight / Go to URL / Go to Sheet / Change Set Values / Change Parameter, with how the action is run, source (including excluded sheets), target and fields |
| 5. Worksheets | Title, data sources, calculated fields and parameters used, dashboards the sheet appears on |
| 6. Filters | Shared (context) filters and per-worksheet filters, with the field and the setting ("Keep only A, B", "Exclude C", ranges, etc.) |
| 7. Parameters | Data type, current value and allowable values (Range / List / All) |
| 8. Calculated Fields | Lineage (dependency diagram with links to each field), data type, role, comments (in Tableau and in the formula), referenced fields, worksheets using it, and the formula (internal IDs resolved to display names). Unused fields are flagged with ⚠ |
| 9. Table Calculations | Per-field settings by worksheet (field, aggregation, calculation type, Compute Using) and the default settings stored on the calculated field. "Specific Dimensions" is shown with the ordering fields |
| 10. Aliases | "Member → Alias" table for each field |
| 11. Formatting | Fonts, sizes, colours and other settings (workbook / worksheet / dashboard) |
| 12. Health Check | Automated maintenance checks: unused calculated fields and parameters, duplicate formulas, extract row limits (⚠ Warning); worksheets not on a dashboard, unused data sources, deep dependency chains, comment coverage (ℹ Info). The warning count also appears in chapter 1 |
| 13. Field List by Table (Reference) | Every field with its data type and sample values read from the bundled data |

## Sample values (chapter 13)

Up to five distinct values per field are read from the data bundled in the twbx,
so the documentation can answer "what is actually in this field?".

| Data format inside the twbx | Supported |
| --- | --- |
| .csv / .txt | Yes (standard library only) |
| .xlsx | Yes (standard library only) |
| .hyper (Tableau extract) | Yes, but requires `pip install tableauhyperapi` (a note is shown if it is missing) |
| .xls (legacy Excel) | No |

- Fields that cannot be read are shown as "(not available)" (hidden fields are
  not included in extracts, so they cannot be read)
- Use `--no-sample` to skip sampling entirely (for confidential data)

## Terminology

Terms follow the official Tableau Help in both languages, for example
"Compute Using" / 「次を使用して計算」, "Percent of Total" / 「合計に対する割合」,
"Go to URL" / 「URL に移動」, "Number (whole)" / 「数値 (整数)」, so that the
documentation matches what users see in Tableau Desktop.

- English: <https://help.tableau.com/current/pro/desktop/en-us/default.htm>
- Japanese: <https://help.tableau.com/current/pro/desktop/ja-jp/default.htm>

## Licence

MIT License. See [LICENSE](LICENSE).
