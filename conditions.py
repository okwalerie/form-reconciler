"""Describe a set of inputs as readable conditions on the form's answers.

Given every possible input and which of them diverge, say *when* they diverge,
e.g. "Hazardous materials is Possible or Likely, and Prior hostile contact is
not Confirmed". The input space is finite and fully enumerated, so these
statements are checked against every input, not estimated.
"""

from itertools import product

import numpy as np
from sklearn.tree import DecisionTreeClassifier


def describe_box(box, names, domains):
    """{factor: allowed values} -> 'A is x or y, and B is not z'."""
    parts = []
    for f, allowed in box.items():
        dom = domains[f]
        if set(allowed) == set(dom):
            continue
        excluded = [v for v in dom if v not in allowed]
        if len(excluded) < len(allowed):
            parts.append(f"{names[f]} is not {' or '.join(excluded)}")
        else:
            parts.append(f"{names[f]} is {' or '.join(allowed)}")
    return " and ".join(parts) if parts else "always"


def as_box(rows, mask, factors, domains):
    """If the diverging inputs are exactly every combination of some per-factor
    value sets, return those sets; otherwise None."""
    hit = rows[mask]
    if len(hit) == 0:
        return None
    box = {f: [v for v in domains[f] if v in set(hit[:, i])] for i, f in enumerate(factors)}
    size = np.prod([len(v) for v in box.values()])
    return box if size == len(hit) else None


def relevant_factors(rows, mask, factors, domains):
    """Factors that can flip divergence on their own, holding the rest fixed."""
    index = {tuple(r): m for r, m in zip(map(tuple, rows), mask)}
    relevant = []
    for i, f in enumerate(factors):
        for r, m in index.items():
            if any(index.get(r[:i] + (v,) + r[i + 1:], m) != m for v in domains[f] if v != r[i]):
                relevant.append(f)
                break
    return relevant


def tree_rules(rows, mask, factors, domains, max_depth=4):
    """A short decision tree over the relevant factors, as rules with their
    precision and coverage over all inputs."""
    codes = {f: {v: k for k, v in enumerate(domains[f])} for f in factors}
    X = np.array([[codes[f][v] for f, v in zip(factors, r)] for r in rows])
    clf = DecisionTreeClassifier(max_depth=max_depth, random_state=0).fit(X, mask)
    t = clf.tree_
    rules = []

    def walk(node, box):
        if t.children_left[node] == -1:
            in_box = np.all([np.isin(X[:, i], [codes[f][v] for v in box[f]]) for i, f in enumerate(factors)], axis=0)
            hits = mask[in_box].sum()
            if hits and hits / in_box.sum() > 0.5:
                rules.append({"box": {f: list(v) for f, v in box.items()},
                              "precision": float(hits / in_box.sum()),
                              "coverage": float(hits / mask.sum())})
            return
        i = t.feature[node]
        f = factors[i]
        thr = t.threshold[node]
        left = [v for v in box[f] if codes[f][v] <= thr]
        right = [v for v in box[f] if codes[f][v] > thr]
        walk(t.children_left[node], {**box, f: left})
        walk(t.children_right[node], {**box, f: right})

    walk(0, {f: list(domains[f]) for f in factors})
    rules.sort(key=lambda r: -r["coverage"])
    exact = bool((clf.predict(X) == mask).all())
    return rules, exact


def explain(rows, mask, factors, names, domains):
    """Readable conditions for the inputs where `mask` is true."""
    mask = np.asarray(mask, dtype=bool)
    if mask.all():
        return {"exact": True, "text": "on every input", "rules": []}
    box = as_box(rows, mask, factors, domains)
    if box:
        return {"exact": True, "text": describe_box(box, names, domains), "rules": [{"box": box}]}
    relevant = relevant_factors(rows, mask, factors, domains)
    rules, exact = tree_rules(rows, mask, factors, domains)
    return {
        "exact": exact,
        "depends_on": [names[f] for f in relevant],
        "text": " OR ".join(f"({describe_box(r['box'], names, domains)})" for r in rules[:3]),
        "rules": [{**r, "text": describe_box(r["box"], names, domains)} for r in rules],
    }


def all_inputs(domains, factors):
    return np.array(list(product(*[domains[f] for f in factors])), dtype=object)
