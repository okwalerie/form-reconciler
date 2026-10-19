"""Mapping for the Field Visit Risk Assessment: which PDF field means which spreadsheet cell.

Written by reading both artifacts (`uv run python inspect_sources.py ...`). This is
the one step that needs judgment about meaning; everything downstream is mechanical.
A new form gets its own file in this folder, in the same shape.
"""

PDF = "artifacts/field-visit-risk-assessment.pdf"
XLSX = "artifacts/risk-factor-values.xlsx"
SHEET = "Assessment"

# Answers: PDF choice field -> spreadsheet input cell. The same answer is given to both.
INPUTS = {
    "opt_L1": "E4", "opt_L2": "E5", "opt_L3": "E6",
    "opt_C1": "E7", "opt_C2": "E8", "opt_C3": "E9",
    "opt_M1": "E10", "opt_M2": "E11", "opt_M3": "E12",
}

# Readable names for the answers, as the form labels them.
NAMES = {
    "opt_L1": "Prior hostile contact at site",
    "opt_L2": "Remote or hard-to-reach site",
    "opt_L3": "Working alone",
    "opt_C1": "Hazardous materials on site",
    "opt_C2": "Distance to medical help",
    "opt_C3": "Severe weather",
    "opt_M1": "Check-in plan",
    "opt_M2": "Second person attending",
    "opt_M3": "Satellite communicator",
}

# Calculated values: PDF field -> spreadsheet cell holding the same quantity.
CELLS = {
    "risk_L1": "I4", "unc_L1": "J4", "risk_L2": "I5", "unc_L2": "J5", "risk_L3": "I6", "unc_L3": "J6",
    "risk_C1": "I7", "unc_C1": "J7", "risk_C2": "I8", "unc_C2": "J8", "risk_C3": "I9", "unc_C3": "J9",
    "risk_M1": "I10", "unc_M1": "J10", "risk_M2": "I11", "unc_M2": "J11", "risk_M3": "I12", "unc_M3": "J12",
    "sub_L": "I14",
    "zz_L": "I14",  # hidden margin helper; holds the likelihood subtotal the total actually reads
    "sub_C": "I15",
    "sub_M": "I16",
    "total_risk": "I18",
    "band": "I19",
    "unc_total": "I20",
    "unc_level": "I21",
    "warning": "I22",
    "approval": "I23",
}

# What the form shows the officer; the scores behind them are hidden fields.
OUTPUTS = ["band", "unc_level", "warning", "approval"]
OUTPUT_LABELS = {
    "band": "Overall risk",
    "unc_level": "Uncertainty level",
    "warning": "Critical-factor warning",
    "approval": "Supervisor approval required",
}
