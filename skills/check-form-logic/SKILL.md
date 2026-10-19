---
name: check-form-logic
description: Check a fillable PDF form's hidden calculation logic against the other documents that describe the same rule (a spreadsheet, a user guide), before anyone automates, migrates or rebuilds the process. Runs the form's own scripts and the spreadsheet's own formulas on every possible input, traces each disagreement to the line that causes it, and ends with evidence and questions for the procedure owner. Use this whenever someone is about to build an automation, agent, workflow or new system on top of an existing fillable PDF or Excel calculator, asks whether a form "does what the spreadsheet/guide says", needs to audit a legacy form's scoring, weights, warnings or approval rules, or is migrating a paper or PDF process (for example to Power Platform, Dataverse or an agent platform), even if they don't say "audit" or "reconcile".
---

# Check a form's logic before automating it

Legacy processes often run on fillable PDF forms whose calculations live in scripts nobody reads, next to a spreadsheet and a user guide that claim to describe the same rule. They drift apart, and nobody notices because each person only uses one of them. Automating the form as it is automates its mistakes. This skill finds where the sources disagree, exactly when, and why, so the owner can decide what is intended before anything is built on it.

**Your job is evidence, not rulings.** You never decide which source is right, never edit the original form or spreadsheet, and never present a finding as a bug in one source. Two sources disagreeing is a question for the procedure owner. The skill ends when the owner has the questions.

Work in the form-reconciler repo (the folder containing `reconcile.py`). Run Python with `uv run`. Node is needed to run the form's scripts.

## 0. Triage the form

Find out what kind of form it is before anything else, because it decides what can be checked:

- **Script-driven AcroForm** (fields with calculation JavaScript): the full method below applies.
- **XFA form** (built in LiveCycle Designer; scripts in XML, often FormCalc): the logic can be read but not run here. Report that, and fall back to step 2's claims approach for the scripts you can read.
- **Built-in calculations only** (`AFSimple_Calculate` etc.): run as normal; the shim may need those functions added to `run_pdf.js`.
- **Scanned form, or a form whose rules are written instructions**: there is no code. Treat it like a user guide (step 2).

