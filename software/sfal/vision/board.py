"""Foto sintética de uma placa (PCBA) depois da refusão, para a inspeção óptica.

Faz o papel da câmera enquanto não há uma: o simulador pede a foto da unidade e, se ela tem defeito de solda,
o defeito aparece na imagem. Com hardware, a foto vem de uma câmera de verdade e este módulo não é usado.

Cada placa tem um CI com terminais dos dois lados e alguns componentes passivos. Defeitos de solda desenhados:
  ponte      solda unindo dois terminais vizinhos do CI
  ausente    terminal ou ilha sem solda (cobre exposto, sem o brilho da junta)
  excesso    bola grande de solda sobre uma junta
A posição dos componentes, a iluminação e o ruído variam de placa para placa (semente = número de série).
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

W, H = 512, 384
DEFECT_KINDS = ("ponte", "ausente", "excesso")
GREEN = (22, 96, 58)
SILK = (225, 232, 225)
COPPER = (176, 112, 52)
SOLDER = (206, 210, 214)
SOLDER_HI = (246, 248, 250)
BODY = (28, 28, 32)


@dataclass
class Photo:
    jpeg: bytes
    defect: str | None      # tipo de defeito desenhado, ou None
    where: str | None       # onde, em palavras (para conferência humana)
    x: float | None = None  # centro do defeito na foto, de 0 a 1 (gabarito de posição para o treino)
    y: float | None = None


def _joint(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float) -> None:
    """Junta boa: ilha de cobre coberta por solda brilhante."""
    d.rectangle([x - w / 2 - 1, y - h / 2 - 1, x + w / 2 + 1, y + h / 2 + 1], fill=COPPER)
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=2, fill=SOLDER)
    d.ellipse([x - w / 4, y - h / 4, x + w / 8, y + h / 8], fill=SOLDER_HI)


def _bare(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float) -> None:
    """Ilha sem solda: só o cobre, fosco."""
    d.rectangle([x - w / 2 - 1, y - h / 2 - 1, x + w / 2 + 1, y + h / 2 + 1], fill=COPPER)
    d.rectangle([x - w / 2 + 2, y - h / 2 + 2, x + w / 2 - 2, y + h / 2 - 2], fill=(150, 92, 40))


def render(serial: int, defect: bool, kind: str | None = None) -> Photo:
    rng = random.Random(serial * 7919 + (1 if defect else 0))
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)

    # trilhas e furos, só para a placa não ser um fundo liso
    for _ in range(14):
        x0, y0 = rng.randint(10, W - 10), rng.randint(10, H - 10)
        horiz = rng.random() < 0.5
        x1, y1 = (x0 + rng.randint(-160, 160), y0) if horiz else (x0, y0 + rng.randint(-120, 120))
        d.line([x0, y0, x1, y1], fill=(30, 118, 72), width=3)
    for cx, cy in ((18, 18), (W - 18, 18), (18, H - 18), (W - 18, H - 18)):
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(200, 170, 90))
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(15, 20, 15))

    # CI central com terminais em cima e embaixo
    pins = 8
    ic_w, ic_h = 208, 78
    ix, iy = W // 2 - ic_w // 2 + rng.randint(-24, 24), H // 2 - ic_h // 2 + rng.randint(-30, 10)
    pitch = ic_w / pins
    joints: list[tuple[float, float, float, float, str]] = []
    for i in range(pins):
        px = ix + pitch * (i + 0.5)
        joints.append((px, iy - 13, 13, 20, f"terminal {i + 1} da fileira de cima do CI"))
        joints.append((px, iy + ic_h + 13, 13, 20, f"terminal {i + 1} da fileira de baixo do CI"))
    d.rectangle([ix, iy, ix + ic_w, iy + ic_h], fill=BODY)
    d.ellipse([ix + 8, iy + 8, ix + 20, iy + 20], fill=(70, 70, 76))
    d.text((ix + 40, iy + ic_h / 2 - 6), f"U1  SFAL-{serial % 10000:04d}", fill=(150, 150, 156))

    # passivos (resistores/capacitores) com duas ilhas cada
    spots = [(70, 70), (190, 60), (330, 58), (440, 80), (64, 300), (180, 318), (330, 322), (446, 300)]
    rng.shuffle(spots)
    for n, (cx, cy) in enumerate(spots[: rng.randint(5, 7)]):
        cx += rng.randint(-10, 10)
        cy += rng.randint(-8, 8)
        joints.append((cx - 17, cy, 13, 18, f"ilha esquerda do componente R{n + 1}"))
        joints.append((cx + 17, cy, 13, 18, f"ilha direita do componente R{n + 1}"))
        d.rectangle([cx - 11, cy - 8, cx + 11, cy + 8], fill=(46, 40, 34) if n % 2 else (150, 120, 84))
        d.text((cx - 9, cy - 24), f"R{n + 1}", fill=SILK)

    kind = (kind or rng.choice(DEFECT_KINDS)) if defect else None
    where = None
    cx = cy = None
    bad = rng.randrange(len(joints))
    if kind == "ponte":
        bad = rng.randrange(0, (pins - 1) * 2)       # precisa de um vizinho na mesma fileira do CI
    for j, (x, y, w, h, name) in enumerate(joints):
        if kind == "ausente" and j == bad:
            _bare(d, x, y, w, h)
            where = name
            cx, cy = x, y
        else:
            _joint(d, x, y, w, h)
    if kind == "ponte":
        x, y, w, h, name = joints[bad]
        x2 = joints[bad + 2][0]
        d.rounded_rectangle([x - w / 2, y - 6, x2 + w / 2, y + 6], radius=5, fill=SOLDER)
        d.ellipse([(x + x2) / 2 - 8, y - 4, (x + x2) / 2 + 3, y + 2], fill=SOLDER_HI)
        where = f"ponte entre o {name} e o vizinho"
        cx, cy = (x + x2) / 2, y
    elif kind == "excesso":
        x, y, w, h, name = joints[bad]
        d.ellipse([x - 15, y - 15, x + 15, y + 15], fill=SOLDER)
        d.ellipse([x - 9, y - 10, x - 1, y - 2], fill=SOLDER_HI)
        where = name
        cx, cy = x, y

    # câmera: leve desfoque, variação de luz e ruído
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    gain = rng.uniform(0.9, 1.08)
    px = img.load()
    for _ in range(2500):
        x, y = rng.randrange(W), rng.randrange(H)
        r, g, b = px[x, y]
        n = rng.randint(-14, 14)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    img = img.point(lambda v: max(0, min(255, int(v * gain))))
    if rng.random() < 0.5:
        img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, fillcolor=GREEN)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return Photo(out.getvalue(), kind, where, None if cx is None else cx / W, None if cy is None else cy / H)
