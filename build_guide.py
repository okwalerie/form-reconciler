"""Build the synthetic user guide for the Field Visit Risk Assessment form.

The guide is the third source: prose that describes the rule. Like real user
guides it is mostly right, sometimes contradicts itself, and leaves the
arithmetic unstated. Screenshots are rendered from the actual form, with the
results filled in by the form's own scripts.
"""

import json
import os
import subprocess
import tempfile

import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from procedure import FACTORS, WEIGHTS
from reconcile import extract_pdf

FORM = "artifacts/field-visit-risk-assessment.pdf"
GUIDE = "artifacts/field-visit-risk-assessment-user-guide.pdf"
SHOTS = "artifacts/guide-screens"

# The worked example used for every screenshot.
EXAMPLE = {
    "L1": "Possible", "L2": "Likely", "L3": "Confirmed",
    "C1": "None known", "C2": "Likely", "C3": "Possible",
    "M1": "In place", "M2": "None", "M3": "In place and tested",
}

# Per-factor guidance: what each answer means, an example, and notes.
GUIDANCE = {
    "L1": {
        "ask": "Has anyone from the program, or another enforcement or inspection body, had a hostile or "
               "threatening interaction at this site or with the people you expect to meet?",
        "answers": {
            "None known": "You checked the site history and asked the regional office, and found nothing.",
            "Possible": "Second-hand or unverified reports, or hostility at a related site.",
            "Likely": "A recent pattern of non-cooperation or verbal threats, not yet documented as an incident.",
            "Confirmed": "A documented incident at this site in the last five years.",
        },
        "example": "A neighbouring property owner told the last inspector the operator \"doesn't like visitors\". "
                   "Nothing is documented. Answer: Possible.",
        "note": "This factor is weighted Critical. If you answer Confirmed, the form displays the Single "
                "Critical Factor warning and the assessment requires supervisor approval.",
    },
    "L2": {
        "ask": "How hard is the site to reach, and how long would it take help to reach you?",
        "answers": {
            "None known": "Urban or roadside site with cell coverage.",
            "Possible": "Rural site, reachable by paved road, patchy coverage.",
            "Likely": "Gravel or seasonal road, no coverage on site.",
            "Confirmed": "Fly-in, boat access, or a road that is often impassable.",
        },
        "example": "A storage yard 40 minutes down a gravel road with no cell signal. Answer: Likely.",
    },
    "L3": {
        "ask": "Will any officer be working out of sight and sound of another officer?",
        "answers": {
            "None known": "The team will stay together for the whole visit.",
            "Possible": "Short periods apart are possible but not planned.",
            "Likely": "The plan splits the team for part of the visit.",
            "Confirmed": "One officer is attending alone.",
        },
        "example": "One officer is attending. Answer: Confirmed.",
    },
    "C1": {
        "ask": "Could officers be exposed to hazardous materials on site (fuels, pesticides, unknown chemicals, "
               "contaminated soil or water)?",
        "answers": {
            "None known": "The site has no history of storing or handling hazardous materials.",
            "Possible": "Materials might be present, for example an unlabelled container was reported.",
            "Likely": "The operator is known to store regulated substances.",
            "Confirmed": "A release or exposure is the reason for the visit.",
        },
        "example": "The yard stores equipment only. Answer: None known.",
        "note": "Any indication of hazardous materials (Possible, Likely or Confirmed) displays the Single "
                "Critical Factor warning. Contact the regional safety advisor before the visit.",
    },
    "C2": {
        "ask": "How far is the nearest medical help that can treat a serious injury?",
        "answers": {
            "None known": "Under 20 minutes by road.",
            "Possible": "20 to 60 minutes by road.",
            "Likely": "More than an hour by road.",
            "Confirmed": "Air evacuation would be needed.",
        },
        "example": "The nearest hospital is 75 minutes away. Answer: Likely.",
    },
    "C3": {
        "ask": "Could weather make the visit or the trip unsafe?",
        "answers": {
            "None known": "No warnings in the forecast.",
            "Possible": "Seasonal risk (ice, heat, storms) but no current warning.",
            "Likely": "A weather statement is in effect for the area.",
            "Confirmed": "A warning is in effect for the day of the visit.",
        },
        "example": "Early spring, no warnings yet, but roads can ice over. Answer: Possible.",
    },
    "M1": {
        "ask": "Is there a check-in plan with a named contact and set check-in times?",
        "answers": {
            "In place and tested": "Named contact, set times, and the plan was tested on a previous visit.",
            "In place": "Named contact and set times, not yet tested.",
            "Informal": "Someone knows where you are going, but there are no set times.",
            "None": "No check-in plan.",
        },
        "example": "The team lead will expect a call at 11:00 and 14:00. Answer: In place.",
    },
    "M2": {
        "ask": "Will a second person (officer, police, or trained staff) attend the visit?",
        "answers": {
            "In place and tested": "A second officer is attending and has worked this site before.",
            "In place": "A second person is attending.",
            "Informal": "A second person is nearby and can come if called.",
            "None": "No second person.",
        },
        "example": "No second officer is available. Answer: None.",
    },
    "M3": {
        "ask": "Will you carry a satellite communicator or another device that works without cell coverage?",
        "answers": {
            "In place and tested": "Device issued, charged, and tested this week.",
            "In place": "Device issued but not tested recently.",
            "Informal": "A device is available at the office but not booked.",
            "None": "No device.",
        },
        "example": "The officer has a tested satellite communicator. Answer: In place and tested.",
    },
}