Then list the sources you have and ask who maintains each. If there is only the form, say so: one source can be checked against its own visible labels (the page may print a weight the script doesn't use), but not reconciled.

## 1. Inventory both sources

```bash
uv run python inspect_sources.py path/to/form.pdf path/to/calculator.xlsx [SHEET]
```

This prints every PDF field with its label on the page, type, flags (`hidden`, `white_text`, `in_margin`), answer options, the fields its script reads, and the script itself, followed by every spreadsheet input (with its allowed answers) and formula (with the text on its row).

Read it closely. Note anything disguised: hidden fields, white text, fields in the margin, document-level helper functions, comments that hint at history ("weights per 2016 table", "Region B"). These are where drift hides.

## 2. Write the mapping

Create `mappings/<form>.py` in the same shape as `mappings/field_visit_risk.py`:

- `PDF`, `XLSX`, `SHEET`: the files.
- `INPUTS`: each PDF answer field → the spreadsheet cell where the same answer goes.
- `NAMES`: each answer field → its readable label, as the form prints it.
- `CELLS`: each PDF calculated field → the spreadsheet cell that holds the same quantity. Include intermediate values (row scores, subtotals), not only results; that is what lets the check trace a disagreement to where it starts. A hidden helper that stands in for a visible value maps to the same cell as that value.
- `OUTPUTS`, `OUTPUT_LABELS`: the fields the person filling in the form actually sees.

This is the one step that needs judgment about meaning. Match by what a field computes, using labels, the fields its script reads, and the formula's row text, never by name similarity alone.

Answer options must match between the two sources (the PDF's shown text before any " / " translation, and the spreadsheet's allowed values). `reconcile.py` stops with an assertion if they don't; when it does, fix the mapping, don't edit the artifacts.

**Check the mapping before trusting the results.** Run a small sample first:

```bash
uv run python reconcile.py --mapping mappings/<form>.py --out runs/<form>/sample.json 2000
```

A wrong mapping looks like a disagreement too, so read every cause it reports: if a mapped pair differs on nearly every input while the fields it reads agree, either the scripts genuinely differ or you mapped two different quantities. Compare a few of the example values it prints against the formula and the script to tell which. Correct the mapping and rerun until every remaining disagreement is explained by the logic, not by the mapping.

## 3. Check every input

```bash
uv run python reconcile.py --mapping mappings/<form>.py --out runs/<form>/results.json
```

With no sample size it runs every combination of answers through both sources, as they are: the form's scripts in Node via `run_pdf.js`, the spreadsheet's formulas in an Excel engine. Nothing is translated, so nothing gets quietly fixed in translation. Expect roughly 15 ms per input per core for the spreadsheet (cached after the first run); the PDF side is fast.

If every combination is too many (above a few million), or the form has free-entry fields (numbers, dates, text), run a large sample instead and say in the report that the results are sampled, not exhaustive. Never describe a sampled result as "every input".

The output names each **cause** (the script or formula where a disagreement starts), what it changes on the visible results and how often, and **exactly when** it happens where a simple condition exists ("Hazardous materials is Possible or Likely, and Prior hostile contact is not Confirmed"). Disagreements in hidden values that never change a visible result are listed as **latent**; report them too, because a later change to the form can expose them.

## 4. State plain facts

For each cause, establish one or two facts by running the artifacts, not by reading the code. Reading code is where misinterpretation creeps in; behaviour over every input is checkable. Write a short script like `facts.py`'s `main()` (which is the worked example for the Field Visit form), using its helpers:

- `load(mapping)`: every input run through both sources, with every mapped value.
- `effective_weights(values, scores, ...)`: if a value is exactly a weighted sum of answer scores, the weights each source actually applies. This is how a hidden weight of 1 against a printed 10 shows up.
- `additive(values, ...)`: whether a score is a plain sum of per-answer amounts.
- `conditions.explain(rows, mask, ...)`: the exact condition under which something happens.

Only claim what a check confirms. If a fact can't be established exactly, say "depends on the combination of answers" rather than guessing a rule.

## 5. Test the written sources

For a user guide, written instructions or a scanned form, turn each statement about the rule into a claim you can test against the full input table: "warning if the highest answer is selected for any Critical factor" becomes a condition you evaluate on every input against each source's actual result. Record for each claim whether it agrees with the form, the spreadsheet, both or neither, and where in the document it is (page and section). Statements too vague to test ("overall risk is calculated from the three sections") are **underspecified**: list them, because they are why the guide alone can't settle anything. A guide that contradicts itself is a finding in its own right.

## 6. Write the owner questions

One question per cause, for the procedure owner, who is usually not technical:

- Describe what each source does in the form's own words, with the exact condition and how often it matters.
- Never mention scripts, fields, cells or formulas.
- Offer the options the sources already take, plus "something else". Don't recommend one.
- Build the question in code from the facts (see `questions()` in `owner_questions.py`) so every number and condition is pulled from what was checked, not retyped.

For a bilingual department, translate each question with `owner_questions.translate(co, text, terms)`, passing the form's own bilingual terms so the translation matches what staff see. Someone fluent should still read the French before it goes out.

## 7. Report

Write `runs/<form>/report.md` with this structure:

```markdown
# <Form name>: does the form do what its sources say?

## Sources checked
<each source, its version or date if known, who maintains it, and anything not checked (and why)>

## Coverage
<every input (N combinations), or a sample of N and why>

## Disagreements
### <plain-language title>
- Form: <what it does>   Spreadsheet: <what it does>   Guide: <what it says, page>
- Exactly when: <condition>, or "depends on the combination of answers"
- Changes: <visible result> on <n> of <N> (<share>)
- Starts at: <PDF field and script excerpt> vs <sheet!cell and formula>

## Latent differences
## Guide claims
<agrees / contradicts / underspecified, with page references>

## Questions for the owner
<numbered, English, then French if needed>

## Not checked
```

Lead with the disagreements that change what the person filling in the form sees, especially approvals and warnings. Keep the owner's decision open: the last line of every finding is a question, not a verdict.

## After the owner answers

The owner's answers are a new source with authority: record them (who, when, which option) next to the report. Rerun the check against the settled rule, and turn every disagreement found into a regression test, so the check reruns whenever the form or spreadsheet changes. That is the step that lets the department maintain this without you.
