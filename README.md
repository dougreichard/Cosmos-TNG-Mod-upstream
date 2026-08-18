# Cosmos-TNG-Mod

51 Star Trek hulls across seven factions, restructured from `Cosmos-TNG-Mod_v0-2-3.zip`
(Cosmos 1.2.0, October 2025) so they **declare** instead of overwriting the game.

Nothing in `f:\a\Cosmos-1-3-0\data\` is touched, and nothing is written into the mission
folder either.

## The mod is ADDITIVE, not a re-skin

The zip is a re-skin: it repoints 50 keys the game already owns, so installing it turns
every light cruiser in every mission into a Saber. That approach does work - measured on
engine 1.3.5 by [`missions/shipdata_override`](../shipdata_override), an add-on entry
**beats** the engine's own `shipData.yaml` for the same key, with `speed_coeff` coming back
`0.2199999988079071` (float32 of the declared `0.22`), so it round-tripped the engine's own
C++ table. That answered a question the anime write-up had listed as "still unmeasured".

It is still the wrong shape for a mod. A re-skin is a conversion: two Trek mods can never
coexist, and nothing can spawn a Saber *and* a Light Cruiser. So every hull here gets its
own key, `tng_<faction>_<class>`, and `tsn_light_cruiser` is left exactly as the game
shipped it. The zip's author wants this too - his README calls the re-skin a stopgap
"due to the way Cosmos mission scripts are created… I'll eventually create a TNG mission
suite that breaks away from this."

The era prefix is deliberate: his roadmap has TOS and TMP versions next, and every Trek era
has a Federation cruiser.

## Layout: who reads it decides where it lives

The useful split is not "art vs code". It is **what the ENGINE opens** (needs real files on
a real disk) versus **what MAST reads** (perfectly happy inside a zip).

```
Cosmos-TNG-Mod/
  __lib__.json          {"version":"v0.2.3","mastlib":["tng_races"],"zip":["media"]}
  media/                -> artemis-sbs.Cosmos-TNG-Mod.media.v0.2.3.zip
    tng_ships.yaml         51 hulls: the ENGINE opens this one itself
    ships/  audio/  fonts/  faces/
  tng_races/            -> artemis-sbs.Cosmos-TNG-Mod.tng_races.v0.2.3.mastlib  (FLAT)
    __init__.mast  tng_setup.py  tng_manifest.json
    tng_sides.amd          seven factions + diplomacy
    tng_taunts.json        Trek taunts, keyed by faction
    tng_<key>.grid   x50   one floor plan per hull
    tng_<faction>_fleets.yaml  x6
  .gitignore            keeps derived art (*.paxmesh etc.) out of source control
  _build_from_zip.py    regenerates all of it from the zip, reporting every repair
```

`sbs.pyz lib Cosmos-TNG-Mod` builds both and unpacks the media pack **once** into
`__lib__/media/<pack>/`, where every mission reads the same copy.

A mission takes the mod with two lines:

```json
"mastlib": [ ..., "artemis-sbs.Cosmos-TNG-Mod.tng_races.v0.2.3.mastlib" ],
"shared_media": [ "artemis-sbs.Cosmos-TNG-Mod.media.v0.2.3.zip" ]
```

Both are needed: the mastlib is the logic, and the pack is where the engine-read ship data
and the art live. Unlike the re-skin version, **load order no longer matters** - unique keys
collide with nothing, so there is no race against LM's `races` add-on to lose.

### No generated file, because the engine has an API for this

`sbs.add_extra_ship_data(name, path)` (engine 1.3.5) points the engine straight at the mod's
own ship file - already probed in [`missions/shipdata_api`](../shipdata_api), which confirmed
the engine loads a ship from a mod folder with nothing written into the mission.

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

## Art: the mechanism exists, one engine crash is in the way

**Engine 1.3.5 added what this needed**, and it is already wired up here:

```yaml
artfileroot: FED_Saber                                    # the file's BASE NAME
artfilepath: data/missions/__lib__/media/<pack>/ships     # the FOLDER, relative to the EXE
```

They work together rather than one replacing the other. `artfilepath` is **baked at build
time** from `__lib__.json` - the pack unpacks to
`__lib__/media/{owner}.{repo}.media.{version}/`, and owner, repo and version are all known
before release, so a CI-built artifact carries the right path and nothing has to write a
file while the game runs. The add-on keeps a self-heal check for the case where the two
disagree (someone re-versioned by hand, or unpacked under a different name); on a normal run
it finds the value already correct and touches nothing.

Verified in the engine: `artfilepath resolves on disk` is one of the checks the test range
runs, and it passes against the real 1.3.5.

**What still blocks the hulls rendering:** generating derived art from a bare `.obj` crashes
the engine - it writes `<root>1024.png` and dies with an access violation. Art that already
has its `.paxmesh` / `.pointcube` / `1024` / `256` renders fine, which is why the engine
team's own `BeamArcTest` example never hits it. Write-up and reproducer:
`VisualTestRange/ENGINE_BUG_derived_art_generation.md`. (A second, probably related crash:
an unresolvable `artfileroot` segfaults where 1.3.4 drew the `unknown` placeholder.)

So the pack ships the derived files for now, and `.gitignore` keeps them out of source
control - see below.

### Why `.gitignore` excludes the derived art

A `.paxmesh` is **baked for a location**: it stores its texture paths as length-prefixed
strings (`ships/<root>_diffuse`), so a mesh baked in one folder looks for its textures
relative to where it was baked rather than where it ends up. Committing one means shipping a
mesh that points at somebody else's disk. `*.paxmesh`, `*.pointcube`, `*.rawbitmap`,
`*1024.png` and `*256.png` are therefore all ignored - they are build output, generated from
the `.obj`, and they have to be rebuilt where the art is finally placed.

That is a policy the repo can hold today even though the engine cannot yet regenerate them
in place. The moment it can, a mod ships `.obj` + textures and nothing else.

## Versioning

`__lib__.json` holds the version and everything else derives from it - the mastlib name, the
pack name, `artfilepath`, and a stamp written into both the ship file and the manifest. At
load the add-on logs it and publishes it as a shared variable, so a running game can say
which build it has.

That stamp is what catches a **half-updated install** - a mastlib from one release sitting
beside a media pack from another, which would otherwise load quietly and render the wrong
hulls. The test range asserts the two agree.

## What the library could do better

Three things this mod ran into. None are applied here - `sbs_utils` is another session's.

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
python sbs.pyz lib Cosmos-TNG-Mod
python -m cosmos_dev.mission_runner TNG_TestRange --test 8 --map 0
```

[`TNG_TestRange`](../TNG_TestRange) is a separate mission on purpose: it has no `tng_races/`
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