def run_form(answers):
    """Fill the form's results using its own scripts (same runner as reconcile.py)."""
    form = extract_pdf(FORM)
    values = {}
    for fid, label in answers.items():
        export = next(e for e, d in form["fields"][f"opt_{fid}"]["options"] if d.startswith(label + " /"))
        values[f"opt_{fid}"] = export
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f_form, \
         tempfile.NamedTemporaryFile("w", suffix=".json") as f_in:
        json.dump(form, f_form)
        json.dump([values], f_in)
        f_form.flush()
        f_in.flush()
        out = subprocess.run(["node", "run_pdf.js", f_form.name, f_in.name],
                             capture_output=True, text=True, check=True)
    return json.loads(out.stdout)[0]


def render_screens(answers):
    """Render each section of the filled-in form as a PNG."""
    os.makedirs(SHOTS, exist_ok=True)
    results = run_form(answers)
    doc = pymupdf.open(FORM)
    page = doc[0]
    labels = {f"opt_{fid}": next(f"{en} / {fr}" for en, fr, _ in opts if en == answers[fid])
              for fid, *_r, opts in FACTORS}
    for w in page.widgets():
        name = w.field_name
        if name in labels:
            w.field_value = labels[name]
            w.update()
        elif name in ("band", "unc_level", "warning", "approval"):
            w.field_value = str(results[name])
            w.update()
    # Section bands, from the form's layout.
    tops = {}
    for block in page.get_text("blocks"):
        text = block[4]
        for key in ("Likelihood / Probabilité", "Consequence / Conséquence", "Mitigation / Atténuation",
                    "Overall risk / Risque global"):
            if text.startswith(key):
                tops[key] = block[1]
    order = list(tops)
    shots = {}
    for i, key in enumerate(order):
        y0 = tops[key] - 6
        y1 = tops[order[i + 1]] - 8 if i + 1 < len(order) else y0 + 100
        path = f"{SHOTS}/{key.split(' / ')[0].lower().replace(' ', '-')}.png"
        page.get_pixmap(dpi=150, clip=pymupdf.Rect(48, y0, 566, y1)).save(path)
        shots[key.split(" / ")[0]] = path
    return shots, results


