"""`cover=` — the chrome remover (spec §12.11).

Cropping only removes baked-in viewer chrome when nothing real shares its x-range; on a
wide drawing the sheet's own labels usually do, at some other height. Covering paints the
chrome out in place with the sampled local background, so the neighbour survives.
"""

from __future__ import annotations

from PIL import Image

from corpus.transforms import RenderContext
from corpus.transforms.image import cover


def _ctx() -> RenderContext:
    return RenderContext()


def _sheet() -> Image.Image:
    """A white sheet with a black 'icon' block top-right and a black 'label' bar lower down
    that shares the icon's x-range — the geometry that defeats a crop."""
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    for x in range(180, 200):
        for y in range(0, 20):
            img.putpixel((x, y), (0, 0, 0))  # chrome
    for x in range(150, 195):
        for y in range(80, 90):
            img.putpixel((x, y), (0, 0, 0))  # real content, same x-range, different height
    return img


def test_cover_removes_chrome_and_keeps_the_neighbour():
    out = cover(_sheet(), "0.9,0,0.1,0.2", _ctx())
    assert out.getpixel((190, 10)) == (255, 255, 255)  # chrome painted out
    assert out.getpixel((190, 85)) == (0, 0, 0)  # the label that a crop would have cost


def test_cover_samples_the_local_background_not_white():
    """A tinted background must stay consistent — the patch is sampled from the ring just
    outside the box, so it never announces itself as a white rectangle."""
    img = Image.new("RGB", (200, 100), (222, 216, 200))
    for x in range(180, 200):
        for y in range(0, 20):
            img.putpixel((x, y), (0, 0, 0))
    out = cover(img, "0.9,0,0.1,0.2", _ctx())
    assert out.getpixel((190, 10)) == (222, 216, 200)


def test_cover_accepts_several_regions():
    out = cover(_sheet(), "0.9,0,0.1,0.2;0.75,0.8,0.225,0.1", _ctx())
    assert out.getpixel((190, 10)) == (255, 255, 255)
    assert out.getpixel((190, 85)) == (255, 255, 255)  # second region covered too


def test_cover_leaves_the_rest_of_the_frame_alone():
    """It does not crop: the output keeps the source's dimensions, so a later `bbox=`/`crop=`
    in the chain still addresses the same coordinate space."""
    src = _sheet()
    out = cover(src, "0.9,0,0.1,0.2", _ctx())
    assert out.size == src.size


def test_cover_requires_a_region():
    for bad in (None, ""):
        try:
            cover(_sheet(), bad, _ctx())
        except ValueError:
            continue
        raise AssertionError(f"cover= accepted {bad!r}")
