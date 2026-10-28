"""Fantasy 'Union Identity Card' template (no real emblems, watermarked SPECIMEN).
FIELD_BOXES is the template grid: OCR reads these regions and the layout check measures drift from them."""
import cv2
import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 630
PORTRAIT = (40, 120, 280, 420)  # x0, y0, x1, y1
QR_BOX = (770, 330, 970, 530)
# value boxes (x0, y0, x1, y1); labels sit just above each
FIELD_BOXES = {
    "name": (310, 140, 760, 188),
    "dob": (310, 228, 540, 274),
    "gender": (570, 228, 760, 274),
    "id_number": (310, 314, 740, 360),
    "issue_date": (310, 400, 540, 446),
}
LABELS = {"name": "Name", "dob": "Date of Birth", "gender": "Gender", "id_number": "ID Number",
          "issue_date": "Issued On"}


def _font(size: int):
    return ImageFont.load_default(size=size)


def fit_text(draw: ImageDraw.ImageDraw, text: str, box, start=36):
    size = start
    while size > 16 and draw.textlength(text, font=_font(size)) > box[2] - box[0] - 8:
        size -= 2
    return _font(size)


def draw_value(draw: ImageDraw.ImageDraw, field: str, text: str):
    box = FIELD_BOXES[field]
    f = fit_text(draw, text, box)
    draw.text((box[0] + 4, box[1] + 4), text, fill=(20, 24, 40), font=f)


def fmt_id(n: str) -> str:
    return f"{n[:4]} {n[4:8]} {n[8:12]}"


def render(fields: dict, portrait: Image.Image | None, qr_text: str | None) -> Image.Image:
    """fields: name, dob (dd/mm/yyyy), gender, id_number (12 digits), issue_date."""
    img = Image.new("RGB", (W, H), (236, 241, 247))
    d = ImageDraw.Draw(img)
    # subtle guilloche-like background lines
    for i in range(0, W + H, 14):
        d.line([(i, 0), (i - H, H)], fill=(224, 231, 240), width=1)
    d.rectangle([0, 0, W, 92], fill=(28, 52, 102))
    d.text((40, 20), "UNION IDENTITY AUTHORITY", fill=(255, 255, 255), font=_font(34))
    d.text((40, 60), "National Identity Card  ·  DEMO / FANTASY DOCUMENT", fill=(190, 205, 235), font=_font(18))
    d.rectangle([0, H - 40, W, H], fill=(28, 52, 102))
    d.text((40, H - 32), "Verify the signed QR with the issuer public key", fill=(190, 205, 235), font=_font(18))

    if portrait is not None:
        p = portrait.convert("RGB").resize((PORTRAIT[2] - PORTRAIT[0], PORTRAIT[3] - PORTRAIT[1]))
        img.paste(p, PORTRAIT[:2])
    d.rectangle(PORTRAIT, outline=(28, 52, 102), width=3)

    for k, box in FIELD_BOXES.items():
        d.text((box[0] + 4, box[1] - 24), LABELS[k], fill=(90, 100, 125), font=_font(18))
    vals = dict(fields)
    vals["id_number"] = fmt_id(fields["id_number"])
    vals["gender"] = {"M": "MALE", "F": "FEMALE"}.get(fields["gender"], fields["gender"])
    for k in FIELD_BOXES:
        draw_value(d, k, str(vals[k]).upper() if k == "name" else str(vals[k]))

    if qr_text:
        q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=2, box_size=1)
        q.add_data(qr_text)
        q.make(fit=True)
        side = QR_BOX[2] - QR_BOX[0]
        n = q.modules_count + 4
        q.box_size = max(1, side // n)  # integer module size: no resampling blur, decodes reliably
        qi = q.make_image(fill_color="black", back_color="white").convert("RGB")
        img.paste(qi, (QR_BOX[0] + (side - qi.width) // 2, QR_BOX[1] + (side - qi.height) // 2))

    # SPECIMEN watermark
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    wd.text((330, 470), "SPECIMEN", fill=(200, 40, 40, 70), font=_font(90))
    img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")
    return img


def poisson_edit(card: Image.Image, field: str, new_text: str) -> Image.Image:
    """Seamlessly blend a re-typed field value into the card (the DeepID 'fine edit' attack)."""
    box = FIELD_BOXES[field]
    bg = np.array(card.crop(box)).reshape(-1, 3).astype(int)
    light = bg[bg.sum(1) > 600]
    bg_col = tuple(int(c) for c in np.median(light, axis=0)) if len(light) else (236, 241, 247)
    patch = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), bg_col)
    pd = ImageDraw.Draw(patch)
    f = fit_text(pd, new_text, (0, 0, patch.width, patch.height))
    pd.text((4, 4), new_text, fill=(20, 24, 40), font=f)
    src = cv2.cvtColor(np.array(patch), cv2.COLOR_RGB2BGR)
    dst = cv2.cvtColor(np.array(card), cv2.COLOR_RGB2BGR)
    mask = np.full(src.shape[:2], 255, np.uint8)
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    out = cv2.seamlessClone(src, dst, mask, center, cv2.NORMAL_CLONE)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def splice_portrait(card: Image.Image, face: Image.Image) -> Image.Image:
    out = card.copy()
    p = face.convert("RGB").resize((PORTRAIT[2] - PORTRAIT[0], PORTRAIT[3] - PORTRAIT[1]))
    out.paste(p, PORTRAIT[:2])
    ImageDraw.Draw(out).rectangle(PORTRAIT, outline=(28, 52, 102), width=3)
    return out
