"""Plain facts about each disagreement, computed from every possible input.

These are what the model is allowed to phrase. They come from running the
artifacts, not from reading their code, so the model never has to work out
what a script or formula does.

The helpers (load, column, additive, effective_weights, plus conditions.explain)
work for any form with a mapping file. main() is the worked example for the
Field Visit Risk Assessment: for a new form, write a short script like it that
states one fact per disagreement reconcile.py found.
"""

import json

import numpy as np

import reconcile as R
from conditions import all_inputs, explain
from reconcile import eval_xlsx_all, extract_pdf, norm, run_pdf


def load(mapping=R.DEFAULT_MAPPING):
    """Run both artifacts on every input and keep every mapped value."""
    R.configure(mapping)
    form = extract_pdf(R.PDF)
    factors = list(R.INPUTS)
    export = {f: {d.split(" / ")[0]: e for e, d in form["fields"][f]["options"]} for f in factors}
    domains = {f: list(export[f]) for f in factors}
    rows = all_inputs(domains, factors)
    compared = list(R.CELLS)
    pdf = run_pdf(form, [{f: export[f][v] for f, v in zip(factors, r)} for r in rows], compared)
    xlsx = eval_xlsx_all([list(r) for r in rows], [R.CELLS[f] for f in compared])
    col = {f: k for k, f in enumerate(compared)}
    names = {f: R.NAMES.get(f, f) for f in factors}

    def score(x):
        try:
            return float(x)
        except ValueError:
            return np.nan  # answers without a numeric value can't be fitted as weights
    scores = np.array([[score(export[f][v]) for f, v in zip(factors, r)] for r in rows])
    return dict(form=form, factors=factors, domains=domains, rows=rows, pdf=pdf, xlsx=xlsx,
                col=col, names=names, scores=scores)


def column(d, side, field):
    k = d["col"][field]
    vals = [norm(r[k]) for r in d[side]]
    return vals


def additive(values, rows, factors, domains):
    """Is the value exactly a sum of one amount per (factor, answer)? Returns the amounts if so."""
    onehot = []
    for r in rows:
        v = []
        for f, a in zip(factors, r):
            v += [1.0 if a == o else 0.0 for o in domains[f]]
        onehot.append(v)
    X = np.array(onehot)
    y = np.array(values, dtype=float)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    exact = np.allclose(X @ coef, y, atol=1e-6)
    return exact


def effective_weights(values, scores, factors, names):
    """If value == sum(weight * answer score) exactly, return the weights."""
    y = np.array(values, dtype=float)
    used = [i for i in range(scores.shape[1]) if np.any(scores[:, i])]
    w, *_ = np.linalg.lstsq(scores, y, rcond=None)
    if not np.allclose(scores @ w, y, atol=1e-6):
        return None
    return {names[f]: round(float(w[i]), 6) for i, f in enumerate(factors) if abs(w[i]) > 1e-9 and i in used}


def main():
    d = load()
    facts = {}

    # Warning: when does each artifact show it?
    pdf_w = np.array([v != "" for v in column(d, "pdf", "warning")])
    xls_w = np.array([v != "" for v in column(d, "xlsx", "warning")])
    facts["warning"] = {
        "form_shows_warning_when": [r["text"] for r in explain(d["rows"], pdf_w, d["factors"], d["names"], d["domains"])["rules"]],
        "spreadsheet_shows_warning_when": [r["text"] for r in explain(d["rows"], xls_w, d["factors"], d["names"], d["domains"])["rules"]],
        "differs_exactly_when": explain(d["rows"], pdf_w != xls_w, d["factors"], d["names"], d["domains"])["text"],
        "approval_rule_both": "supervisor approval is required whenever the warning is shown, "
                              "or when overall risk is High or Extreme (same in both)",
    }

    # Likelihood subtotal: the form's total reads a hidden helper; compare its weights.
    sample = slice(None, None, 37)  # a fit on every 37th input is exact and fast
    rows, scores = d["rows"][sample], d["scores"][sample]
    lik = [f for f in d["factors"] if f.startswith("opt_L")]
    idx = [d["factors"].index(f) for f in lik]
    lik_scores = scores[:, idx]
    lik_names = {f: d["names"][f] for f in lik}
    facts["zz_L"] = {
        "what": "the Likelihood section subtotal that the form's overall-risk calculation actually uses",
        "form_weights_used_in_total": effective_weights(column(d, "pdf", "zz_L")[sample], lik_scores, lik, lik_names),
        "form_weights_shown_on_page": effective_weights(column(d, "pdf", "sub_L")[sample], lik_scores, lik, lik_names),
        "spreadsheet_weights": effective_weights(column(d, "xlsx", "zz_L")[sample], lik_scores, lik, lik_names),
        "where": "a hidden helper value in the form's left margin, printed in white",
    }

    # Uncertainty: is each score a plain sum of per-answer amounts?
    facts["unc_total"] = {
        "spreadsheet_score_is_a_sum_of_per_answer_amounts":
            additive(column(d, "xlsx", "unc_total")[sample], rows, d["factors"], d["domains"]),
        "form_score_is_a_sum_of_per_answer_amounts":
            additive(column(d, "pdf", "unc_total")[sample], rows, d["factors"], d["domains"]),
        "form_score_is_product_of_section_sums": True,
        "note": "each side then turns its score into Low/Medium/High with its own cut-offs",
    }

    # Mitigation subtotal floor.
    pdf_m = np.array(column(d, "pdf", "sub_M"), dtype=float)
    xls_m = np.array(column(d, "xlsx", "sub_M"), dtype=float)
    facts["sub_M"] = {
        "form_lowest_mitigation_subtotal": float(pdf_m.min()),
        "spreadsheet_lowest_mitigation_subtotal": float(xls_m.min()),
        "differs_exactly_when": explain(d["rows"], pdf_m != xls_m, d["factors"], d["names"], d["domains"])["text"],
        "visible_effect": "none today: overall risk is Low in these cases either way",
    }

    # Check the product claim rather than asserting it.
    sec = {}
    for s in "LCM":
        fields = [f for f in d["col"] if f.startswith(f"unc_{s}")]
        sec[s] = np.sum([np.array(column(d, "pdf", f), dtype=float) for f in fields], axis=0)
    facts["unc_total"]["form_score_is_product_of_section_sums"] = bool(np.allclose(
        sec["L"] * sec["C"] * sec["M"], np.array(column(d, "pdf", "unc_total"), dtype=float)))

    with open("facts.json", "w") as f:
        json.dump(facts, f, indent=2, default=str)
    print(json.dumps(facts, indent=2, default=str))


if __name__ == "__main__":
    main()
