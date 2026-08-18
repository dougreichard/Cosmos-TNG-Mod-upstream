"""Render the canonical bust depth rig used to condition every face cell.

One rig image conditions all ~320 cells, which buys two separate things:

  * FRAMING - independently generated busts share a head size, crop and centre,
    so a sheet reads as one set instead of 320 unrelated portraits.
  * REGISTRATION - because the head lands in the same place every time, an
    implant/VISOR overlay drawn once fits every base. Layered faces only work
    while this holds, so the rig is frozen once generation starts and its hash
    is recorded beside the sheets (see _tools/README).

The geometry is not invented: it is measured from the 190 non-junk cells of the
existing set (`new/work/facecells`), so regenerated art keeps the framing the
mod already ships. Measured at 512, doubled here:

    silhouette x 64..447 (centred, 64px margins)   head touches the top edge
    neck narrowest at y=288                        shoulders full-width by y=384

Depth convention is SDXL/xinsir: WHITE IS NEAREST.
"""
import argparse, hashlib, math
import numpy as np
from PIL import Image, ImageFilter

S = 1024                      # rig is square and matches the SDXL generation size
CX = S // 2

# --- measured geometry, at 1024 (512-space measurements x2) -------------------
HEAD_CY, HEAD_RX, HEAD_RY = 330.0, 240.0, 272.0   # skull; scalp allowance, no hair
NECK_CX_HALF, NECK_TOP, NECK_BOT = 112.0, 500.0, 700.0
SHOULDER_TOP, SHOULDER_HALF = 636.0, 384.0        # 384 = full measured half-width
SHOULDER_ROUND = 105.0                            # how fast the slope reaches full width
NOSE_CY, NOSE_RX, NOSE_RY, NOSE_H = 400.0, 34.0, 62.0, 0.055

# Depth bands. Kept apart so the parts read as separate solids to the ControlNet
# rather than one blob; combined with max() so the head correctly occludes neck.
BG, SHOULDER_Z, NECK_Z, HEAD_Z = 0.0, 0.42, 0.52, 0.60
SHOULDER_BULGE, NECK_BULGE, HEAD_BULGE = 0.13, 0.10, 0.34


def _grid():
    y, x = np.mgrid[0:S, 0:S].astype(np.float64)
    return x, y


def build():
    x, y = _grid()
    z = np.full((S, S), BG)

    # Shoulders: a wide slab whose top edge curves down away from the neck, so the
    # trapezius reads as a slope instead of a shelf.
    dx = np.abs(x - CX)
    shoulder_edge = SHOULDER_TOP + SHOULDER_ROUND * (dx / SHOULDER_HALF) ** 2
    sh = (dx <= SHOULDER_HALF) & (y >= shoulder_edge)
    bulge = np.sqrt(np.clip(1.0 - (dx / SHOULDER_HALF) ** 2, 0, 1))
    z = np.where(sh, SHOULDER_Z + SHOULDER_BULGE * bulge, z)

    # Neck: a cylinder, so its shading cue is horizontal only.
    nk = (dx <= NECK_CX_HALF) & (y >= NECK_TOP) & (y <= NECK_BOT)
    nbulge = np.sqrt(np.clip(1.0 - (dx / NECK_CX_HALF) ** 2, 0, 1))
    z = np.where(nk, np.maximum(z, NECK_Z + NECK_BULGE * nbulge), z)

    # Head: an ellipsoid. sqrt of the remaining radius term is the sphere profile.
    r2 = ((x - CX) / HEAD_RX) ** 2 + ((y - HEAD_CY) / HEAD_RY) ** 2
    hd = r2 <= 1.0
    z = np.where(hd, np.maximum(z, HEAD_Z + HEAD_BULGE * np.sqrt(np.clip(1 - r2, 0, 1))), z)

    # A restrained nose. Enough to tell the model the face is frontal and where the
    # centreline is; not enough to impose a nose shape on every species.
    n2 = ((x - CX) / NOSE_RX) ** 2 + ((y - NOSE_CY) / NOSE_RY) ** 2
    z = np.where(n2 <= 1.0, z + NOSE_H * np.sqrt(np.clip(1 - n2, 0, 1)), z)

    img = Image.fromarray((np.clip(z, 0, 1) * 255).astype(np.uint8), "L")
    # Small blur only: enough to kill the aliased silhouette that made the old
    # rig_depth_00.png stair-step, not enough to soften the depth bands.
    return img.filter(ImageFilter.GaussianBlur(2.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="rig_depth.png")
    a = ap.parse_args()
    img = build()
    img.save(a.out)
    h = hashlib.sha256(open(a.out, "rb").read()).hexdigest()[:16]
    print(f"{a.out}  {img.size[0]}x{img.size[1]}  sha256:{h}")
    print("FREEZE THIS. Overlays generated against a different rig will not register.")


if __name__ == "__main__":
    main()
