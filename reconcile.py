"""Check a fillable PDF's hidden logic against a spreadsheet for the same procedure.

1. Extract the PDF's calculation scripts and the spreadsheet's formulas.
2. Run both, as-is, on every possible combination of answers.
3. Report where they disagree, which script or formula causes it, and exactly when.

Usage: uv run python reconcile.py [SAMPLE_SIZE]   (default: every possible input)
"""

import gzip
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from multiprocessing import Pool

import formulas
import numpy as np
import pikepdf
from openpyxl import load_workbook

from conditions import all_inputs, explain
from mapping import CELLS, INPUTS, OUTPUT_LABELS, OUTPUTS
from procedure import FACTORS

PDF = "artifacts/field-visit-risk-assessment.pdf"
XLSX = "artifacts/risk-factor-values.xlsx"
SHEET = "Assessment"
BOOK = "risk-factor-values.xlsx"


# --- Extraction ------------------------------------------------------------

def extract_pdf(path):
    pdf = pikepdf.open(path)
    acro = pdf.Root.AcroForm
    page_w = float(pdf.pages[0].MediaBox[2])
    fields = {}
    for f in acro.Fields:
        name = str(f.T)
        rect = [float(v) for v in f.Rect]
        da = str(f.get("/DA", ""))
        calc = ""
        if "/AA" in f and "/C" in f.AA:
            calc = str(f.AA.C.JS)
        field = {
            "type": str(f.FT),
            "default": str(f.get("/V", "")),
            "calculate": calc,
            "depends_on": sorted(set(re.findall(r'getField\("([^"]+)"\)', calc))),
            "rect": rect,
            "white_text": bool(re.search(r"\b1 1 1 rg\b", da)),
            "in_margin": rect[0] < 0.07 * page_w or rect[2] > 0.95 * page_w,
            "hidden": bool(int(f.get("/F", 0)) & 2),
        }
        if "/Opt" in f:
            field["options"] = [[str(o[0]), str(o[1])] for o in f.Opt]
        fields[name] = field
    # Helpers called with a list of names, e.g. sumFields(this, ["a", "b"]).
    for field in fields.values():
        for args in re.findall(r"sumFields\(this, \[([^\]]*)\]\)", field["calculate"]):
            field["depends_on"] = sorted(set(field["depends_on"]) | set(re.findall(r'"([^"]+)"', args)))
    doc_js = []
    if "/Names" in pdf.Root and "/JavaScript" in pdf.Root.Names:
        names = pdf.Root.Names.JavaScript.Names
        doc_js = [str(names[i + 1].JS) for i in range(0, len(names), 2)]
    return {
        "fields": fields,
        "calculation_order": [str(f.T) for f in acro.CO],
        "document_js": doc_js,
    }


def extract_xlsx(path):
    ws = load_workbook(path)[SHEET]
    cells = {}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                cells[c.coordinate] = c.value
    choices = {}
    for dv in ws.data_validations.dataValidation:
        opts = dv.formula1.strip('"').split(",")
        for ref in str(dv.sqref).split():
            choices[ref] = opts
    return {"formulas": cells, "choices": choices}


# --- Running ---------------------------------------------------------------

def run_pdf(form, inputs, fields):
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f_form, \
         tempfile.NamedTemporaryFile("w", suffix=".json") as f_in, \
         tempfile.NamedTemporaryFile("w", suffix=".json") as f_out:
        json.dump(form, f_form)
        json.dump(inputs, f_in)
        json.dump(fields, f_out)
        for f in (f_form, f_in, f_out):
            f.flush()
        out = subprocess.run(["node", "--max-old-space-size=4096", "run_pdf.js", f_form.name, f_in.name, f_out.name],
                             capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def compile_xlsx(input_cells, output_cells):
    xl = formulas.ExcelModel().loads(XLSX).finish()
    ref = lambda c: f"'[{BOOK}]{SHEET.upper()}'!{c}"
    fn = xl.compile(inputs=[ref(c) for c in input_cells], outputs=[ref(c) for c in output_cells])

    def run(values):
        res = fn(*values)
        return [r.value[0][0] if hasattr(r, "value") else r for r in res]
    return run


def norm(v):
    """Compare like a person reading the form would."""
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, str):
        v = v.split(" / ")[0].strip()  # bilingual "Yes / Oui" -> "Yes"
        try:
            return float(v)
        except ValueError:
            return v
    if isinstance(v, (int, float)):
        return float(v)
    return v


