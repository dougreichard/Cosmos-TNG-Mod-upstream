"""Fetch one reference still per named character, for the face-identity IPAdapter.

The generated leads read as generic without this - "knock offs, not the real
things" was the verdict, and it was correct. SDXL has no reliable idea what these
characters look like and there are no character LoRAs installed, so identity has
to be supplied as an image.

WHY THESE SMALL IMAGES ARE FINE. Wikipedia lead images are mostly 220-280px wide,
which would be useless as an img2img init at 1024 - it would just be the old
upscaling problem again. But they are not used that way. IPAdapter encodes the
reference through CLIP-ViT-H at 224x224, so a 272x365 still carries as much
identity as a 4K one would. The cell itself is still generated fresh at 1024:

    rig_depth.png  -> framing and registration   (ControlNet depth)
    this still     -> identity                   (IPAdapter plus-face)
    style_ref.png  -> house style                (IPAdapter style transfer)
    txt2img @1024  -> the actual pixels

So nothing low-resolution ever reaches the sheet.

These are copyrighted publicity stills. They are fetched to a local scratch folder
as drawing reference for stylized derivative art in a personal mod, are not
redistributed, and are NOT part of the shipped media pack - out/ is scratch. The
mod already ships likeness art of these characters.

Wikipedia's REST summary endpoint is used with a descriptive User-Agent and a
rate limit, per their API etiquette.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "refs")
UA = "cosmos-tng-mod-facegen/1.0 (local art reference; contact: mod author)"

# key -> Wikipedia article title. Written out rather than derived: "data" and "q"
# and "rom" are hopeless as search terms, and a wrong article silently yields a
# confident, wrong face.
TITLES = {
    # TOS
    "kirk": "James T. Kirk", "spock": "Spock", "mccoy": "Leonard McCoy",
    "chekov": "Pavel Chekov", "chapel": "Christine Chapel", "uhura": "Uhura",
    "scotty": "Montgomery Scott", "sulu": "Hikaru Sulu",
    # TNG
    "picard": "Jean-Luc Picard", "riker": "William Riker", "data": "Data (Star Trek)",
    "worf": "Worf", "troi": "Deanna Troi", "beverly_crusher": "Beverly Crusher",
    "tasha_yar": "Tasha Yar", "guinan": "Guinan (Star Trek)",
    "geordi": "Geordi La Forge", "wesley": "Wesley Crusher",
    "obrien": "Miles O'Brien (Star Trek)", "pulaski": "Katherine Pulaski",
    "barclay": "Reginald Barclay", "q": "Q (Star Trek)",
    # DS9
    "sisko": "Benjamin Sisko", "kira": "Kira Nerys", "odo": "Odo (Star Trek)",
    "quark": "Quark (Star Trek)", "rom": "Rom (Star Trek)", "nog": "Nog (Star Trek)",
    "bashir": "Julian Bashir", "dax": "Jadzia Dax", "ezri": "Ezri Dax",
    "garak": "Elim Garak", "dukat": "Dukat (Star Trek)", "jake": "Jake Sisko",
    "martok": "Martok", "gowron": "Gowron", "weyoun": "Weyoun", "damar": "Damar",
    "kai_winn": "Winn Adami", "leeta": "Leeta", "brunt": "Brunt (Star Trek)",
    "zek": "Zek (Star Trek)", "eddington": "Michael Eddington", "bareil": "Bareil Antos",
    # VOY - the era with no existing art at all, so these matter most
    "janeway": "Kathryn Janeway", "chakotay": "Chakotay", "tuvok": "Tuvok",
    "torres": "B'Elanna Torres", "paris": "Tom Paris", "kim": "Harry Kim (Star Trek)",
    "the_doctor": "The Doctor (Star Trek: Voyager)", "neelix": "Neelix",
    "kes": "Kes (Star Trek)", "seven_of_nine": "Seven of Nine",
}

# `_alt` cells are the same person in different dress, so they share a reference.
ALIASES = {"kirk_alt": "kirk", "spock_alt": "spock", "mccoy_alt": "mccoy",
           "picard_alt": "picard", "riker_alt": "riker", "data_alt": "data",
           "worf_alt": "worf", "troi_alt": "troi",
           # Lore is Data's brother, played by the same actor, so he shares the
           # reference and the prompt carries the difference (hair, cruel smile).
           # He also has to be aliased rather than fetched: the "Lore (Star Trek)"
           # article's lead image is a photograph of the ISS, which would have
           # produced a confident, completely wrong face.
           "lore": "data"}


# Actor names, for topping up from Commons when an article is short of stills.
ACTORS = {
    "kirk": "William Shatner", "spock": "Leonard Nimoy", "mccoy": "DeForest Kelley",
    "uhura": "Nichelle Nichols", "sulu": "George Takei", "chekov": "Walter Koenig",
    "scotty": "James Doohan", "chapel": "Majel Barrett",
    "picard": "Patrick Stewart", "riker": "Jonathan Frakes", "data": "Brent Spiner",
    "worf": "Michael Dorn", "troi": "Marina Sirtis", "beverly_crusher": "Gates McFadden",
    "geordi": "LeVar Burton", "tasha_yar": "Denise Crosby", "guinan": "Whoopi Goldberg",
    "wesley": "Wil Wheaton", "obrien": "Colm Meaney", "q": "John de Lancie",
    "barclay": "Dwight Schultz", "pulaski": "Diana Muldaur",
    "sisko": "Avery Brooks", "kira": "Nana Visitor", "odo": "Rene Auberjonois",
    "quark": "Armin Shimerman", "bashir": "Alexander Siddig", "dax": "Terry Farrell",
    "ezri": "Nicole de Boer", "garak": "Andrew Robinson", "dukat": "Marc Alaimo",
    "jake": "Cirroc Lofton", "rom": "Max Grodenchik", "nog": "Aron Eisenberg",
    "martok": "J. G. Hertzler", "gowron": "Robert O'Reilly", "weyoun": "Jeffrey Combs",
    "damar": "Casey Biggs", "kai_winn": "Louise Fletcher", "leeta": "Chase Masterson",
    "brunt": "Jeffrey Combs", "zek": "Wallace Shawn", "eddington": "Kenneth Marshall",
    "janeway": "Kate Mulgrew", "chakotay": "Robert Beltran", "tuvok": "Tim Russ",
    "torres": "Roxann Dawson", "paris": "Robert Duncan McNeill", "kim": "Garrett Wang",
    "the_doctor": "Robert Picardo", "neelix": "Ethan Phillips", "kes": "Jennifer Lien",
    "seven_of_nine": "Jeri Ryan",
}


def _get(url, timeout=20, tries=5):
    """GET with backoff on 429.

    Measured: a 0.4s gap between calls gets the whole run rate-limited about a third
    of the way through, and a 429 arrives as an exception that otherwise reads as
    "this article has no image" - which is a lie that would silently drop a character
    to prompt-only generation. Back off and retry instead.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    delay = 2.0
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == tries - 1:
                raise
            time.sleep(delay)
            delay *= 2


