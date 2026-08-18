# Asking Gemini for more cells that MATCH

Style drift happens when a thread loses sight of its own earlier output. Describing
the style again in words does not fix it; showing it the target does.

## Every request

1. **Attach `gemini_style_reference.png`.** Nine finished cells covering skin, ridges,
   scales and prosthetics, so the reference shows how the style handles the hard cases
   rather than one easy face.
2. Ask for the same treatment, explicitly as a match:

> Using the attached image as the exact style reference, create a 3x3 grid of Star
> Trek: The Animated Series style character portraits in the identical style, line
> weight, flat colour and framing. Each portrait is a head-and-shoulders bust,
> centred, on its own flat solid colour square background, arranged as a 3x3 grid on
> a starfield. Match the attached reference exactly.

3. Then list the nine subjects, one per line.

## What makes a grid easy to cut

* **3x3 is the sweet spot.** On a 1408-wide image that gives ~210px panels, a 2.4x
  upscale to a 512 cell - measured clean on flat cel art. The 7-wide "expanded cast"
  sheets drop to ~110px, which is a 4.6x upscale and past the point where it holds.
* Panels on their own flat squares, separated or touching, either is fine -
  `cut_grid.py` detects both.
* The starship artwork overlapping a panel is fine; lattice completion recovers it.

## Subjects still wanted

Run `python cut_grid.py --help` for the cutting step. The gaps, in priority order:

* **human** - have 64, want ~120  (56 more)
* **romulan** - have 2, want ~24  (22 more)
* **kazon** - have 0, want ~20  (20 more)
* **klingon** - have 8, want ~26  (18 more)
* **jemhadar** - have 0, want ~18  (18 more)
* **cardassian** - have 9, want ~26  (17 more)
* **orion** - have 0, want ~14  (14 more)
* **breen** - have 0, want ~12  (12 more)
* **vorta** - have 1, want ~8  (7 more)
* **bajoran** - have 5, want ~12  (7 more)
* **ferengi** - have 5, want ~10  (5 more)

## Regenerating the 64-character generic sheet

`new/builder/sheet.jfif` has 64 good generic characters in the right style, but at
1024px across an 8x8 grid each panel is only **128px** - a 4.0x upscale to a 512 cell.
Measured on this art, 2.4x is clean and 4x is not; the whole point of this rebuild was
undoing a 2.67x upscale in the original sheets, so it should not ship at 4x.

Ask for the same characters as **eight 3x3 grids at 1408px** instead. That gives ~210px
panels and a 2.4x upscale, which measured clean. Attach `gemini_style_reference.png`
each time so the style does not drift between grids.

Then:

    python cut_grid.py out/refs_user/<grid>.png --preview -o out/grids/<n>
    # check the preview, then re-run with --keys to name them
    python facesheets.py --cells out/cells_named -o out/sheets

`cut_grid.py` handles both layouts it will produce - panels separated on a starfield
(contour detector) and panels touching in a tight mosaic (lattice detector) - and
recovers any panel the starship artwork overlaps.


## MEASURED GAPS (regenerate this section after adding grids)

The set is 127 cells and it is **73% Federation**. Two factions that ship hulls AND a
fleet ladder have NO face at all, so `random_face("Kazon")` returns a stock Terran -
visibly wrong beside TAS art.

Priority 1 - factions with ships and no faces:

| faction | faces | ask for |
|---|---|---|
| Kazon | 0 | 2 grids (18): warriors, a maj, crew - big ridged foreheads, matted manes |
| Orion | 0 | 1 grid (9): green skin, pirates and a syndicate boss |
| Dominion | 1 | 2 grids (18): jem'hadar soldiers (grey, horned), vorta, breen helmets |
| Romulan | 2 | 2 grids (18): commanders, subcommanders, senators |
| Klingon | 8 | 1 grid (9): more warriors, a chancellor, a woman |
| Cardassian | 9 | 1 grid (9): gul, glinn, an obsidian order type |

Priority 2 - roles. Present counts: {'ops': 73, 'medical': 7, 'command': 34, 'science': 6, 'civilian': 7}.
Medical, science and civilian are ~7 each across ALL species, so a doctor or a
shopkeeper has almost no options. Ask for a grid of each, mixed species, in the
right division colour (teal for medical/science after TOS).

Priority 3 - eras. Present counts: {'race': 44, 'ds9': 15, 'tng': 46, 'voy': 11, 'tos': 11}.
TOS and Voyager are the thin ones; a grid each.

Priority 4 - the OVERLAY bank (14 cells, none drawn). Borg implants, a VISOR, a scar,
an eyepatch, a breather - drawn on a TRANSPARENT field, one per panel, in the same
line weight. These are what make `tng_face_assimilate()` usable: an overlay stacks
onto ANY face, so a character already on screen can be assimilated at runtime.


## AFTER THE 16 RACE SHEETS (2026-08-17)

Cut with `cut_regular.py`, upscaled 4x through ComfyUI (RealESRGAN_x4plus_anime_6B)
by `upscale_sheets.py`, QC'd by `qc_cells.py`, species corrected in `relabel.py`.
**878 cells at 512px over 17 species.** Every faction that had ships and no faces is
now covered EXCEPT one:

| faction | before | after | |
|---|---|---|---|
| Orion | 0 | 63 | filled |
| Dominion (vorta+jemhadar) | 1 | 138 | filled |
| Romulan | 2 | 63 | filled |
| Klingon | 8 | 126 | filled |
| Cardassian | 9 | 63 | filled |
| **Kazon** | **0** | **1** | **STILL THE GAP** |

**The Kazon sheet was not a Kazon sheet.** It was requested as Kazon and came back as
64 Klingons with a single Kazon at index 3 (confirmed by eye) - so the one faction
that most needed faces is the one still without them, and the request produced a
Klingon sheet nobody asked for. Worth knowing when asking again: name the features,
not the species. Kazon read as a lumpy sloped forehead and a huge matted mane, quite
unlike a Klingon's ridged crest and braided hair - ask for THAT and do not rely on
the name alone.

Still absent entirely (the mod has no art for these at all): ferengi, vulcan,
hologram, android, changeling, talaxian, ocampa, benzite, tellarite, elaurian,
species8472 - all of which the CURRENT shipping set does cover, so the new sheets
supplement rather than replace it.
