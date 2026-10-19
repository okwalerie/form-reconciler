"""Questions for the procedure owner, built from verified facts.

The English question is generated in code from facts.json, so every claim in it
is something we checked on all 262,144 possible assessments. Cohere's
translation model turns it into Canadian French, using the form's own terms.

(In testing, asking Command A+ to draft the questions from the same facts gave
accurate questions in one run and inaccurate ones in another, so drafting
stays deterministic and the model only translates.)

Usage: uv run --env-file cohere.env python owner_questions.py
"""

import json
import os

import cohere

from procedure import CATEGORY_FR, FACTORS

TRANSLATE_MODEL = "command-a-translate-08-2025"
N = 262_144


def pct(n):
    return f"{n / N:.0%}"


def effects(results, field):
    entry = next(c for c in results["causes"] if c["pdf_field"] == field)
    return {e["output"]: e for e in entry["effects"]}


def questions(results, facts):
    qs = []

    w = facts["warning"]
    e = effects(results, "warning")
    qs.append({
        "pdf_field": "warning",
        "title": "When should the critical factor warning appear?",
        "question": (
            "The form and the spreadsheet disagree on when the single critical factor warning appears. "
            f"They differ exactly when {w['differs_exactly_when'].replace(' and ', ', and ')}: "
            "the form shows the warning, and so requires supervisor approval; the spreadsheet does not. "
            f"This affects {pct(e['Critical-factor warning']['inputs'])} of possible assessments "
            f"and changes the approval requirement for {pct(e['Supervisor approval required']['inputs'])}. "
            "Which is intended? (a) The form: warn when hazardous materials is Possible or higher. "
            "(b) The spreadsheet: warn only when a critical factor is Confirmed. (c) Something else."
        ),
    })

    z = facts["zz_L"]
    factor = next(f for f in z["spreadsheet_weights"]
                  if z["form_weights_used_in_total"][f] != z["spreadsheet_weights"][f])
    used, shown, sheet = (int(z[k][factor]) for k in
                          ("form_weights_used_in_total", "form_weights_shown_on_page", "spreadsheet_weights"))
    e = effects(results, "zz_L")
    qs.append({
        "pdf_field": "zz_L",
        "title": f"What weight should \"{factor}\" have?",
        "question": (
            f"The form shows a weight of {shown} for \"{factor}\", but its overall risk calculation uses "
            f"a weight of {used} (from a hidden value in the margin). The spreadsheet uses {sheet}. "
            f"As a result, overall risk differs on {pct(e['Overall risk']['inputs'])} of possible assessments "
            f"and supervisor approval on {pct(e['Supervisor approval required']['inputs'])}. "
            f"Which weight is intended? (a) {used}. (b) {sheet}. (c) Something else."
        ),
    })

    u = facts["unc_total"]
    assert u["form_score_is_product_of_section_sums"] and u["spreadsheet_score_is_a_sum_of_per_answer_amounts"]
    e = effects(results, "unc_total")
    qs.append({
        "pdf_field": "unc_total",
        "title": "How should the uncertainty level be calculated?",
        "question": (
            "The form calculates the uncertainty score by multiplying the Likelihood, Consequence and "
            "Mitigation totals. The spreadsheet adds the amounts for every answer. Each then uses its own "
            "cut-offs for Low, Medium and High, and the uncertainty level differs on "
            f"{pct(e['Uncertainty level']['inputs'])} of possible assessments. "
            "Which method is intended? (a) Multiply the section totals, as the form does. "
            "(b) Add them, as the spreadsheet does. (c) Something else."
        ),
    })

    m = facts["sub_M"]
    latent = next(c for c in results["latent"] if c["pdf_field"] == "sub_M")
    qs.append({
        "pdf_field": "sub_M",
        "latent": True,
        "title": "Should the mitigation total have a minimum?",
        "question": (
            "When all three mitigation measures (Check-in plan, Second person attending, Satellite "
            "communicator) are In place and tested, the form's mitigation total is "
            f"{int(m['form_lowest_mitigation_subtotal'])}, while the spreadsheet never goes below "
            f"{int(m['spreadsheet_lowest_mitigation_subtotal'])}. This affects {latent['inputs']:,} possible "
            "assessments and changes nothing the form shows today, because overall risk is Low either way. "
            "But a total of 0 cancels out every other answer, so a future change to the cut-offs could "
            "expose it. Is a minimum intended? (a) No minimum, as the form does. (b) A minimum of 1, as the "
            "spreadsheet does. (c) Something else."
        ),
    })
    return qs


def glossary():
    lines = ["fillable PDF form = formulaire PDF à remplir", "spreadsheet = chiffrier",
             "Overall risk = Risque global", "uncertainty level = niveau d'incertitude",
             "single critical factor warning = avertissement de facteur critique unique",
             "supervisor approval = approbation du superviseur"]
    lines += [f"{c} = {fr}" for c, fr in CATEGORY_FR.items()]
    seen = set()
    for _fid, _cat, en, fr, _w, options in FACTORS:
        lines.append(f"{en} = {fr}")
        for o_en, o_fr, _s in options:
            if o_en not in seen:
                seen.add(o_en)
                lines.append(f"{o_en} = {o_fr}")
    return "\n".join(lines)


def translate(co, text):
    prompt = (
        "Translate the following text into Canadian French for a Government of Canada program manager. "
        "Follow Translation Bureau (TERMIUM Plus) usage, not France French. Use these terms exactly:\n"
        f"{glossary()}\n\nReply with the translation only.\n\nText:\n{text}"
    )
    resp = co.chat(model=TRANSLATE_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    return next(c.text for c in resp.message.content if c.type == "text").strip()


def main():
    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    results = json.load(open("results.json"))
    facts = json.load(open("facts.json"))
    out = []
    for q in questions(results, facts):
        q["title_fr"] = translate(co, q["title"])
        q["question_fr"] = translate(co, q["question"])
        out.append(q)
        print(f"\n[{q['pdf_field']}] {q['title']}\n{q['question']}\n---\n{q['title_fr']}\n{q['question_fr']}")
    with open("owner_questions.json", "w") as f:
        json.dump({"translation_model": TRANSLATE_MODEL, "questions": out}, f, indent=2, ensure_ascii=False)
    print("\nWrote owner_questions.json")


if __name__ == "__main__":
    main()