def build_guide():
    shots, results = render_screens(EXAMPLE)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
                        spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=10,
                        spaceBefore=8, spaceAfter=2)
    note = ParagraphStyle("note", parent=body, backColor=colors.HexColor("#FFF6D6"),
                          borderColor=colors.HexColor("#E0C060"), borderWidth=0.5, borderPadding=5,
                          spaceBefore=4, spaceAfter=6)

    def shot(key, width=6.6 * inch):
        iw, ih = ImageReader(shots[key]).getSize()
        return Image(shots[key], width=width, height=width * ih / iw)

    s = []
    s.append(Paragraph("Field Visit Risk Assessment (Form FVRA-04)", h1))
    s.append(Paragraph("User guide for officers and supervisors, version 2.0 (2018)", body))
    s.append(Paragraph("<i>Synthetic document for demonstration. Fictional program; not a real government "
                       "guide. Version française disponible sur demande.</i>", small))
    s.append(Spacer(1, 10))

    s.append(Paragraph("1. Before you start", h2))
    s.append(Paragraph(
        "Complete a Field Visit Risk Assessment before every planned field visit, and update it if the plan "
        "changes. The lead officer completes the form. Answer every factor; if you are unsure, choose the "
        "answer that best matches what you know today and explain in your visit plan.", body))
    s.append(Paragraph(
        "The form has three sections. <b>Likelihood</b> factors describe how likely something is to go wrong. "
        "<b>Consequence</b> factors describe how bad it would be. <b>Mitigation</b> factors describe what you "
        "have in place to reduce the risk. Each factor has a weight, shown next to it on the form.", body))
    weights = [["Factor", "Section", "Weight"]] + [
        [en, cat, f"{wcat} ({WEIGHTS[wcat]})"] for _fid, cat, en, _fr, wcat, _o in FACTORS]
    t = Table(weights, colWidths=[3.2 * inch, 1.4 * inch, 1.2 * inch])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Table 1. Factor weights", small))
    s.append(t)
    s.append(Paragraph(
        "The screenshots in this guide follow one worked example: a lone officer inspecting a rural storage "
        "yard down a gravel road in early spring.", body))

    for section, key in [("2. Likelihood factors", "Likelihood"), ("3. Consequence factors", "Consequence"),
                         ("4. Mitigation factors", "Mitigation")]:
        s.append(PageBreak())
        s.append(Paragraph(section, h2))
        s.append(shot(key))
        s.append(Paragraph(f"Figure: the {key} section, completed for the worked example.", small))
        for fid, cat, en, _fr, wcat, _opts in FACTORS:
            if cat != key:
                continue
            g = GUIDANCE[fid]
            block = [Paragraph(f"{en} ({wcat})", h3), Paragraph(g["ask"], body)]
            rows = [[Paragraph(f"<b>{a}</b>", small), Paragraph(d, small)] for a, d in g["answers"].items()]
            at = Table(rows, colWidths=[1.4 * inch, 5.1 * inch])
            at.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                    ("TOPPADDING", (0, 0), (-1, -1), 1)]))
            block.append(at)
            block.append(Paragraph(f"<i>Example:</i> {g['example']}", body))
            if "note" in g:
                block.append(Paragraph(f"<b>Note.</b> {g['note']}", note))
            s.append(KeepTogether(block))

    s.append(PageBreak())
    s.append(Paragraph("5. Reading the results", h2))
    s.append(shot("Overall risk"))
    s.append(Paragraph("Figure: results for the worked example.", small))
    s.append(Paragraph("Overall risk", h3))
    s.append(Paragraph(
        "The form calculates the overall risk from your answers in the three sections. Higher likelihood "
        "and consequence raise the overall risk; stronger mitigation lowers it. The result is shown as Low, "
        "Moderate, High or Extreme.", body))
    s.append(Paragraph("Uncertainty level", h3))
    s.append(Paragraph(
        "The uncertainty level shows how much of your assessment rests on unconfirmed information. "
        "Confirmed answers carry the least uncertainty; Possible answers carry the most. The result is shown "
        "as Low, Medium or High. If uncertainty is High, gather more information before the visit if you can.",
        body))
    s.append(Paragraph("Single critical factor", h3))
    s.append(Paragraph(
        "This field displays a warning if you select the highest answer for any factor whose weight is "
        "Critical. A warning means the assessment must go to your supervisor, whatever the overall risk.",
        body))
    s.append(Paragraph("Supervisor approval", h3))
    s.append(Paragraph(
        "Supervisor approval is required when the Single Critical Factor warning is displayed, or when the "
        "overall risk is High or Extreme. Send the completed form to your supervisor and do not start the "
        "visit until it is approved.", body))

    doc = SimpleDocTemplate(GUIDE, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title="Field Visit Risk Assessment user guide (synthetic)")
    doc.build(s)
    return results


if __name__ == "__main__":
    r = build_guide()
    print("built", GUIDE)
    print("worked example, as the form computes it:",
          {k: r[k] for k in ("band", "unc_level", "warning", "approval")})
