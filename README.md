# Cosmos-TNG-Mod

52 Star Trek hulls across eight factions (the original 51 plus a Borg Cube), restructured from this repo's v0.2.3 release
(`Cosmos-TNG-Mod_v0-2-3.zip`, Cosmos 1.2.0, October 2025 - "the zip" below) so they
**declare** themselves to the game instead of overwriting its files.

Nothing in the Cosmos `data/` folder is touched, and nothing is written into a mission
folder either.

## Origin and credits

- **The original TNG mod is ScornMandark's**: the ship classes and their art, the
  audio, the fonts, the Starfleet avatars and the original balance (which built on the
  earlier TNG, TMP and ItB mods). Everything here started from that release.
- **Trek taunts** by Mike Substelny, carried over unchanged in content.
- **Faces**: the original 127 (sheets `tng1`/`tng2`, never repacked, so existing face
  strings still point at the same people), plus 441 more across 28 species that were
  AI-generated, upscaled and hand-checked per cell (`new/races/` holds the sources,
  `_tools/` the pipeline).
- The six skyboxes are generated rather than painted (`_tools/`).

## Installing

One command, run from the Cosmos `data/missions` folder (where `sbs.pyz` lives):

```
python sbs.pyz fetch Cosmos-TNG-Mod -u ScornMandark
```

