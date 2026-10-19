"""The fictional Field Visit Risk Assessment.

Structure follows a real federal risk-assessment form; every name, weight,
score and threshold here is invented.
"""

WEIGHTS = {"Low": 1, "Medium": 3, "High": 5, "Critical": 10}

# Option score -> uncertainty score. Confirmed answers are the least uncertain,
# "Possible" (and an untested mitigation in place) the most.
UNCERTAINTY = {0: 1, 1: 2, 3: 3, 6: 2, 10: 1}

RISK_OPTIONS = [
    ("None known", "Aucun connu", 1),
    ("Possible", "Possible", 3),
    ("Likely", "Probable", 6),
    ("Confirmed", "Confirmé", 10),
]

MITIGATION_OPTIONS = [
    ("In place and tested", "En place et testé", 0),
    ("In place", "En place", 3),
    ("Informal", "Informel", 6),
    ("None", "Aucun", 10),
]

FACTORS = [
    # id, category, English, French, weight category, options
    ("L1", "Likelihood", "Prior hostile contact at site", "Contact hostile antérieur sur le site", "Critical", RISK_OPTIONS),
    ("L2", "Likelihood", "Remote or hard-to-reach site", "Site éloigné ou difficile d'accès", "Medium", RISK_OPTIONS),
    ("L3", "Likelihood", "Working alone", "Travail seul", "High", RISK_OPTIONS),
    ("C1", "Consequence", "Hazardous materials on site", "Matières dangereuses sur le site", "Critical", RISK_OPTIONS),
    ("C2", "Consequence", "Distance to medical help", "Distance des soins médicaux", "Medium", RISK_OPTIONS),
    ("C3", "Consequence", "Severe weather", "Conditions météo extrêmes", "Low", RISK_OPTIONS),
    ("M1", "Mitigation", "Check-in plan", "Plan de communication", "High", MITIGATION_OPTIONS),
    ("M2", "Mitigation", "Second person attending", "Deuxième personne présente", "Medium", MITIGATION_OPTIONS),
    ("M3", "Mitigation", "Satellite communicator", "Communicateur satellite", "Low", MITIGATION_OPTIONS),
]

CATEGORIES = ["Likelihood", "Consequence", "Mitigation"]
CATEGORY_FR = {"Likelihood": "Probabilité", "Consequence": "Conséquence", "Mitigation": "Atténuation"}

# Overall risk bands on the total (product of category subtotals).
BANDS = [(50_000, "Low"), (300_000, "Moderate"), (1_000_000, "High"), (float("inf"), "Extreme")]
BAND_FR = {"Low": "Faible", "Moderate": "Modéré", "High": "Élevé", "Extreme": "Extrême"}

# Uncertainty level on the uncertainty score (sum of row uncertainties).
UNC_LEVELS = [(60, "Low"), (90, "Medium"), (float("inf"), "High")]


def reference(choices):
    """The reconciled rule, as the spreadsheet states it. choices: {factor_id: score}."""
    sub = {c: 0 for c in CATEGORIES}
    unc = 0
    warning = False
    for fid, cat, _, _, wcat, _ in FACTORS:
        w = WEIGHTS[wcat]
        s = choices[fid]
        sub[cat] += s * w
        unc += UNCERTAINTY[s] * w
        if wcat == "Critical" and s == 10:
            warning = True
    sub = {c: max(1, v) for c, v in sub.items()}
    total = sub["Likelihood"] * sub["Consequence"] * sub["Mitigation"]
    band = next(name for limit, name in BANDS if total < limit)
    return {
        "total_risk": total,
        "band": band,
        "uncertainty": unc,
        "unc_level": next(name for limit, name in UNC_LEVELS if unc < limit),
        "warning": warning,
        "approval": warning or band in ("High", "Extreme"),
    }
