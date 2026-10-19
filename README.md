# Form reconciler

Before you automate a government form, check what it actually computes.

This repo is the working code behind [Before You Automate the Form](https://claude.ai/artifact/J3vanRr6G38VXWTsCyjcVZ), a Day One story from a forward deployed engineering engagement. It takes a legacy fillable PDF and the spreadsheet that is supposed to implement the same rules, runs both exactly as they are on every possible input, and reports where they disagree, why, and exactly when.

**Everything here is synthetic.** The form, spreadsheet and user guide are modeled on a real reconciliation I did on a federal risk-assessment form, but every name, weight and threshold is invented.

## What it found

Checked on all 262,144 possible ways to fill in the form:

| What the form shows | Disagree | Cause |
|---|---|---|
| Supervisor approval required | 29.7% | A widened warning rule, and a stale weight |
| Critical-factor warning | 37.5% | The form warns from "Possible" up; the spreadsheet only at "Confirmed" |
| Overall risk | 39.4% | A white-text field in the margin uses a weight of 1 where the page and spreadsheet say 10 |
| Uncertainty level | 10.7% | The form multiplies section totals; the spreadsheet adds them |

A fourth difference (a missing minimum on the mitigation total) never changes what the form shows today, and is reported as latent.

## How it works

1. **Extract.** Pull the JavaScript out of every PDF form field, including hidden and disguised ones (`pikepdf`), and the formulas out of the spreadsheet (`openpyxl`).
2. **Run both as they are.** The form's scripts run in Node through a small implementation of Acrobat's form API (`run_pdf.js`). The spreadsheet's formulas run in an Excel engine (`formulas`). Nothing is translated, so nothing gets quietly fixed in translation.
3. **Check every input.** Every field is a dropdown, so there are exactly 4⁹ = 262,144 possible assessments. All of them go through both.
4. **Trace and state exactly when.** Follow each disagreement back through the form's field dependencies to the script where it starts (`reconcile.py`), describe the inputs where it happens as readable conditions (`conditions.py`), and recover plain facts from behaviour, such as the weight each version actually applies, by exact fit over all inputs (`facts.py`).
5. **Ask the owner.** Build one question per disagreement from those checked facts, and translate it into Canadian French with Cohere's Command A Translate (`owner_questions.py`).

The model translates. It never decides what is true. An earlier version asked Command A+ to draft the questions; given the same facts it was accurate in one run and wrong in the next, so drafting moved into code.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node.

```bash
uv sync
uv run python reconcile.py          # every input; the spreadsheet half takes a few minutes the first time, then it's cached
uv run python reconcile.py 5000     # or a random sample, for a quick look
uv run python facts.py              # plain facts recovered from behaviour
```

To regenerate the owner questions, put a Cohere API key in `cohere.env` as `COHERE_API_KEY=...`, then:

```bash
uv run --env-file cohere.env python owner_questions.py
```

To try the form with its scripts running, open `artifacts/field-visit-risk-assessment.pdf` in Firefox or Acrobat, or serve the repo and use the pdf.js viewer:

```bash
(cd viewer && npm install)
python3 -m http.server 8765
```

Then open `http://localhost:8765/viewer/index.html`.

## What's here

| Path | What it is |
|---|---|
| `artifacts/` | The synthetic form (PDF), spreadsheet and user guide |
| `procedure.py` | The fictional procedure, and the reconciled rule |
| `build_artifacts.py`, `build_guide.py` | Generate the artifacts, with the disagreements planted |
| `reconcile.py`, `run_pdf.js`, `mapping.py` | The check |
| `conditions.py`, `facts.py` | Exact conditions and plain facts from the full input table |
| `owner_questions.py` | Questions for the procedure owner, English and French |
| `results.json`, `facts.json`, `owner_questions.json` | Output of the last run |
| `tests/answer_key.json` | What was planted. Used to check the tool; never an input |

## Scope

Works as shown for script-driven AcroForms. XFA forms need an engine for their FormCalc scripts. Scanned forms and written instructions have no code; they go the way the user guide does here, as claims tested against what can be run.

Valerie Kim