That downloads the viewer mission into `data/missions/Cosmos-TNG-Mod/`, then the mod's
built mastlib and media pack its `story.json` pins (this repo's release of that version) into
`data/missions/__lib__/`,
and unpacks the art there once. Nothing in the Cosmos install is overwritten - no
`preferences.json`, `gridData.json` or `shipData.yaml` - so there is no backup step and
nothing to restore. (This replaces the old "unzip into the Cosmos folder" install.)

The viewer shows up in the mission list as **TNG Mod Viewer (dev)**: every face and hull,
with stats and the 3D model.

### Using the mod in a mission

Add the two lines shown under [Layout](#layout-who-reads-it-decides-where-it-lives) to the
mission's `story.json`, and set `EXTRA_SHIP_DATA: true` in its `settings.yaml` (or a
profile). With those pins in place, `sbs fetch` of **that** mission downloads the mod
too - a player never installs it separately.

### Working on the mod itself

`sbs fetch` leaves out the source folders (`tng_races/`, `media/`, `_tools/`, `new/` are
`export-ignore` - a fetched copy loads the released build). To edit the mod, clone it
instead, then build it locally under the same owner name the pins use:

```
git clone https://github.com/ScornMandark/Cosmos-TNG-Mod.git    # into data/missions/
python sbs.pyz lib Cosmos-TNG-Mod -u ScornMandark
```

The `-u ScornMandark` matters: without it `sbs lib` names the build
`artemis-sbs.Cosmos-TNG-Mod.*`, which nothing pins. (`python sbs.pyz fetch Cosmos-TNG-Mod
-u ScornMandark --source` does the clone and build in one step.)

### Releasing

1. Bump `"version"` in `__lib__.json`, and the same string in `story.json`,
   `tng_races/tng_manifest.json` and the `artfileroot` prefix in `media/tng_ships.json`,
   `media/tng_reskin.json` and `media/ship_portraits/tng.json` (a search-and-replace of
   `media.v0.3.0` does the last three).
2. Commit, then push a tag with exactly that version: `git tag v0.3.1 && git push origin v0.3.1`.

`.github/workflows/main.yml` builds the assets and attaches them to the release; it fails
straight away if the tag does not match `__lib__.json`.

## The mod is ADDITIVE, not a re-skin

The zip is a re-skin: it repoints 50 keys the game already owns, so installing it turns
every light cruiser in every mission into a Saber. That approach does work - measured on
engine 1.3.5 with a small probe mission, an add-on entry **beats** the engine's own
`shipData.yaml` for the same key, with `speed_coeff` coming back `0.2199999988079071`
(float32 of the declared `0.22`), so it round-tripped the engine's own C++ table.

It is still the wrong shape for a mod. A re-skin is a conversion: two Trek mods can never
coexist, and nothing can spawn a Saber *and* a Light Cruiser. So every hull here gets its
own key, `tng_<faction>_<class>`, and `tsn_light_cruiser` is left exactly as the game
shipped it. The original README wanted this too - it calls the re-skin a stopgap
"due to the way Cosmos mission scripts are created… I'll eventually create a TNG mission
suite that breaks away from this."

The era prefix is deliberate: the roadmap has TOS and TMP versions next, and every Trek era
has a Federation cruiser.

## Layout: who reads it decides where it lives

The useful split is not "art vs code". It is **what the ENGINE opens** (needs real files on
a real disk) versus **what MAST reads** (perfectly happy inside a zip).

```
Cosmos-TNG-Mod/
  __lib__.json          {"version":"v0.3.0","mastlib":["tng_races"],"zip":["media"]}
  media/                -> ScornMandark.Cosmos-TNG-Mod.media.v0.3.0.zip
    tng_ships.json         52 hulls: the ENGINE opens this one itself.
                           JSON, and the ONLY ship file - the engine searches for
                           .yaml FIRST, so a .yaml sitting beside it is opened
                           instead and silently rejected whole (the add-on still
                           merges library-side, so nothing else notices).
    ships/  audio/  fonts/  faces/
  tng_races/            -> ScornMandark.Cosmos-TNG-Mod.tng_races.v0.3.0.mastlib  (FLAT)
    __init__.mast  tng_setup.py  tng_manifest.json
    tng_sides.amd          seven factions + diplomacy
    tng_taunts.json        Trek taunts, keyed by faction
    tng_<key>.grid   x50   one floor plan per hull
    tng_<faction>_fleets.yaml  x6
  .gitignore            keeps derived art (*.paxmesh etc.) out of source control
  _build_from_zip.py    regenerates all of it from the zip, reporting every repair
```

`sbs.pyz lib Cosmos-TNG-Mod -u ScornMandark` (or the release workflow) builds both and unpacks the media pack **once** into
`__lib__/media/<pack>/`, where every mission reads the same copy.

A mission takes the mod with two lines:

```json
"mastlib": [ ..., "ScornMandark.Cosmos-TNG-Mod.tng_races.v0.3.0.mastlib" ],
"shared_media": [ "ScornMandark.Cosmos-TNG-Mod.media.v0.3.0.zip" ]
```

Both are needed: the mastlib is the logic, and the pack is where the engine-read ship data
and the art live. Unlike the re-skin version, **load order no longer matters** - unique keys
collide with nothing, so there is no race against LM's `races` add-on to lose.

### No generated file, because the engine has an API for this

`sbs.add_extra_ship_data(name, path)` (engine 1.3.5) points the engine straight at the mod's
own ship file - a probe mission confirmed the engine loads a ship from a mod folder with
nothing written into the mission.

That matters for more than tidiness. The other route, `ship_data_merge_mod`, gets ships to
the engine by **generating `extraShipData.json` in the mission folder** during
`sim_create()`. The file then stays on disk, and on the next run `get_ship_data()` reads it
back **and** the add-on merges the same entries again. Measured on this mod: run 1 gives 51
hulls, run 2 gives **102**, and `filter_ship_data_by_side(None, "Klingon", "warship")`
returns 8 ships where there are 4. `_read_mission_entries` already drops `#mod` entries when
it WRITES that file; `get_ship_data()` does not when it READS it, and that asymmetry is the
bug. Writing nothing sidesteps the whole class - verified stable across three consecutive
runs.

The engine call does not populate sbs_utils' own table, so the add-on merges library-side
too, behind a presence guard. `filter_ship_data_by_side` is how a prefab finds "a Klingon
warship" and `get_ship_name` is what a console displays, so the library needs them as much
as the engine does.

## The factions

The zip's README says what each hull became and then leaves `origin` alone in the data, so
in the running game a Kazon Raider still reported itself Kralien. The mapping was recovered
**from the art prefixes, not the prose** - `FED_`, `CRD_`, `KAZ_`, `RMN_`, `KLG_`, `ORN_`,
`JEM_`, `BRN_` - with the README as the cross-check.

| faction | hulls | fleet ladder | notes |
|---|---|---|---|
| Federation | 24 | - | player faction; LM ships no `tsn` ladder either |
| Cardassian | 5 | yes | |
| Kazon | 5 | yes | |
| Romulan | 5 | yes | |
| Klingon | 4 | yes | |
| Orion | 4 | yes | |
| Dominion | 3 | yes | |
| Breen | 1 | folded into Dominion | the Chel Grett is Breen hardware in Dominion service |
| Borg | 1 | - | hostile to everyone, including the other TNG factions |

Two places the art prefix is the wrong answer, so they are named explicitly: **DS9** wears
Cardassian art but is Federation-run and the zip lists it under USFP; and the three bases on
the "Waiting for … Base" list keep their stock hull, so their name is the only evidence.

`origin`, shipData `side` and `race` all carry the faction name, because in sbs_utils they
are one field - `SpaceObject.race` returns `origin`, and `side` is what
`filter_ship_data_by_side` matches. So this is not cosmetic:

- **Taunts** are looked up by race, so `tng_taunts.json` is keyed by faction. The stock
  names are *not* kept as aliases the way they were in the re-skin version - these hulls no
  longer pretend to be Kralien.
- **Science bio scan** reads "A bunch of romulan creatures". An upgrade.
- **Raider hails** degrade: LM's `raider_hails.amd` has scenes for the stock races only, so
  a Cardassian falls back to its `default` scene. Worth a TNG hails file later.
- **Carrier fighters**: `npc_cag.get_fighter_key` falls through to `arvonian_fighter` for a
  race it does not know, so `tng_kaz_fighter` is unreachable through it. It is already
  marked `# TODO: This is not good enough for modding` in LM.
- **Faces are NOT affected** - both `random_face` callers pass a fleet or prefab race
  string, never the object's origin.

The add-on **adds** its factions to `PLAYABLE_RACES` and `NPC_RACES` rather than replacing
them, so Klingons can raid a TSN crew and a Galaxy can fight Kraliens. A pure TNG game is a
mission setting - name only these factions - not something a mastlib does to you.

## Repairs made on the way in

All applied by `_build_from_zip.py` and printed when it runs, so none are silent.

| repair | why |
|---|---|
| each entry = **current game entry + only the author's own deltas** | keeps 18 `torpedostart` fields the game has moved on; the zip's copy would revert the PShock and Tag rounds |
| `monster_charbdis` dropped | a misspelling of the game's `monster_charybdis`, not new content |
| **every key gets a floor plan** (50) | with unique keys there is no stock plan to fall back on, so a hull the zip does not draw would have *no* Engineering console. Sources: the zip's own plan where it drew one, else LM's `races` plan for the hull it replaced - which is where stock interiors now live, `data/grid_data.json` being empty for hulls races fully plans |
| 7 blanked interiors ignored | the zip ships them as empty lists; they fall through to the derived plan instead |
| `klg_ktinga` re-keyed | the zip keyed that plan by `artfileroot`; grid data is keyed by shipData **key**, so as shipped it matched no hull and did nothing |
| **24 stacked grid cells** resolved | a cell holds one object. Stock uses 0 stacked cells across 162 hulls and `races` 0 across 63, so this is a slip, not an idiom. Weapon and system cells win over rooms, because they feed `system_max_damage` |
| `SHIELD` split into `fwd-shield` / `aft-shield` | the `.grid` legend maps a name to one roleset, and the registry resolves `SHIELD` to *aft* - so all 37 shield cells would have become aft, deleting the forward shield from the damage model. Caught by a round-trip check, not by reading |
| **map sizes grown to fit their interior** | the renderer draws a `w`x`h` box and silently drops anything outside it. Three hulls shrink their map below the extent of the plan they end up with |

### Left alone, deliberately

The floor plans carry **about twice as many torpedo cells as the hull has tubes**, and more
beam cells than beam ports, on nearly every hull. The shipped baseline does not - 21 of 24
`races` plans are exactly one torpedo cell per tube - so this is real drift that inflates the
weapon systems' damage pools. It is also the author's room layout, and quietly deleting
rooms is not a restructuring job. Every mismatch prints as a `WARN`.

## Art: the ship file points straight into the pack

Since engine 1.3.6, `artfileroot` carries the whole path, relative to the exe:

```yaml
artfileroot: data/missions/__lib__/media/ScornMandark.Cosmos-TNG-Mod.media.v0.3.0/ships/FED_Saber
```

That prefix is **baked at build time** from `__lib__.json` (`art_path()` in
`_build_from_zip.py`) - the pack unpacks to `__lib__/media/{owner}.{repo}.media.{version}/`,
and owner, repo and version are all known before release, so nothing has to write a file
while the game runs. If ship art ever goes missing, the baked prefix in
`media/tng_ships.json` is the first suspect: it must match the pack name actually installed.

The engine bakes each hull's derived art (`.paxmesh` etc.) the first time it draws it; the
viewer mission bakes all 47 meshes on a clean install.

### Why `.gitignore` excludes the derived art

A `.paxmesh` is **baked for a location**: it stores its texture paths as length-prefixed
strings (`ships/<root>_diffuse`), so a mesh baked in one folder looks for its textures
relative to where it was baked rather than where it ends up. Committing one means shipping a
mesh that points at somebody else's disk. `*.paxmesh`, `*.pointcube`, `*.rawbitmap`,
`*1024.png` and `*256.png` are therefore all ignored - they are build output, generated from
the `.obj`, and they have to be rebuilt where the art is finally placed.

So the repo ships `.obj` + textures and nothing else.

## Versioning

`__lib__.json` holds the version and everything else derives from it - the mastlib name, the
pack name, the `artfileroot` prefix, and a stamp written into both the ship file and the manifest. At
load the add-on logs it and publishes it as a shared variable, so a running game can say
which build it has.

That stamp is what catches a **half-updated install** - a mastlib from one release sitting
beside a media pack from another, which would otherwise load quietly and render the wrong
hulls. The test range asserts the two agree.

## What the library could do better

Three things this mod ran into. None are applied here - they belong in `sbs_utils`.

1. **`get_ship_data()` should drop `#mod` entries when reading `extraShipData.json`**, the
   way `_read_mission_entries` already does when writing it. Without it, any add-on using
   `ship_data_merge_mod` double-counts its ships from run 2 onward (51 -> 102, measured).
2. **`get_ship_index()` keeps the LAST duplicate.** `merge_mod_ship_yaml` prepends for
   priority, but the index walks front to back, so a prepended override loses. Harmless for
   this mod now that the keys are unique; it is what made the re-skin version disagree with
   the engine. One line: keep the first occurrence.
3. **Taunts have no registry.** Ship data, interiors and fleets each have a `*_merge_mod`
   entry point; taunts do not, so this add-on reaches for LM's `taunt_data` shared variable
   by name after its comms add-on has set it. It works and it is the weakest seam here - a
   rename in LM breaks it silently, with taunts just staying stock.

## Verifying

```
python sbs.pyz lib Cosmos-TNG-Mod -u ScornMandark
python -m cosmos_dev.mission_runner TNG_TestRange --test 8 --map 0
```

`TNG_TestRange` (a sibling mission folder, not part of this repo) is separate on purpose: it has no `tng_races/`
folder of its own, so the compiler cannot substitute the source and it loads the **built**
mastlib out of `__lib__` - the artifact people actually install. (It also has to be a
top-level mission folder, because `pinned_packs` globs one level deep and a nested one could
not pin the media pack.)

### The repo is also a mission - the viewer

```
python -m cosmos_dev.mission_runner Cosmos-TNG-Mod --gui
open http://localhost:8765/server
```

This repo carries its own mission at the **root** (`story.json`, `story.mast`, `maps/`,
`script.py`) beside the addon folders, the shape LegendaryMissions and OpenUniverse already
use. It is a viewer with two screens - every face the addon registers, and every hull it
declares with its stats and 3D model - and its only dependencies are **sbs_utils and this
mod**. No LegendaryMissions.

**That last part is the point, and it is what makes this a pattern rather than a one-off.**
An addon whose test mission needs a 20-addon mission library cannot be verified on its own;
this one can, from a fresh clone, with nothing else installed.

It complements `TNG_TestRange` rather than replacing it - the two answer different questions:

| | loads the addon from | needs LegendaryMissions | answers |
|---|---|---|---|
| this repo's viewer | **source** (MAST source-wins) | no | does the art look right, right now, as I edit it |
| `TNG_TestRange` | the **built** mastlib | yes, 20 addons | does the shipped artifact still merge into a real install |

So the viewer gives a fast edit-and-run loop and will never catch a "forgot to rebuild the
lib" error; that is exactly `TNG_TestRange`'s job. Keep both.

**Four things about this layout are load-bearing** - each was a silent failure first:

- **Root, not a subfolder.** `pinned_packs()` globs `missions/*/story.json` and
  `prune_media()` deletes any unpacked pack nothing pins, so a mission one level deeper
  would have the media pack pruned out from under it. A mission inside `tng_races/` is
  worse - it would be zipped INTO the mastlib and compiled into every consuming mission.
- **No `@map` labels.** The map-selection screen is LM's server console, and the headless
  runner's `--map` auto-start reads `maps_get_list()`, which returns `[]` when no page is
  current. With only sbs_utils, neither exists: the server page comes up blank and the map
  never starts, with no error. An sbs_utils-only mission must draw its own entry screen.
- **`main` falls through into the bootstrap, which lives in `story.mast`.** Every file's
  top-level code is concatenated into one `main`, mission first then addons, so main runs
  `tng_register_faces()` before falling into the first label - no wait loop needed for the
  data, only for the tick. main IS `page.gui_task`, so sitting in that label keeps the gui
  task alive for `gui_task_jump` to redirect. Put the bootstrap in an imported file and
  main ends first, the jump no-ops, and the console stays blank.
- **`import` INLINES the file where it appears**, so the imports go LAST - above the
  top-level code they would push it behind a run of labels and it would stop being `main`.

The 51 checks assert the data ARRIVED - a mastlib that fails to load still reports
`PASS - no runtime errors`, so the verdict alone means nothing. Among them: the stock
`tsn_light_cruiser` is untouched, no TNG key shadows a stock one, every Federation hull has
an interior, every ladder names a key that exists, the forward shields survived the name
split, and LM's own taunt groups are still there.

## Balance

The mod's combat numbers are **generated**, not hand-edited. The design lives in
`_tools/balance_targets.json` — 51 rows of class, shields, hull, guns — and
`_tools/retune_ships.py` writes `media/tng_ships.json` from it. A balance change is a
small reviewable diff in the table, not a 140 KB diff in the ship data.

That matters because the alternative already failed once: `tng_ships.json` and
`tng_reskin.json` held the same ships and had drifted apart by exactly 1.2x on every
Federation beam, with nothing to catch it. The reskin is now generated too.

### Weight classes are the contract

Every hull declares one in its `roles`, and the bands are **adjacent, not nested** —
the top of `light` sits below the bottom of `medium`. Values are forward shields:

| class | shields | hullpoints | guns (`coef_sum`) |
|---|---|---|---|
| fighter / shuttle | 35 – 60 | 1 | 0.30 – 0.55 |
| light | 80 – 130 | 2 – 3 | 0.35 – 0.60 |
| medium | 140 – 200 | 4 – 5 | 0.60 – 0.95 |
| heavy | 210 – 320 | 6 – 8 | 0.90 – 1.40 |
| capital / leader | 350 – 450 | 9 | 1.40 – 2.00 |
| civilian | 60 – 100 | 2 – 6 | 0.00 – 0.15 |
| station | 300 – 800 | 100 – 200 (armor) | 0.00 – 0.60 |

The anchors come from `data/shipData.yaml`, not from taste — `tsn_light_cruiser`
(120 shields, hull 3, guns 0.33) anchors light, `tsn_dreadnought` (220, 8, 0.83)
anchors heavy. **That shared curve is what lets stock and TNG hulls fight on one map**,
which is the whole reason the mod was normalised down rather than the base game up.

**Class first, canon second.** The class fixes the band; canon only decides where
inside it. The Defiant is 171 m, so it is `medium` — and being famously
over-engineered for its size is expressed as the *ceiling* of that band in shields,
hull and guns at once, plus the sharpest turn rate in the class. It beats every other
medium at everything and out-guns the softest heavies. What it cannot do is out-tank a
Galaxy.

`guns` is `sum(damage_coeff / cycle_time)`. Real DPS is that times the
`set_beam_damages` base, which LegendaryMissions sets to 7.0 for players and
`DIFFICULTY/2+3` for NPCs.

### Physical scale

Hulls are drawn at **0.400 game units per metre** (1 unit = 2.5 m). That convention was
*measured*, not chosen: 14 of the 36 hulls with a canonical length already sat within 1%
of it. Canonical lengths and their provenance are in `_tools/canon_lengths.json`, each
marked `onscreen`, `approx` or `by_class`; hulls with no canonical length are sized to
the median of their class. `exclusionradius` is `max(25, 0.52 × drawn length)` — the
floor is stock's own, which gives every cockpit-class craft a flat 25.

### Faction weapons

Beams carry a faction's identity in a fight, because **NPCs never launch torpedoes**;
`arc` and `cycle_bias` in the targets file are what make a Klingon feel unlike a
Starfleet ship. Ordnance splits two ways:

- **Torpedo tubes** only matter on a player-flown hull. Five of the seven factions had
  `tubecount: 0` everywhere, so a mission could not seat a crew in a Romulan or
  Cardassian ship and have them fire anything. They all have tubes now.
- **Drones** (`drone_launch_timer`) are the NPC-facing projectile — the field's presence
  sets `elite_drone_launcher` and the engine fires them. Romulans stand off, the
  Dominion swarms, the Breen lob slowly; Klingons get none and close instead.

### Checkers

Run all four before shipping a stats change. Each exits non-zero on failure.

```
python _tools/balance_report.py    # weight bands, hullpoints, fleet-tier parity
python _tools/scale_report.py      # mesh size vs canonical length, collision radius
python _tools/duel_report.py       # time-to-kill against the engine's own 15-110 s band
python _tools/make_reskin.py       # regenerate the reskin; diff must be empty
```

`retune_ships.py` iterates to a fixed point, so re-running it is free and the output is
byte-stable. Assert that after any change to it — an earlier version was not idempotent
and quietly took the Galaxy's magazine from 40 photons to 16 to 4 across three runs.

### Fleet ladders

`tng_races/*_fleets.yaml` are generated by `_tools/retune_fleets.py`. Every faction
composes waves from its own roster onto one shared power curve, so difficulty *N* is the
same fight whoever shows up — it used to span **51x** at tier 0, and four factions got
*weaker* from tier 3 to tier 4. Faction character moved into the *shape* of a wave: the
Kazon send many cheap hulls, the Breen send one heavy loner, the Romulans send fewer
better ships. The Breen borrow Dominion hulls at low tiers, which the manifest already
declared (`"serves": {"Breen": "Dominion"}`) and which is also the history.
