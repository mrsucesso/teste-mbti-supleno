#!/usr/bin/env python3
"""Gera as imagens Open Graph oficiais do Testes Supleno."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "og"
W, H = 1200, 630

GREEN_950 = "#153126"
GREEN_900 = "#1F4033"
GREEN_700 = "#3C6E52"
GREEN_500 = "#5C9A78"
GREEN_100 = "#EAF3EC"
PAPER = "#FBFAF7"
INK = "#24302A"
LINE = "#C6D9CA"
FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
REGULAR = FONT_DIR / "LiberationSerif-Regular.ttf"
BOLD = FONT_DIR / "LiberationSerif-Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD if bold else REGULAR
    if not path.is_file():
        raise FileNotFoundError(f"Fonte necessária não encontrada: {path}")
    return ImageFont.truetype(str(path), size)


def rounded_paste(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int], radius: int = 36) -> None:
    x1, y1, x2, y2 = box
    fitted = ImageOps.fit(image.convert("RGB"), (x2 - x1, y2 - y1), Image.Resampling.LANCZOS)
    mask = Image.new("L", fitted.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fitted.width, fitted.height), radius=radius, fill=255)
    base.paste(fitted, (x1, y1), mask)


def draw_base(title: str, subtitle: str, kicker: str, meta: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), GREEN_950)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 42, 1158, 588), radius=34, fill=GREEN_900, outline=GREEN_700, width=2)
    draw.text((78, 78), kicker.upper(), font=font(22, True), fill=GREEN_100)
    draw.line((78, 116, 232, 116), fill=GREEN_500, width=4)

    title_font = font(61, True)
    lines = title.split("\n")
    y = 154
    for line in lines:
        draw.text((78, y), line, font=title_font, fill=PAPER)
        y += 68

    subtitle_font = font(27)
    for line in subtitle.split("\n"):
        draw.text((80, y + 12), line, font=subtitle_font, fill=GREEN_100)
        y += 34

    draw.rounded_rectangle((78, 493, 560, 548), radius=27, fill=GREEN_100)
    draw.text((104, 507), meta, font=font(20, True), fill=GREEN_950)
    return image, draw


def draw_portal() -> Image.Image:
    image, _ = draw_base(
        "Você não cabe\nem um rótulo.",
        "Três testes. Três olhares.\nUma conversa mais clara com você.",
        "Testes Supleno",
        "77 perguntas  ·  resultado imediato",
    )
    artwork = Image.open(ROOT / "assets" / "illustrations" / "portal-atlas.webp")
    rounded_paste(image, artwork, (650, 72, 1128, 558), 38)
    return image


def draw_tipos() -> Image.Image:
    image, draw = draw_base(
        "Supleno Tipos",
        "Preferências de percepção, decisão,\ninteração e organização.",
        "Autoconhecimento Supleno",
        "28 perguntas  ·  16 tipos",
    )
    cx, cy = 890, 310
    draw.ellipse((710, 130, 1070, 490), fill=GREEN_100, outline=GREEN_500, width=5)
    draw.polygon([(cx, 165), (1035, cy), (cx, 455), (745, cy)], fill=GREEN_700)
    draw.ellipse((825, 245, 955, 375), fill=PAPER)
    for angle_point in ((890, 185), (1015, 310), (890, 435), (765, 310)):
        x, y = angle_point
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=GREEN_950)
    draw.line((765, 310, 1015, 310), fill=PAPER, width=5)
    draw.line((890, 185, 890, 435), fill=PAPER, width=5)
    return image


def draw_estilos() -> Image.Image:
    image, draw = draw_base(
        "Supleno Estilos",
        "Quatro maneiras de agir, decidir\ne interagir no momento atual.",
        "Autoconhecimento Supleno",
        "24 perguntas  ·  4 estilos",
    )
    boxes = [(700, 145, 870, 305), (900, 145, 1070, 305), (700, 335, 870, 495), (900, 335, 1070, 495)]
    fills = (GREEN_100, GREEN_500, GREEN_700, PAPER)
    for i, (box, fill) in enumerate(zip(boxes, fills), 1):
        draw.rounded_rectangle(box, radius=30, fill=fill, outline=LINE, width=3)
        x1, y1, x2, y2 = box
        text_fill = GREEN_950 if fill in (GREEN_100, GREEN_500, PAPER) else PAPER
        label = str(i)
        bbox = draw.textbbox((0, 0), label, font=font(54, True))
        draw.text(((x1 + x2 - (bbox[2] - bbox[0])) / 2, (y1 + y2 - (bbox[3] - bbox[1])) / 2 - 8), label, font=font(54, True), fill=text_fill)
    return image


def draw_tracos() -> Image.Image:
    image, draw = draw_base(
        "Supleno Traços",
        "Cinco dimensões contínuas para\nobservar tendências sem rótulos.",
        "Autoconhecimento Supleno",
        "25 afirmações  ·  5 dimensões",
    )
    heights = (170, 275, 215, 330, 245)
    x = 700
    for idx, height in enumerate(heights):
        left = x + idx * 82
        draw.rounded_rectangle((left, 500 - height, left + 46, 500), radius=23, fill=GREEN_100, outline=GREEN_500, width=3)
        knob_y = 500 - height + 34
        draw.ellipse((left + 7, knob_y - 16, left + 39, knob_y + 16), fill=GREEN_700)
    draw.line((680, 500, 1120, 500), fill=GREEN_500, width=4)
    return image


def draw_mapa() -> Image.Image:
    image, draw = draw_base(
        "Mapa Integrado",
        "Tipos, Estilos e Traços reunidos\nem uma leitura educativa.",
        "Testes Supleno",
        "3 resultados  ·  leitura local",
    )
    circles = [(820, 280, GREEN_500), (960, 280, GREEN_700), (890, 395, GREEN_100)]
    for cx, cy, color in circles:
        draw.ellipse((cx - 125, cy - 125, cx + 125, cy + 125), fill=color, outline=PAPER, width=5)
    draw.ellipse((850, 275, 930, 355), fill=GREEN_950, outline=PAPER, width=4)
    for x, y in ((820, 280), (960, 280), (890, 395)):
        draw.line((890, 315, x, y), fill=PAPER, width=4)
    return image


def save(name: str, image: Image.Image) -> None:
    target = OUT / f"{name}.jpg"
    image.save(target, "JPEG", quality=90, optimize=True, progressive=True, subsampling=1)
    print(f"{target.relative_to(ROOT)} {image.size} {target.stat().st_size} bytes")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generators = {
        "portal": draw_portal,
        "tipos": draw_tipos,
        "estilos": draw_estilos,
        "tracos": draw_tracos,
        "mapa": draw_mapa,
    }
    for name, generator in generators.items():
        save(name, generator())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
