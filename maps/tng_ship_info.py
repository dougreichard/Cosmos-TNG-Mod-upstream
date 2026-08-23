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
from sbs_utils.procedural.ship_data import (filter_ship_data_by_side, get_ship_data_for,
                                            get_ship_index)

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


# ---------------------------------------------------------------------------
# Bake walk
# ---------------------------------------------------------------------------
#
# A hull's `.paxmesh` is derived art the engine bakes the FIRST TIME something draws the
# hull. Until then the client loads the raw `.obj` and bakes it mid-session - and a client
# that dies during a session dies in front of guests.
#
# The bake is worth forcing ahead of time for its own sake, and it is also the A/B for a
# crash we are chasing: `elementCount is zero for DX11PaxGraphicsClass::CreateIndexList`,
# an assert whose only callers are the engine's two mesh loaders, so it fires at LOAD time.
# Bake everything up front and either the crash stops - which names the bake path - or it
# does not, which clears it.
#
# This only does anything in the REAL engine. The browser mock draws gui_ship without ever
# writing a .paxmesh, so a walk under cosmos_dev proves nothing. Check the result on disk
# with _tools/check_art.py.


def tngview_bake_keys(scope=None):
    """One ship key per distinct artfileroot, in a stable order.

    De-duplicated by artfileroot because baking is per ART FILE, not per ship key: the mod
    reskins stock keys onto its own hulls, so `tng_crd_damar` and `arvonian_carrier` are one
    mesh and drawing both bakes nothing twice but costs twice the wall clock.

    scope "all" walks every key in the merged ship table - stock and LM art included, which
    is what the party missions actually spawn. Anything else walks the mod's own hulls only.
    """
    if scope == "all":
        entries = list(get_ship_index().values())
    else:
        entries = tngview_ships()
    seen = set()
    keys = []
    for entry in sorted(entries, key=lambda e: (e.get("artfileroot") or "")):
        root = entry.get("artfileroot")
        key = entry.get("key")
        if not root or not key or root in seen:
            continue
        seen.add(root)
        keys.append(key)
    return keys


def tngview_bake_at(keys, index):
    """The key at `index`, or None once the walk has run off the end.

    The bounds test lives here so the .mast never indexes a list: an IndexError inside a
    MAST expression stops the command that contains it, so the walker would end silently
    partway through and look like it had simply finished.
    """
    if not keys or index is None or index < 0 or index >= len(keys):
        return None
    return keys[index]


def tngview_status(keys, index, ship):
    """Header text: bake progress while walking, the normal heading otherwise.

    Kept free of `:` and `;` because the caller embeds it in a style string, and free of
    braces because MAST re-runs an assigned string through f-string formatting.
    """
    if not keys:
        return tngview_heading()
    done = index + 1 if index is not None else 1
    if done > len(keys):
        done = len(keys)
    return ("baking " + str(done) + " of " + str(len(keys)) + " - "
            + _clean(ship or "").replace(":", " ").replace(";", " "))


def tngview_status_style(keys, index, ship):
    """The header's full style string.

    Text.update() replaces the WHOLE style, not just the text in it, so the color and font
    have to travel with every update or the header goes plain the moment a walk starts.
    Building it here keeps the build and the update reading from one place.
    """
    return "color:#8cf;font:gui-3;$text:" + tngview_status(keys, index, ship) + ";"


def tngview_bake_show(ship_widget, status_widget, keys, index, key):
    """Swap the model and the header IN PLACE - deliberately without a page rebuild.

    Rebuilding is the obvious way to do this and it is the wrong one: a repaint ends the
    tasks hosted on the GUI task, and the walker asks for a change once a second, so a
    rebuilding walker kills itself on its own first step. MEASURED - it baked exactly one
    hull and stopped, as a sub-task and as an independent task alike.

    Updating the two widgets directly leaves the page alone, so nothing ends the walker,
    and it is cheaper than a rebuild besides.

    The widgets arrive as arguments rather than being looked up because the page reassigns
    them on every repaint; the walker reads the shared refs fresh each step, so an operator
    clicking a row mid-walk cannot leave it writing to a dead widget.

    Returns True when a hull was really shown, False when the page is not built yet.
    """
    if ship_widget is None:
        # The page has not built yet - `bake=` starts the walk at map entry, ahead of the
        # first repaint. Report nothing shown so the caller waits rather than burning a hull.
        return False
    text = tngview_status(keys, index, key)
    # print, not log - log() is Python logging with no handler under the engine, so it is
    # invisible. The operator is watching this run; give them progress they can read.
    print(text)
    ship_widget.update(key)
    if status_widget is not None:
        status_widget.update(tngview_status_style(keys, index, key))
    return True
