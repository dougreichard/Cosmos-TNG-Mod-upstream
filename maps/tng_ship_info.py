"""Backing data for the TNG ship browser map.

Everything here is `tngview_`-prefixed. A mission's .py files exec into the SAME flat
MAST-global namespace as every loaded add-on, so an unprefixed helper here would collide
with - or silently overwrite - a library or add-on function of the same name. `tng_` is
the add-on's prefix and must not be shadowed; a leading underscore marks a real private
that is never exported.

The list is built from the merged ship table rather than from the mod's own tng_ships.json
on purpose: the table is what the game actually resolves a hull against, so a hull that
failed to merge simply is not here, and the browser shows the truth rather than the intent.
"""
from sbs_utils.mast.mast_node import MastDataObject
from sbs_utils.pages.widgets.layout_listbox import LayoutListBoxHeader
from sbs_utils.procedural.gui import gui_row, gui_text
from sbs_utils.procedural.ship_data import filter_ship_data_by_side, get_ship_data_for

# Every hull the mod declares is keyed `tng_<faction>_<class>`, so one substring selects
# the mod's own hulls out of a table that also holds every stock and LM hull.
TNGVIEW_KEY_PREFIX = "tng_"


def _clean(text):
    """Strip the characters that break a MAST assignment or a text area.

    Two different hazards, both silent:
      * `{` - MAST re-runs an assigned STRING through f-string formatting, so a brace in
        returned text is a SyntaxError reported against the CALLER, not against this file.
      * `[` - gui_text_area reads `[...]` as a markdown link reference and REPLACES the
        line with whatever follows it, so a shields value of "[2500, 2500]" would delete
        its own line.
    """
    out = str(text)
    for ch in "{}[]":
        out = out.replace(ch, "")
    return out


def tngview_ships():
    """Every hull the mod declares, as raw table entries."""
    return filter_ship_data_by_side(TNGVIEW_KEY_PREFIX, None) or []


def tngview_ship_rows():
    """Hulls grouped by faction, as listbox items with collapsible group headers.

    Shape follows modding_tools/grid_editor.get_ship_data_listbox_data(): a
    LayoutListBoxHeader per faction followed by one MastDataObject per hull. The listbox
    turns that into a collapsible tree on its own.
    """
    by_side = {}
    for s in tngview_ships():
        by_side.setdefault(s.get("side") or s.get("origin") or "Unknown", []).append(s)
    rows = []
    for side in sorted(by_side):
        rows.append(LayoutListBoxHeader(side, False))
        for s in sorted(by_side[side], key=lambda e: (e.get("name") or "")):
            rows.append(MastDataObject({"key": s.get("key"),
                                        "name": s.get("name") or s.get("key"),
                                        "roles": (s.get("roles") or "").lower()}))
    return rows


def tngview_first_ship(rows):
    """The first real hull in the rows - skipping the faction headers."""
    for r in rows:
        if not isinstance(r, LayoutListBoxHeader):
            return r.key
    return None


def tngview_ship_title():
    gui_row("row-height: 1.4em;")
    gui_text("$text:`HULL`;font:gui-2;color:#8cf;")


def tngview_ship_row(item):
    # The template is called for group headers too, and they carry no .key - rendering
    # them as a normal row raises AttributeError inside the listbox's own draw.
    if isinstance(item, LayoutListBoxHeader):
        gui_row("row-height: 1.6em;")
        mark = "-" if not item.collapse else "+"
        gui_text("$text:`" + mark + " " + _clean(item.label) + "`;color:#fd8;font:gui-2;")
        return
    gui_row("row-height: 1.5em;")
    gui_text("$text:`  " + _clean(item.name) + "`;font:gui-2;")


def tngview_ship_detail(key):
    """Panel text for one hull. Brace-free and bracket-free - see _clean."""
    d = get_ship_data_for(key)
    if d is None:
        return "# Unknown hull\nNo entry named " + _clean(key) + " in the ship table."
    shields = d.get("shields") or []
    fwd = shields[0] if len(shields) > 0 else "-"
    aft = shields[1] if len(shields) > 1 else "-"
    roles = (d.get("roles") or "").replace(",", ", ")
    # long_desc is absent on 8 of the 51 hulls; a missing line reads as a rendering bug,
    # so say plainly that the mod does not describe this one.
    desc = d.get("long_desc") or "No description in the mod's ship data."
    lines = [
        "# " + _clean(d.get("name") or key),
        _clean(d.get("origin") or d.get("side") or "unknown origin"),
        "",
        "- shields " + _clean(fwd) + " fwd / " + _clean(aft) + " aft",
        "- hull " + _clean(d.get("hullpoints") or "-"),
        "- roles " + _clean(roles or "-"),
        "- key " + _clean(key),
        "",
        _clean(desc),
    ]
    return "\n".join(lines)


def tngview_heading():
    ships = tngview_ships()
    sides = sorted({(s.get("side") or s.get("origin") or "Unknown") for s in ships})
    return "TNG hulls: " + str(len(ships)) + " over " + str(len(sides)) + " factions"


def tngview_row_key(item):
    """The hull key for a listbox row, or None for a faction header.

    The type test lives HERE rather than in the .mast because MAST's eval globals are a
    whitelist and `hasattr` is not in it: `hasattr(picked, "key")` raises
    `NameError: name 'hasattr' is not defined` at runtime. Nothing catches that earlier -
    it is only reachable by actually clicking a row, so it survives compile, --test and a
    page that renders perfectly.
    """
    if item is None or isinstance(item, LayoutListBoxHeader):
        return None
    return getattr(item, "key", None)
