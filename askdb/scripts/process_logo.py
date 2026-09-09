"""Strip white backgrounds and export NQL Insight brand assets from the supplied logo."""

from __future__ import annotations

import base64
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image, ImageEnhance

SRC = Path(
    r"C:\Users\HP\.cursor\projects\e-ai-data-rag-ai-data-v2\assets"
    r"\c__Users_HP_AppData_Roaming_Cursor_User_workspaceStorage_"
    r"379afc90e68402030eba66cba2c5b8df_images_Gemini_Generated_Image_"
    r"gnh91ognh91ognh9-e9085218-212e-41f7-8982-a4455c70c28a.png"
)
OUT = Path(r"E:\ai_data_rag\ai_data_v2\askdb\apps\web\public\brand")
PUBLIC = Path(r"E:\ai_data_rag\ai_data_v2\askdb\apps\web\public")


def strip_paper(img: Image.Image) -> Image.Image:
    """Remove white / light-gray paper so the mark sits on any theme."""
    img = img.convert("RGBA")
    px = img.load()
    assert px is not None
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            mx = max(r, g, b)
            mn = min(r, g, b)
            chroma = mx - mn
            # Flat paper: high luminance, low chroma
            if mx >= 250 and chroma < 18:
                px[x, y] = (r, g, b, 0)
            elif mx >= 220 and chroma < 22:
                t = (mx - 220) / 35
                px[x, y] = (r, g, b, int(a * (1 - t)))
            elif mx >= 200 and chroma < 16 and (r + g + b) / 3 > 205:
                t = ((r + g + b) / 3 - 200) / 55
                px[x, y] = (r, g, b, int(max(0, a * (1 - min(1, t)))))
    return img


def crop_content(img: Image.Image, pad: int = 8) -> Image.Image:
    bbox = img.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    return img.crop(
        (max(0, l - pad), max(0, t - pad), min(img.size[0], r + pad), min(img.size[1], b + pad))
    )


def extract_brain(full: Image.Image) -> Image.Image:
    w, h = full.size
    brain = crop_content(full.crop((0, 0, w, int(h * 0.52))), pad=4)
    side = max(brain.size) + 28
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(brain, ((side - brain.size[0]) // 2, (side - brain.size[1]) // 2), brain)
    return canvas


def brighten_for_dark(img: Image.Image) -> Image.Image:
    """Lift dark emerald/navy strokes so they read on charcoal UI — same art, not redrawn."""
    out = img.copy()
    px = out.load()
    assert px is not None
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 16:
                continue
            # Skip residual light fluff
            if r > 200 and g > 200 and b > 200:
                px[x, y] = (r, g, b, 0)
                continue
            # Boost luminance while preserving hue lean (green left / blue right)
            factor = 1.55
            nr = min(255, int(r * factor + 28))
            ng = min(255, int(g * factor + 36))
            nb = min(255, int(b * factor + 48))
            # Push right-side cooler blues toward cyan for pop on dark
            if x > w * 0.48 and b >= g:
                nb = min(255, nb + 40)
                ng = min(255, ng + 18)
            if x <= w * 0.52 and g >= b:
                ng = min(255, ng + 28)
                nr = min(255, int(nr * 0.92))
            px[x, y] = (nr, ng, nb, a)
    # Slight clarity
    rgb = out.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(out.getchannel("A"))
    return rgba


def navy_text_to_light(img: Image.Image) -> Image.Image:
    out = img.copy()
    px = out.load()
    assert px is not None
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 20:
                continue
            if r < 55 and g < 55 and b < 85 and abs(r - g) < 28:
                px[x, y] = (226, 232, 240, a)
    return out


def write_svg_mark(png_path: Path, svg_path: Path, size: int = 256) -> None:
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    svg_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="NQL Insight">
  <title>NQL Insight</title>
  <image href="data:image/png;base64,{b64}" width="{size}" height="{size}" preserveAspectRatio="xMidYMid meet"/>
</svg>
""",
        encoding="utf-8",
    )


def write_wordmark_svg(path: Path, *, dark: bool) -> None:
    primary = "#E8EEF7" if dark else "#0B1F3A"
    accent = "#22D3EE" if dark else "#0E7490"
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="220" height="36" viewBox="0 0 220 36" role="img" aria-label="NQL Insight">
  <text x="0" y="26" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="22" font-weight="700" letter-spacing="-0.02em" fill="{primary}">NQL</text>
  <text x="58" y="26" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="22" font-weight="500" letter-spacing="-0.02em" fill="{accent}">Insight</text>
</svg>
""",
        encoding="utf-8",
    )


def save_ico(icon512: Image.Image, dest: Path) -> None:
    sizes = [(16, 16), (32, 32), (48, 48)]
    frames = [icon512.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    frames[1].save(dest, format="ICO", sizes=sizes, append_images=[frames[0], frames[2]])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    full = crop_content(strip_paper(Image.open(SRC)))
    full.save(OUT / "logo-source-transparent.png", "PNG")
    full.save(OUT / "logo-lockup-light.png", "PNG")
    navy_text_to_light(full).save(OUT / "logo-lockup-dark.png", "PNG")

    brain = extract_brain(full)
    brain = strip_paper(brain)

    mark_light = brain.resize((256, 256), Image.Resampling.LANCZOS)
    mark_dark = brighten_for_dark(brain).resize((256, 256), Image.Resampling.LANCZOS)
    mark_light.save(OUT / "logo-mark.png", "PNG")
    mark_dark.save(OUT / "logo-mark-dark.png", "PNG")
    write_svg_mark(OUT / "logo-mark.png", OUT / "logo-mark.svg")
    write_svg_mark(OUT / "logo-mark-dark.png", OUT / "logo-mark-dark.svg")
    write_svg_mark(OUT / "logo-mark.png", OUT / "logo-loading.svg")

    icon512 = brain.resize((512, 512), Image.Resampling.LANCZOS)
    icon512.save(OUT / "icon.png", "PNG")
    icon512.resize((180, 180), Image.Resampling.LANCZOS).save(OUT / "apple-touch-icon.png", "PNG")
    icon512.resize((32, 32), Image.Resampling.LANCZOS).save(OUT / "favicon-32.png", "PNG")
    save_ico(icon512, OUT / "favicon.ico")
    shutil.copy2(OUT / "favicon.ico", PUBLIC / "favicon.ico")
    shutil.copy2(OUT / "apple-touch-icon.png", PUBLIC / "apple-touch-icon.png")

    write_wordmark_svg(OUT / "logo-wordmark.svg", dark=False)
    write_wordmark_svg(OUT / "logo-wordmark-dark.svg", dark=True)

    # Quick QC
    px = mark_light.load()
    assert px is not None
    samples = [
        px[x, y]
        for y in range(0, 256, 8)
        for x in range(0, 256, 8)
        if px[x, y][3] > 200
    ]
    print("Wrote", OUT)
    print("opaque sample top", Counter((c[0] // 16 * 16, c[1] // 16 * 16, c[2] // 16 * 16) for c in samples).most_common(5))


if __name__ == "__main__":
    main()
