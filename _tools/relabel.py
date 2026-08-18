"""Per-cell species corrections for the Gemini race sheets.

A sheet is named for what was ASKED for, not for what came back, and the two differ.
The `kaonz` sheet is the clear case: it was requested as Kazon and is a Klingon sheet
with exactly ONE Kazon in it (source index 3, the matted mane) - so labelling by
filename would have `random_face("Kazon")` hand back a Klingon 63 times out of 64,
and would bury 63 good Klingons under the wrong species.

Corrections live here rather than in the cutter so the cut stays purely mechanical
and every judgement about WHAT a face is stays in one reviewable place. Keys are
source sheet stems; values map a source index (or a range) to the real species, with
`default` for everything not called out.
"""

SHEETS = {
    # Asked for Kazon; came back Klingon except one. Confirmed by eye.
    "kaonz": {"default": "klingon", 3: "kazon"},
    # Two species deliberately on one sheet, Vorta first then Gorn.
    "vorta_gorn": {"default": "gorn", "range": [(0, 39, "vorta")]},
}

# Sheets whose filename is simply misspelt - no species judgement involved.
SPELLING = {
    "andorian": "andorian", "q": "q", "bajoran": "bajoran", "betazoid": "betazoid",
    "borg": "borg", "cardasian": "cardassian", "dominian": "dominion",
    "horta": "horta", "human": "human", "jemhadar": "jemhadar",
    "kligon": "klingon", "orian": "orion", "romulan": "romulan", "trill": "trill",
    "ferengi": "ferengi", "vulcan": "vulcan",
    # Singular, to match the race name the shipped index already uses.
    "androids": "android",
    # Sheet filename is misspelt; the race name matches the shipped index.
    "changling": "changeling",
}


def species_for(stem, index):
    """The real species of one cut cell, or None to drop it."""
    rule = SHEETS.get(stem)
    if rule is None:
        return SPELLING[stem]
    for lo, hi, name in rule.get("range", []):
        if lo <= index < hi:
            return name
    return rule.get(index, rule.get("default"))