# --- Comparing -------------------------------------------------------------

def root_causes(field, diverges, form, seen=None):
    """The fields whose own script introduces a divergence feeding `field`."""
    seen = seen or set()
    if field in seen:
        return set()
    seen.add(field)
    upstream = [d for d in form["fields"][field]["depends_on"] if d in CELLS and diverges.get(d)]
    if not upstream:
        return {field}
    causes = set()
    for d in upstream:
        causes |= root_causes(d, diverges, form, seen)
    return causes


def eval_xlsx_all(xlsx_inputs, output_cells, workers=os.cpu_count()):
    """Run the spreadsheet on every input, in parallel, cached by file content."""
    digest = hashlib.sha256(open(XLSX, "rb").read()).hexdigest()[:16]
    cache = f"results/xlsx-{digest}-{len(xlsx_inputs)}.json.gz"
    if os.path.exists(cache):
        with gzip.open(cache, "rt") as f:
            return json.load(f)
    chunks = [xlsx_inputs[i:i + 2000] for i in range(0, len(xlsx_inputs), 2000)]
    with Pool(workers, initializer=_init_xlsx, initargs=(list(INPUTS.values()), output_cells)) as pool:
        out = [row for part in pool.imap(_run_xlsx_chunk, chunks) for row in part]
    os.makedirs("results", exist_ok=True)
    with gzip.open(cache, "wt") as f:
        json.dump(out, f)
    return out


_xlsx_fn = None


def _init_xlsx(input_cells, output_cells):
    global _xlsx_fn
    _xlsx_fn = compile_xlsx(input_cells, output_cells)


def _run_xlsx_chunk(chunk):
    return [[norm(v) for v in _xlsx_fn(x)] for x in chunk]


