"""Which PDF field corresponds to which spreadsheet cell.

Written by hand after reading both artifacts. This is the one step that needs
judgment about meaning; everything downstream is mechanical.
"""

from procedure import FACTORS

FIRST_ROW = 4  # first factor row on the Assessment sheet

INPUTS = {}   # PDF choice field -> spreadsheet input cell
CELLS = {}    # PDF calculated field -> spreadsheet formula cell

for i, (fid, *_rest) in enumerate(FACTORS):
    r = FIRST_ROW + i
    INPUTS[f"opt_{fid}"] = f"E{r}"
    CELLS[f"risk_{fid}"] = f"I{r}"
    CELLS[f"unc_{fid}"] = f"J{r}"

CELLS.update({
    "sub_L": "I14",
    "zz_L": "I14",  # hidden margin helper; holds the likelihood subtotal
    "sub_C": "I15",
    "sub_M": "I16",
    "total_risk": "I18",
    "band": "I19",
    "unc_total": "I20",
    "unc_level": "I21",
    "warning": "I22",
    "approval": "I23",
})

# What the form shows; the scores themselves are hidden fields.
OUTPUTS = ["band", "unc_level", "warning", "approval"]
OUTPUT_LABELS = {
    "band": "Overall risk",
    "unc_level": "Uncertainty level",
    "warning": "Critical-factor warning",
    "approval": "Supervisor approval required",
}