# Junk that turns up in a page's image list: UI chrome, stub icons, and the
# occasional wholly unrelated photo. The "Lore (Star Trek)" article carries an ISS
# photograph, which is how a space station nearly became Data's brother.
_JUNK = ("icon", "logo", "blank television", "dragon-", "commons-", "wikiquote",
         "wikidata", "edit-ltr", "ambox", "question_book", "disambig", "stub",
         "iss-", "symbol", "flag_of", "portal", "star_trek_logo")


def _is_photo(title):
    t = title.lower()
    if not t.endswith((".jpg", ".jpeg", ".png")):
        return False
    return not any(j in t for j in _JUNK)


def api(host, params):
    params.setdefault("format", "json")
    url = "https://%s/w/api.php?%s" % (host, urllib.parse.urlencode(params))
    try:
        return json.loads(_get(url))
    except Exception as e:
        print("   api failed: %s" % e)
        return {}


def page_images(title, host="en.wikipedia.org"):
    """Every real photo on an article, in page order (the lead image tends to be
    first, and is usually the best single reference)."""
    d = api(host, {"action": "query", "prop": "images", "titles": title, "imlimit": 50})
    out = []
    for p in (d.get("query", {}).get("pages", {}) or {}).values():
        for im in p.get("images", []):
            if _is_photo(im["title"]):
                out.append(im["title"])
    return out


