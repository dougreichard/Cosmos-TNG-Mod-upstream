"""Generate face cells for the TNG mod through a local ComfyUI SDXL server.

Run ComfyUI FIRST, on 8188 (not 8189 - the model tree is shared between the two
installs but ComfyUI_IPAdapter_plus and comfyui_controlnet_aux are only installed
on 8188):

    C:/Users/DougR/miniforge3/envs/comfyui/python.exe E:/ai/ComfyUI/main.py \
        --listen 127.0.0.1 --port 8188

Three things hold ~320 independently generated busts together as one set:

  RIG        every cell is conditioned by the same depth bust (_tools/rig_depth.png),
             so head size, crop and centre agree. This is also what makes layered
             implant/VISOR overlays register against any base - see make_rig.py.
  STYLE REF  IPAdapter in "style transfer" mode carries the house style from one
             frozen reference image. Style comes from the reference, NOT from
             prompt wording, which is the only way it stays put across hundreds of
             prompts. weight_type matters: plain "linear" drags the reference's
             composition and face along with its style.
  SEED       derived from the cell key, so re-rolling one cell cannot disturb any
             other, and a whole run reproduces.

Two modes:

  txt2img    rig + prompt. Archetypes, new races, and all of Voyager (there is no
             existing VOY art to inherit likeness from).
  from-cell  img2img over the existing 512 cell upscaled to 1024. For the ~36
             identified characters: identity, pose and uniform carry across from
             art that already reads as the right person, and the checkpoint
             supplies detail that was never in a 192x256 source.

Cells are generated on a flat background and keyed to alpha afterwards by
cutcells.py, because SDXL cannot emit an alpha channel. See BG below for why the
background is neutral rather than a chroma-key colour.
"""
import argparse
import glob
import hashlib
import io
import json
import mimetypes
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RIG = os.path.join(HERE, "rig_depth.png")

# The background only has to be FLAT, not a particular colour. cutcells.py keys it by
# flood-filling inward from the border, which stops dead at the bold outline the house
# style draws around the bust - so the fill never needs to tell background from skin.
#
# It was magenta once, on the theory that no Trek uniform is magenta. Measured: SDXL
# obligingly tinted the entire subject magenta too, because a colour named three times
# in the prompt is a colour the model paints everything with. A neutral, weakly-stated
# background leaves the subject alone and keys just as well.
BG = "plain flat light grey studio background"

# The house style, in words. The FROZEN style_ref.png is what actually carries the
# look - the style board proved neither checkpoint stylizes from wording alone - but
# the words still steer, and keeping them here means the style lives in exactly one
# place. Changing either this or style_ref.png invalidates every cell already made.
#
# The target is Star Trek: The Animated Series. That choice does more than set a look:
# a photographic identity reference and a painterly style reference pull AGAINST each
# other, which is why likeness and style kept trading off during calibration. A flat
# cel target pulls the same way the simplification does, and TAS exists as proof that
# these characters stay recognisable when reduced to flat color and a hard outline -
# which is also exactly what survives at the ~64px gui_face actually draws.
STYLE_TEXT = ("1970s Filmation limited animation cel, flat unshaded blocks of color, "
              "heavy uniform-weight black outlines, no gradients, no rendering, "
              "simplified geometric facial features, large clean shapes, retro "
              "saturated television animation, animation model sheet")

FRAMING = ("head and shoulders bust portrait, facing the viewer straight on, "
           "centered, head near the top of the frame, shoulders filling the bottom "
           "edge, even frontal lighting, no hands, no props")