def main(sample=None, seed=7):
    form = extract_pdf(PDF)
    sheet = extract_xlsx(XLSX)

    hidden = [n for n, f in form["fields"].items() if f["hidden"]]
    disguised = [n for n, f in form["fields"].items() if f["white_text"] or f["in_margin"]]
    n_scripts = sum(1 for f in form["fields"].values() if f["calculate"])
    print(f"PDF: {len(form['fields'])} fields, {n_scripts} calculation scripts, "
          f"{len(form['document_js'])} document-level script(s)")
    print(f"  {len(hidden)} hidden fields (never shown on the form)")
    for n in disguised:
        f = form["fields"][n]
        print(f"  disguised field '{n}': white text={f['white_text']}, in margin={f['in_margin']}, "
              f"read by: {[m for m, g in form['fields'].items() if n in g['depends_on']]}")
    print(f"Spreadsheet: {len(sheet['formulas'])} formulas, {len(sheet['choices'])} input cells")

    # Each factor's answers, as the form labels them; the same answer goes to both artifacts.
    factors = list(INPUTS)
    export = {f: {d.split(" / ")[0]: e for e, d in form["fields"][f]["options"]} for f in factors}
    domains = {f: list(export[f]) for f in factors}
    for f, cell in INPUTS.items():
        assert domains[f] == sheet["choices"][cell], (f, domains[f], sheet["choices"][cell])
    rows = all_inputs(domains, factors)
    if sample:
        rows = rows[random.Random(seed).sample(range(len(rows)), sample)]
    n = len(rows)
    what = f"a random sample of {n}" if sample else f"all {n:,} possible"
    print(f"Checking {what} assessments" + ("" if sample else " (every combination of answers)") + ".")

    compared = list(CELLS)
    print("Running them through the PDF's own scripts...")
    pdf_out = run_pdf(form, [{f: export[f][v] for f, v in zip(factors, r)} for r in rows], compared)
    print("Running them through the spreadsheet's own formulas (cached after the first run)...")
    xlsx_out = eval_xlsx_all([list(r) for r in rows], [CELLS[f] for f in compared])

    col = {f: k for k, f in enumerate(compared)}
    diverges = np.array([[norm(p[k]) != x[k] for k in range(len(compared))] for p, x in zip(pdf_out, xlsx_out)])

    # Root cause of each diverging output, per input.
    cause_mask = defaultdict(lambda: np.zeros(n, dtype=bool))   # (cause, output) -> inputs
    own_mask = defaultdict(lambda: np.zeros(n, dtype=bool))     # field whose own script differs
    for i in range(n):
        d = {f: bool(diverges[i, col[f]]) for f in compared}
        for f in compared:
            if d[f] and root_causes(f, d, form) == {f}:
                own_mask[f][i] = True
        for o in OUTPUTS:
            if d[o]:
                for c in root_causes(o, d, form):
                    cause_mask[(c, o)][i] = True

    names = {f: next(en for fid, _c, en, *_ in FACTORS if f == f"opt_{fid}") for f in factors}
    results = {"n_inputs": n, "exhaustive": not sample, "outputs": {}, "causes": [], "latent": []}
    print(f"\nOf {what} assessments, the PDF and the spreadsheet disagree on:")
    for o in OUTPUTS:
        k = int(diverges[:, col[o]].sum())
        results["outputs"][o] = {"label": OUTPUT_LABELS[o], "diverging": k, "share": k / n}
        print(f"  {OUTPUT_LABELS[o]:<30} {k:>8,}  ({k / n:.1%})")

    def example(mask, field):
        i = int(np.argmax(mask))
        return {"answers": {names[f]: v for f, v in zip(factors, rows[i])},
                "pdf": {o: pdf_out[i][col[o]] for o in OUTPUTS} | {field: pdf_out[i][col[field]]},
                "spreadsheet": {o: xlsx_out[i][col[o]] for o in OUTPUTS} | {field: xlsx_out[i][col[field]]}}

    print("\nCauses (the script or formula where the disagreement starts), and exactly when:")
    causes = sorted({c for c, _ in cause_mask}, key=lambda c: -sum(m.sum() for (cc, _), m in cause_mask.items() if cc == c))
    for cause in causes:
        f = form["fields"][cause]
        entry = {
            "pdf_field": cause,
            "hidden": f["hidden"],
            "disguised": f["white_text"] or f["in_margin"],
            "pdf_script": f["calculate"],
            "spreadsheet_cell": f"{SHEET}!{CELLS[cause]}",
            "spreadsheet_formula": sheet["formulas"].get(CELLS[cause]),
            "own_value_differs_on": int(own_mask[cause].sum()),
            "effects": [],
        }
        tag = "  [WHITE TEXT IN MARGIN]" if entry["disguised"] else ("  [HIDDEN FIELD]" if entry["hidden"] else "")
        print(f"\n- PDF field '{cause}'{tag} vs {entry['spreadsheet_cell']}")
        print("  PDF script:  " + f["calculate"].replace("\n", "\n               "))
        print(f"  Spreadsheet: {entry['spreadsheet_formula']}")
        print(f"  Its own value differs on {entry['own_value_differs_on']:,} of {n:,} inputs.")
        for o in OUTPUTS:
            mask = cause_mask.get((cause, o))
            if mask is None or not mask.any():
                continue
            cond = explain(rows, mask, factors, names, domains)
            entry["effects"].append({"output": OUTPUT_LABELS[o], "inputs": int(mask.sum()),
                                     "share": float(mask.mean()), "when": cond, "example": example(mask, cause)})
            print(f"  -> {OUTPUT_LABELS[o]} differs on {int(mask.sum()):,} inputs ({mask.mean():.1%})")
            if cond["exact"] and not cond.get("depends_on"):
                print(f"     exactly when: {cond['text']}")
            else:
                print(f"     depends on: {', '.join(cond['depends_on'])}")
                for r in cond["rules"][:3]:
                    print(f"     mostly when: {r['text']}  "
                          f"(precision {r['precision']:.0%}, covers {r['coverage']:.0%})")
        results["causes"].append(entry)

    latent = [c for c in own_mask if c not in causes and c not in OUTPUTS and own_mask[c].any()]
    if latent:
        print("\nLatent (differs in a hidden score, but never changes what the form shows):")
    for cause in latent:
        f = form["fields"][cause]
        mask = own_mask[cause]
        cond = explain(rows, mask, factors, names, domains)
        results["latent"].append({
            "pdf_field": cause, "inputs": int(mask.sum()), "when": cond,
            "pdf_script": f["calculate"], "spreadsheet_cell": f"{SHEET}!{CELLS[cause]}",
            "spreadsheet_formula": sheet["formulas"].get(CELLS[cause]), "example": example(mask, cause),
        })
        print(f"\n- PDF field '{cause}' vs {SHEET}!{CELLS[cause]}: {int(mask.sum()):,} inputs")
        print(f"  exactly when: {cond['text']}" if cond["exact"] else f"  depends on: {cond['depends_on']}")

    with open("results.json", "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print("\nWrote results.json")


if __name__ == "__main__":
    # No argument: every possible input. A number: a random sample of that size.
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