def commons_search(term, limit=6):
    """Commons file search - used only to TOP UP a character short of stills."""
    d = api("commons.wikimedia.org", {"action": "query", "list": "search",
                                      "srsearch": term, "srnamespace": 6,
                                      "srlimit": limit})
    return [r["title"] for r in d.get("query", {}).get("search", [])
            if _is_photo(r["title"])]


def file_url(file_title, host="en.wikipedia.org", width=900):
    """Resolve `File:X.jpg` to a downloadable URL, capped to a thumbnail: the
    adapter encodes at 224x224, so pulling a full-size original off someone
    else's server would be wasted bandwidth."""
    d = api(host, {"action": "query", "titles": file_title, "prop": "imageinfo",
                   "iiprop": "url", "iiurlwidth": width})
    for p in (d.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        u = ii.get("thumburl") or ii.get("url")
        if u:
            return u
    return None


MA_HOST = "memory-alpha.fandom.com"

# Memory Alpha article title per key. Usually the character's full name, and it is
# a different namespace from Wikipedia's - "Data" is "Data" here, not
# "Data (Star Trek)".
MA_TITLES = {
    "kirk": "James T. Kirk", "spock": "Spock", "mccoy": "Leonard McCoy",
    "chekov": "Pavel Chekov", "chapel": "Christine Chapel", "uhura": "Nyota Uhura",
    "scotty": "Montgomery Scott", "sulu": "Hikaru Sulu",
    "picard": "Jean-Luc Picard", "riker": "William T. Riker", "data": "Data",
    "worf": "Worf", "troi": "Deanna Troi", "beverly_crusher": "Beverly Crusher",
    "tasha_yar": "Natasha Yar", "guinan": "Guinan", "geordi": "Geordi La Forge",
    "wesley": "Wesley Crusher", "obrien": "Miles O'Brien", "pulaski": "Katherine Pulaski",
    "barclay": "Reginald Barclay", "q": "Q", "lore": "Lore",
    "sisko": "Benjamin Sisko", "kira": "Kira Nerys", "odo": "Odo", "quark": "Quark",
    "rom": "Rom", "nog": "Nog", "bashir": "Julian Bashir", "dax": "Jadzia Dax",
    "ezri": "Ezri Dax", "garak": "Elim Garak", "dukat": "Dukat", "jake": "Jake Sisko",
    "martok": "Martok", "gowron": "Gowron", "weyoun": "Weyoun", "damar": "Damar",
    "kai_winn": "Winn Adami", "leeta": "Leeta", "brunt": "Brunt", "zek": "Zek",
    "eddington": "Michael Eddington", "bareil": "Bareil Antos",
    "janeway": "Kathryn Janeway", "chakotay": "Chakotay", "tuvok": "Tuvok",
    "torres": "B'Elanna Torres", "paris": "Tom Paris", "kim": "Harry Kim",
    "the_doctor": "The Doctor", "neelix": "Neelix", "kes": "Kes",
    "seven_of_nine": "Seven of Nine",
}

# A scene shot is not a portrait. Memory Alpha names files descriptively, so the
# title says whether the image is of THIS character alone or of an event with
# several people in it - which is far more reliable than trying to work it out
# from the pixels.
_SCENE = (" and ", " with ", " meets ", " confronts ", " tours ", " dies",
          " crew", " family", " wedding", " funeral", " bridge", " ship",
          "uss ", "starship", " console", " viewscreen", " planet", " village",
          " pier", " creek", " speech", " imprisoned", " describes")


def ma_score(title, name):
    """Rank a Memory Alpha file as a portrait reference for `name`. None = reject.

    The strong signal is a title that STARTS with the character's name, which is
    Memory Alpha's convention for its canonical portraits - "Jean-Luc Picard,
    2364.jpg", "Jean-Luc Picard, 2379.jpg". Those are exactly the head-and-shoulders
    shots wanted here, and there are usually several per character across eras.
    """
    t = title.lower().replace("file:", "").strip()
    n = name.lower()
    last = n.split()[-1]
    if not t.endswith((".jpg", ".jpeg", ".png")):
        return None
    if any(j in t for j in _JUNK):
        return None
    if any(w in t for w in _SCENE):
        return None
    if t.startswith(n):
        # "<name>, <year>.jpg" is the canonical portrait form - prefer it, and
        # prefer LATER-numbered years only insofar as they are still the series
        # era; no attempt is made to pick an era here, variety is the point.
        return 0 if "," in t else 1
    if t.startswith(last):
        return 2
    if n in t or last in t:
        return 3
    return None


def ma_images(key, want):
    """Best `want` portrait candidates for a key from Memory Alpha, or []."""
    name = MA_TITLES.get(key)
    if not name:
        return []
    titles = page_images(name, host=MA_HOST)
    scored = []
    for t in titles:
        sc = ma_score(t, name)
        if sc is not None:
            scored.append((sc, t))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [t for _, t in scored[:want]]


def summary(title):
    url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
           + urllib.parse.quote(title.replace(" ", "_"), safe=""))
    try:
        return json.loads(_get(url))
    except Exception as e:
        print("   summary failed: %s" % e)
        return None