NEG = ("photo, photograph, photorealistic, 3d render, blurry, low resolution, jpeg "
       "artifacts, upscaled, soft focus, grainy, "     # the exact failure of the old set
       "full body, legs, hands, arms, waist, standing figure, "
       "profile view, side view, looking away, tilted head, "
       "multiple people, two heads, crowd, group, collage, grid, sprite sheet, "
       "border, frame, picture frame, vignette, gradient background, scenery, "
       "starfield, spaceship interior, room, wall, "
       # These help but DO NOT solve it. "comic book illustration" in the positive
       # prompt drags in comic COVER conventions - radial bursts, halos, bridge sets
       # behind the head. Measured border variance with these negatives in place was
       # still 29-57 (bursts became gradients and interiors), so the background is NOT
       # reliably flat and a chroma/flood key cannot be trusted. cutcells.py mattes the
       # bust out instead, which is why the background prompt is now cosmetic only.
       "radial lines, speed lines, sunburst, starburst, halo, rays, glow behind head, "
       "background pattern, decorative background, ornament, texture, brush strokes, "
       "splatter, ink splash, dramatic background, action lines, motion lines, "
       "text, watermark, signature, logo, caption, letters, "
       "extra eyes, deformed face, disfigured, mutated, asymmetric eyes")


def _api(server):
    base = "http://" + server

    def get(p):
        return json.loads(urllib.request.urlopen(base + p, timeout=300).read())

    def post(p, d):
        r = urllib.request.Request(base + p, data=json.dumps(d).encode(),
                                   headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(r, timeout=300).read())

    def upload(path):
        """POST an image to /upload/image; returns the server-side filename."""
        path = os.path.abspath(path)
        boundary = "----facegen" + uuid.uuid4().hex
        data = open(path, "rb").read()
        ctype = mimetypes.guess_type(path)[0] or "image/png"
        b = io.BytesIO()

        def w(s):
            b.write(s.encode() if isinstance(s, str) else s)

        w("--" + boundary + "\r\n")
        w('Content-Disposition: form-data; name="image"; filename="'
          + os.path.basename(path) + '"\r\n')
        w("Content-Type: " + ctype + "\r\n\r\n")
        w(data)
        w("\r\n")
        w("--" + boundary + "\r\n")
        w('Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n')
        w("--" + boundary + "--\r\n")
        req = urllib.request.Request(
            base + "/upload/image", data=b.getvalue(),
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        r = json.load(urllib.request.urlopen(req, timeout=300))
        return r["name"] if not r.get("subfolder") else r["subfolder"] + "/" + r["name"]

    def view(fn, sub, typ, dest):
        q = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
        with urllib.request.urlopen(base + "/view?" + q, timeout=300) as r:
            open(dest, "wb").write(r.read())

    return get, post, upload, view


def seed_for(key, candidate):
    """Per-key seed, so one cell can be re-rolled without disturbing the rest."""
    h = hashlib.sha256((key + "#" + str(candidate)).encode()).hexdigest()[:8]
    return int(h, 16) % (2 ** 31)


class Graph:
    """Thin wrapper that fills each node's required inputs from /object_info.

    Same trick as VenusClouds/_venus_gen_ref.py: the graph then only has to state
    what actually differs from the node's own defaults, so it does not rot every
    time a node gains an input.
    """

    def __init__(self, object_info):
        self.oi = object_info
        self.g = {}
        self._n = 0

    def _defaults(self, cls):
        o = {}
        for n, s in self.oi[cls]["input"].get("required", {}).items():
            t = s[0]
            m = s[1] if len(s) > 1 and isinstance(s[1], dict) else {}
            if isinstance(t, list):
                o[n] = m.get("default", t[0] if t else None)
            elif t in ("INT", "FLOAT", "STRING", "BOOLEAN"):
                o[n] = m.get("default", 0 if t in ("INT", "FLOAT")
                             else ("" if t == "STRING" else False))
        return o

    def add(self, cls, **w):
        self._n += 1
        nid = str(self._n)
        i = self._defaults(cls)
        i.update(w)
        self.g[nid] = {"class_type": cls, "inputs": i}
        return nid


def build(oi, prompt, ckpt, seed, steps, cfg, rig_name, cn_strength,
          style_name, ip_weight, init_name=None, denoise=1.0, size=1024,
          prefix="facegen", cn_end=0.5, bg=None, face_name=None,
          face_weight=0.8, face_end=0.9, lora=None, lora_weight=0.9):
    G = Graph(oi)
    ck = G.add("CheckpointLoaderSimple", ckpt_name=ckpt)
    model, clip = [ck, 0], [ck, 1]

    # --- style, in the weights -------------------------------------------------
    # Trained on the 127 finished cells, which ARE the target: 512 bust tiles in TAS
    # style on a flat backdrop. A LoRA holds the style in the model rather than
    # fighting for it through an adapter, which is what frees the IPAdapter to carry
    # identity alone - the two were competing for the same influence before.
    if lora:
        ll = G.add("LoraLoader", model=model, clip=clip, lora_name=lora,
                   strength_model=lora_weight, strength_clip=lora_weight)
        model, clip = [ll, 0], [ll, 1]

    # --- identity lock --------------------------------------------------------
    # WHO the face is. SDXL has no dependable idea what these characters look like
    # and there are no character LoRAs installed, so prompting alone returned, in the
    # author's words, "knock offs, not the real things". A publicity still through the
    # plus-face IPAdapter supplies the identity instead.
    #
    # Applied BEFORE the style adapter so style has the last word on rendering; the
    # reference only has to carry who it is, not how it is drawn. weight_type is
    # "linear" here (full transfer) because unlike the style reference we DO want the
    # subject, not just its treatment.
    #
    # The reference is never used as an init image. It is encoded through CLIP-ViT-H
    # at 224x224, so a 272x365 Wikipedia still carries as much identity as a large one
    # would, and the cell is still generated fresh at 1024 - none of the reference's
    # resolution reaches the sheet. See fetch_refs.py.
    if face_name:
        names = face_name if isinstance(face_name, (list, tuple)) else [face_name]
        fl = G.add("IPAdapterModelLoader",
                   ipadapter_file="ip-adapter-plus-face_sdxl_vit-h.safetensors")
        cv = G.add("CLIPVisionLoader",
                   clip_name="CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
        # Several references are batched and their embeddings AVERAGED, so one
        # unlucky angle or a hard shadow stops deciding the identity on its own.
        # Only images with a real detected face reach here - see crop_refs.py, which
        # exists because an article's image list also contains props and scenery.
        img_ref = G.add("LoadImage", image=names[0])
        img_out = [img_ref, 0]
        for extra in names[1:]:
            nxt = G.add("LoadImage", image=extra)
            img_out = [G.add("ImageBatch", image1=img_out, image2=[nxt, 0]), 0]
        fa = G.add("IPAdapterAdvanced", model=model, ipadapter=[fl, 0],
                   image=img_out, weight=face_weight, weight_type="linear",
                   combine_embeds="average", clip_vision=[cv, 0],
                   start_at=0.0, end_at=face_end)
        model = [fa, 0]

    # --- style lock -----------------------------------------------------------
    # "style transfer" takes the reference's rendering style but not its subject.
    # With plain "linear" every cell drifts toward the reference person's face.
    if style_name:
        ipl = G.add("IPAdapterUnifiedLoader", model=model,
                    preset="STANDARD (medium strength)")
        sref = G.add("LoadImage", image=style_name)
        ipa = G.add("IPAdapterAdvanced", model=[ipl, 0], ipadapter=[ipl, 1],
                    image=[sref, 0], weight=ip_weight, weight_type="style transfer")
        model = [ipa, 0]

    bg = BG if bg is None else bg
    text = prompt + ", " + FRAMING + ((", " + bg) if bg else "")
    pos = G.add("CLIPTextEncode", text=text, clip=clip)
    neg = G.add("CLIPTextEncode", text=NEG, clip=clip)
    cpos, cneg = [pos, 0], [neg, 0]

    # --- framing / registration lock ------------------------------------------
    # The rig steers COMPOSITION, not content, so it must release partway through the
    # sampling. Held too long or too hard it stops being a guide and gets traced.
    # Measured sweep at end=0.5, SDXL base, same prompt and seeds:
    #   0.00  good art, but no framing control at all - one result came back a
    #         full-body figure in a cape, which is precisely what the rig exists to stop
    #   0.25  correct bust framing every time, centred, head and shoulders where the
    #         measured set puts them, and full facial detail            <-- use this
    #   0.40  tracing begins: blank egg heads, helmet-shaped skull outlines
    #   0.55/end 0.85  returns the rig itself as flat vector shapes, nose bump and all
    if rig_name:
        cn = G.add("ControlNetLoader",
                   control_net_name="controlnet-depth-sdxl-1.0.safetensors")
        rig = G.add("LoadImage", image=rig_name)
        ap = G.add("ControlNetApplyAdvanced", positive=cpos, negative=cneg,
                   control_net=[cn, 0], image=[rig, 0], strength=cn_strength,
                   start_percent=0.0, end_percent=cn_end)
        cpos, cneg = [ap, 0], [ap, 1]

    # --- latent: empty for txt2img, the upscaled old cell for from-cell --------
    if init_name:
        src = G.add("LoadImage", image=init_name)
        up = G.add("ImageScale", image=[src, 0], width=size, height=size,
                   upscale_method="lanczos", crop="disabled")
        lat = G.add("VAEEncode", pixels=[up, 0], vae=[ck, 2])
    else:
        lat = G.add("EmptyLatentImage", width=size, height=size, batch_size=1)
        denoise = 1.0

    ks = G.add("KSampler", model=model, positive=cpos, negative=cneg,
               latent_image=[lat, 0], seed=seed, steps=steps, cfg=cfg,
               sampler_name="dpmpp_2m", scheduler="karras", denoise=denoise)
    dec = G.add("VAEDecode", samples=[ks, 0], vae=[ck, 2])
    save = G.add("SaveImage", images=[dec, 0], filename_prefix=prefix)
    return G.g, save


# The existing cells are CUTOUTS. Handing one to LoadImage turns transparent into
# BLACK, and img2img then renders the subject lit against black while every txt2img
# cell is lit against the style reference's neutral grey - so the ~19 from-cell leads
# would come out subtly darker and rim-lit differently from the other ~345 cells.
# Flattening onto the same neutral first is what keeps the two paths one set.
NEUTRAL = (235, 235, 238)


def _flatten(path, cache={}):
    if path in cache:
        return cache[path]
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    if im.getchannel("A").getextrema()[0] == 255:
        cache[path] = path
        return path
    bg = Image.new("RGBA", im.size, NEUTRAL + (255,))
    bg.alpha_composite(im)
    # Scratch, NOT beside the source: writing "_flat_c08r00.png" into
    # new/work/facecells left 19 temp files sitting in the directory that is
    # supposed to hold exactly the 192 original cells.
    scratch = os.path.join(HERE, "out", "_flat")
    os.makedirs(scratch, exist_ok=True)
    dest = os.path.join(scratch, os.path.basename(path))
    bg.convert("RGB").save(dest)
    cache[path] = dest
    return dest


def run(jobs, server, ckpt, rig, style_ref, out_dir, steps, cfg,
        cn_strength, ip_weight, size, cn_end=0.5, bg=None, face_dir=None,
        face_weight=0.8, face_end=0.9, lora=None, lora_weight=0.9,
        timeout=7200, verbose=True):
    """jobs: list of dicts {key, prompt, candidate, denoise, init_path}."""
    get, post, upload, view = _api(server)
    oi = get("/object_info")
    os.makedirs(out_dir, exist_ok=True)

    rig_name = upload(rig) if rig else None
    style_name = upload(style_ref) if style_ref else None
    if verbose:
        print("rig=%s  style=%s  ckpt=%s" % (rig_name, style_name, ckpt))

    inits = {}
    faces = {}
    queued = []
    for j in jobs:
        init_name = None
        if j.get("init_path"):
            p = j["init_path"]
            if p not in inits:
                inits[p] = upload(_flatten(p))
            init_name = inits[p]
        face_name = None
        fp = j.get("face_ref")
        if fp:
            paths = fp if isinstance(fp, (list, tuple)) else [fp]
            up = []
            for q in paths:
                if not os.path.exists(q):
                    continue
                if q not in faces:
                    faces[q] = upload(q)
                up.append(faces[q])
            face_name = up or None
        seed = j.get("seed") or seed_for(j["key"], j["candidate"])
        prefix = "fg_%s_c%d" % (j["key"], j["candidate"])
        g, save_id = build(oi, j["prompt"], ckpt, seed, steps, cfg, rig_name,
                           cn_strength, style_name, ip_weight, init_name,
                           j.get("denoise", 1.0), size, prefix,
                           j.get("cn_end", cn_end), bg, face_name,
                           j.get("face_weight", face_weight), face_end,
                           lora, lora_weight)
        try:
            pid = post("/prompt", {"prompt": g, "client_id": "facegen"})["prompt_id"]
        except urllib.error.HTTPError as e:
            print("VALIDATION FAILED %s c%d:\n%s"
                  % (j["key"], j["candidate"], e.read().decode()[:1500]))
            raise SystemExit(1)
        queued.append((j, pid, save_id, seed))
        if verbose:
            print("queued %s c%d seed %d" % (j["key"], j["candidate"], seed), flush=True)

    if verbose:
        print("--- %d queued, rendering ---" % len(queued), flush=True)
    # Poll /queue, NOT /history per prompt. The per-prompt version issued one HTTP
    # request per outstanding job per cycle - with ~1100 queued that is ~1100 requests
    # a sweep, so the progress counter fell hours behind the actual work (it reported
    # 29 done when the server had executed 116) and it pointlessly hammered the server
    # it was waiting on. /queue answers the same question in one request.
    t0 = time.time()
    total = len(queued)
    last = -1
    while time.time() - t0 < timeout:
        try:
            q = get("/queue")
            left = len(q.get("queue_running", [])) + len(q.get("queue_pending", []))
        except Exception:
            time.sleep(3)
            continue
        if left == 0:
            break
        done = total - left
        if verbose and done // 25 != last // 25:
            rate = (time.time() - t0) / max(done, 1)
            print("  %d/%d done  (~%.0f min left)"
                  % (done, total, rate * left / 60), flush=True)
            last = done
        time.sleep(5)

    written = []
    for j, pid, save_id, seed in queued:
        h = get("/history/" + pid).get(pid, {})
        st = h.get("status", {}).get("status_str")
        imgs = h.get("outputs", {}).get(save_id, {}).get("images", [])
        if st != "success" or not imgs:
            print("FAILED %s c%d: %s %s" % (j["key"], j["candidate"], st,
                                            json.dumps(h.get("status", {}))[:400]))
            continue
        im = imgs[0]
        dest = os.path.join(out_dir, "%s_c%d.png" % (j["key"], j["candidate"]))
        view(im["filename"], im.get("subfolder", ""), im.get("type", "output"), dest)
        written.append(dest)
    if verbose:
        print("wrote %d/%d to %s" % (len(written), len(queued), out_dir))
    return written


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", help="face_roster.json")
    ap.add_argument("--key", action="append", help="generate only these keys (repeatable)")
    ap.add_argument("--era", help="filter roster by era (tos/tng/ds9/voy)")
    ap.add_argument("--race", help="filter roster by race")
    ap.add_argument("--subject", help="ad-hoc: one prompt, no roster")
    ap.add_argument("--name", default="adhoc", help="key to use with --subject")
    ap.add_argument("--candidates", type=int, default=4)
    ap.add_argument("--denoise", type=float, default=0.70,
                    help="from-cell img2img strength. Measured on picard+kirk: 0.45 keeps "
                         "the old mush, 0.60 balances, 0.75 matches the new style best but "
                         "drifts; 0.70 buys style coherence with the txt2img cells while "
                         "the likeness still reads.")
    ap.add_argument("--cells", default=None, help="dir of existing 512 cells for from-cell")
    ap.add_argument("--force-txt2img", action="store_true")
    ap.add_argument("--ckpt", default="sd_xl_base_1.0.safetensors")
    ap.add_argument("--rig", default=DEFAULT_RIG)
    ap.add_argument("--no-rig", action="store_true")
    ap.add_argument("--style-ref", default=os.path.join(HERE, "style_ref.png"))
    ap.add_argument("--lora", default="tas_style.safetensors",
                    help="style LoRA trained on the finished cells; '' to disable")
    ap.add_argument("--lora-weight", type=float, default=0.9)
    ap.add_argument("--ip-weight", type=float, default=0.85)
    ap.add_argument("--face-refs", default=os.path.join(HERE, "out", "refs"),
                    help="dir of character reference stills + index.json (fetch_refs.py)")
    ap.add_argument("--no-face-refs", action="store_true")
    ap.add_argument("--face-weight", type=float, default=0.85)
    ap.add_argument("--face-end", type=float, default=0.55,
                    help="fraction of sampling the face reference steers. Measured on "
                         "picard/janeway/seven/quark: held to 0.9 the identity adapter "
                         "overpowers the style adapter and the cell comes back "
                         "semi-realistic with the reference's background; 0.55 keeps the "
                         "likeness and lets the house style win the late steps; 0.35 is "
                         "the most stylized but the likeness starts to slip.")
    ap.add_argument("--cn-strength", type=float, default=0.25)
    ap.add_argument("--cn-end", type=float, default=0.5,
                    help="fraction of sampling the rig steers; past ~0.6 it gets traced")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=6.5)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--style-text", default=STYLE_TEXT)
    ap.add_argument("--bg", default=None,
                    help="override the background phrase; empty string to omit it")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "raw"))
    a = ap.parse_args()

    jobs = []
    if a.subject:
        for c in range(a.candidates):
            jobs.append({"key": a.name, "prompt": a.subject, "candidate": c})
    else:
        if not a.roster:
            ap.error("need --roster or --subject")
        roster = json.load(open(a.roster))
        entries = roster["cells"] if isinstance(roster, dict) else roster
        # Character reference stills, by key. Only the named characters have one;
        # archetypes and race pools are meant to be new people, not likenesses.
        refs = {}
        if not a.no_face_refs:
            ix = os.path.join(a.face_refs, "index.json")
            if os.path.exists(ix):
                refs = {k: os.path.join(a.face_refs, v)
                        for k, v in json.load(open(ix)).items()}
        for e in entries:
            if a.key and e["key"] not in a.key:
                continue
            if a.era and e.get("era") != a.era:
                continue
            if a.race and e.get("race") != a.race:
                continue
            init = None
            if not a.force_txt2img and e.get("mode") == "from-cell" and a.cells:
                p = os.path.join(a.cells, e.get("source_cell", "") + ".png")
                init = p if os.path.exists(p) else None
            for c in range(a.candidates):
                prompt = e["prompt"]
                if a.style_text:
                    prompt += ", " + a.style_text
                jobs.append({"key": e["key"], "prompt": prompt, "candidate": c,
                             "init_path": init,
                             "face_ref": refs.get(e["key"]),
                             "denoise": a.denoise if init else 1.0})
    if not jobs:
        print("nothing to do")
        return
    run(jobs, a.server, a.ckpt, None if a.no_rig else a.rig, a.style_ref, a.out,
        a.steps, a.cfg, a.cn_strength, a.ip_weight, a.size, a.cn_end, a.bg,
        None, a.face_weight, a.face_end, a.lora or None, a.lora_weight)


if __name__ == "__main__":
    main()