def fetch(key, title, out_dir, delay=1.5):
    dest_base = os.path.join(out_dir, key)
    for ext in (".jpg", ".png", ".jpeg"):
        if os.path.exists(dest_base + ext):
            return dest_base + ext, "have"
    d = summary(title)
    time.sleep(delay)                       # be polite to the API
    if not d:
        return None, "no summary"
    img = d.get("originalimage") or d.get("thumbnail")
    if not img or not img.get("source"):
        return None, "no image on article"
    src = img["source"]
    ext = os.path.splitext(urllib.parse.urlparse(src).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    dest = dest_base + ext
    try:
        data = _get(src, timeout=30)
    except Exception as e:
        return None, "download failed: %s" % e
    with open(dest, "wb") as f:
        f.write(data)
    time.sleep(delay)
    return dest, "%dx%d" % (img.get("width", 0), img.get("height", 0))


def _download(u, dest, delay):
    if os.path.exists(dest):
        return True
    try:
        data = _get(u, timeout=30)
    except Exception:
        return False
    if not data:
        return False
    with open(dest, "wb") as f:
        f.write(data)
    time.sleep(delay)
    return True


def fetch_many(key, title, out_dir, want=4, actor=None, delay=1.2):
    """Up to `want` references for one character.

    Several references beat one: IPAdapter averages their embeddings, so a single
    unlucky angle, a heavy shadow or one odd expression stops deciding the whole
    identity on its own.

    MEASURED, AND MOSTLY A TRAP. Volume alone makes likeness WORSE. What the
    unfiltered version actually returned:

      picard  a photograph of a flute in a presentation box (Picard's Ressikan flute)
      worf    a rack of bat'leths, and a video game screenshot
      quark   three photos of Armin Shimerman WITHOUT prosthetics - a bald human man
      janeway/seven  modern out-of-costume actor photos, decades after the show

    Averaged into the identity embedding those do not add robustness, they add
    noise, and for a prosthetic character an unmasked actor photo is actively
    wrong. So: ARTICLE images only (--actors is off by default and exists mainly to
    reproduce the finding), and crop_refs.py then drops anything with no detectable
    face, which is what removes the flute, the bat'leths and the screenshot.
    """
    got, srcs = [], []
    # Memory Alpha FIRST. Wikipedia carries 2-4 images per character and several are
    # not the character (a flute, a rack of bat'leths, a video game screenshot);
    # Memory Alpha carries ~60 and names them descriptively enough to pick the
    # portraits out by title alone.
    ma = ma_images(key, want)
    for ft in ma:
        u = file_url(ft, host=MA_HOST)
        time.sleep(delay)
        if not u:
            continue
        ext = os.path.splitext(urllib.parse.urlparse(u).path)[1].lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"
        dest = os.path.join(out_dir, "%s_%d%s" % (key, len(got) + 1, ext))
        if _download(u, dest, delay):
            got.append(os.path.basename(dest))
            srcs.append("MA")
    for ft in ([] if len(got) >= want else page_images(title)[:want - len(got)]):
        u = file_url(ft)
        time.sleep(delay)
        if not u:
            continue
        ext = os.path.splitext(urllib.parse.urlparse(u).path)[1].lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"
        dest = os.path.join(out_dir, "%s_%d%s" % (key, len(got) + 1, ext))
        if _download(u, dest, delay):
            got.append(os.path.basename(dest))
            srcs.append("article")
    if actor and len(got) < want:
        for ft in commons_search(actor, want - len(got)):
            u = file_url(ft, host="commons.wikimedia.org")
            time.sleep(delay)
            if not u:
                continue
            ext = os.path.splitext(urllib.parse.urlparse(u).path)[1].lower()
            ext = ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"
            dest = os.path.join(out_dir, "%s_%d%s" % (key, len(got) + 1, ext))
            if _download(u, dest, delay):
                got.append(os.path.basename(dest))
                srcs.append("commons")
    return got, srcs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=OUT)
    ap.add_argument("--key", action="append", help="fetch only these keys")
    ap.add_argument("--multi", type=int, default=0,
                    help="fetch up to N references per character instead of 1")
    ap.add_argument("--actors", action="store_true",
                    help="ALSO pull Commons photos of the actor. Off by default and "
                         "rarely wanted: they are decades out of period and, for a "
                         "prosthetic character like Quark or Worf, show the actor "
                         "unmasked - which poisons the identity embedding.")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    keys = a.key or sorted(TITLES)
    got, missing = {}, []
    if a.multi:
        multi = {}
        for k in keys:
            title = TITLES.get(k)
            if not title:
                missing.append(k)
                continue
            files, srcs = fetch_many(k, title, a.out, a.multi,
                                     ACTORS.get(k) if a.actors else None)
            print("%-18s %-32s %d refs %s"
                  % (k, title, len(files),
                     "(" + ",".join(srcs) + ")" if files else "NONE"))
            if files:
                multi[k] = files
            else:
                missing.append(k)
        for alt, base in ALIASES.items():
            if base in multi:
                multi[alt] = multi[base]
        with open(os.path.join(a.out, "index_multi.json"), "w") as f:
            json.dump(multi, f, indent=1, sort_keys=True)
        tot = sum(len(v) for v in multi.values())
        print("\n%d characters, %d reference images -> %s"
              % (len(multi), tot, a.out))
        if missing:
            print("no reference for: %s" % ", ".join(missing))
        return

    for k in keys:
        title = TITLES.get(k)
        if not title:
            print("%-18s no title mapping" % k)
            missing.append(k)
            continue
        path, note = fetch(k, title, a.out)
        print("%-18s %-34s %s" % (k, title, note if path else "MISSING (" + note + ")"))
        if path:
            got[k] = os.path.basename(path)
        else:
            missing.append(k)

    # `_alt` keys point at their base character's file rather than fetching twice.
    for alt, base in ALIASES.items():
        if base in got:
            got[alt] = got[base]

    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(got, f, indent=1, sort_keys=True)
    print("\n%d references (+%d alt aliases) -> %s"
          % (len(keys) - len(missing), len(ALIASES), a.out))
    if missing:
        print("no reference for: %s" % ", ".join(missing))
        print("those keys fall back to prompt-only generation.")


if __name__ == "__main__":
    main()
