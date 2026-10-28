"""Sample documents for the Kestrel home-loan KYC demo, one folder per test identity, plus fraud samples.

    cd backend && ../.venv/Scripts/python.exe ../clients/kyc-homeloan/tools/make_test_docs.py [--photo me.jpg]

Writes clients/kyc-homeloan/public/test-documents/. Every page says SAMPLE: these are fictional documents for testing
the KYC flow on localhost. The ID cards use TrueID's own card template and issuer key, so their QR verifies. Pass
--photo with a photo of yourself to put your face on the cards, so the live-selfie face match can pass with your webcam.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "test-documents"
sys.path.insert(0, str(HERE.parents[2] / "backend"))

# same people as DEMO_IDENTITIES in clients/*/server.js
PEOPLE = [
    dict(name="Riya Kamat", dob="04/09/1999", gender="F", id_number="234567890124", pan="ABCPK1234Z", address="14 Altinho Road, Panaji, Goa", pin="403001",
         employer="Konkan Software Pvt Ltd", net_pay=68400, bank="Harbour Co-operative Bank", account_no="40021187650", ifsc="HRBR0000412", consumer_no="610233457781"),
    dict(name="Arjun Naik", dob="17/02/1994", gender="M", id_number="345678901238", pan="BNKPN5521K", address="B-302 Sea Breeze, Margao, Goa", pin="403601",
         employer="Mandovi Logistics Ltd", net_pay=54250, bank="Harbour Co-operative Bank", account_no="40021190331", ifsc="HRBR0000415", consumer_no="610245118020"),
    dict(name="Meera Desai", dob="29/11/1988", gender="F", id_number="456789012341", pan="CDQPD7781M", address="7 Hill View Lane, Kothrud, Pune", pin="411038",
         employer="Sahyadri Health Services", net_pay=92300, bank="Western Ghats Bank", account_no="71200034478", ifsc="WGTB0002201", consumer_no="170044582913"),
    dict(name="Karthik Prabhu", dob="08/06/2001", gender="M", id_number="567890123458", pan="DPLPP3304R", address="22 MG Road, Mangaluru, Karnataka", pin="575001",
         employer="Netravati Foods Pvt Ltd", net_pay=38900, bank="Western Ghats Bank", account_no="71200051296", ifsc="WGTB0003117", consumer_no="560078120344"),
]
TODAY = date.today()


def font(size, bold=False):
    for f in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def inr(n: int) -> str:
    s = str(n)
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return (head + "," + tail if head else tail) + ".00"


def page(w=1240, h=1600, title="", color=(15, 118, 110)):
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 120], fill=color)
    d.text((50, 34), title, font=font(40, True), fill="white")
    d.text((w - 330, h - 50), "SAMPLE - FOR TESTING ONLY", font=font(22, True), fill=(200, 40, 40))
    return img, d


def rows(d, items, x=60, y=180, gap=48, size=28):
    for k, v in items:
        d.text((x, y), k, font=font(size), fill=(90, 100, 110))
        d.text((x + 380, y), str(v), font=font(size, True), fill=(20, 30, 40))
        y += gap
    return y


def bill(p, when: date, name=None):
    img, d = page(title="COASTAL POWER DISTRIBUTION LTD")
    d.text((50, 130), "Electricity Bill  -  Low Tension Domestic", font=font(26), fill=(60, 70, 80))
    rows(d, [("Consumer Name", (name or p["name"]).upper()), ("Consumer No", p["consumer_no"]), ("Bill Date", when.strftime("%d/%m/%Y")),
             ("Due Date", (when + timedelta(days=15)).strftime("%d/%m/%Y")), ("Service Address", p["address"]), ("PIN", p["pin"]),
             ("Units Consumed", "212 kWh"), ("Amount Payable", "Rs " + inr(1240))], y=220)
    return img


def slip(p, month: date):
    img, d = page(title=p["employer"].upper(), color=(30, 64, 120))
    d.text((50, 130), f"Payslip for {month.strftime('%B %Y')}", font=font(26), fill=(60, 70, 80))
    gross = round(p["net_pay"] * 1.22)
    rows(d, [("Employee Name", p["name"].upper()), ("Employer", p["employer"]), ("Pay Month", month.strftime("%B %Y")), ("PAN", p["pan"]),
             ("Gross Earnings", "Rs " + inr(gross)), ("Total Deductions", "Rs " + inr(gross - p["net_pay"])), ("Net Pay", "Rs " + inr(p["net_pay"])),
             ("Paid to A/c", "XXXXXX" + p["account_no"][-4:])], y=220)
    return img


def statement(p, month: date):
    img, d = page(title=p["bank"].upper(), color=(70, 50, 120))
    d.text((50, 130), "Statement of Account", font=font(26), fill=(60, 70, 80))
    y = rows(d, [("Account Holder", p["name"].upper()), ("Account Number", p["account_no"]), ("IFSC", p["ifsc"]),
                 ("Period", f"01/{month.strftime('%m/%Y')} - {TODAY.strftime('%d/%m/%Y')}")], y=220)
    y += 30
    d.line([(60, y), (1180, y)], fill=(180, 180, 190), width=2)
    for i, (dt, desc, cr, dr) in enumerate([(month.replace(day=2), "UPI/GROCERY", "", "2,315.00"), (month.replace(day=28), f"NEFT SALARY {p['employer'][:18].upper()}", inr(p["net_pay"]), ""),
                                            (month.replace(day=28) + timedelta(days=3), "ELECTRICITY BILL", "", "1,240.00")]):
        yy = y + 20 + i * 50
        for x, t in ((60, dt.strftime("%d/%m/%Y")), (280, desc), (820, cr), (1010, dr)):
            d.text((x, yy), t, font=font(26), fill=(20, 30, 40))
    return img


def cheque(p):
    img = Image.new("RGB", (1400, 640), (240, 248, 246))
    d = ImageDraw.Draw(img)
    d.text((40, 30), p["bank"].upper(), font=font(40, True), fill=(20, 60, 70))
    d.text((40, 90), f"IFSC: {p['ifsc']}", font=font(28), fill=(20, 30, 40))
    d.text((40, 200), "Pay ____________________________________________", font=font(28), fill=(80, 90, 100))
    d.text((40, 300), f"A/c No. {p['account_no']}", font=font(32, True), fill=(20, 30, 40))
    d.text((900, 420), p["name"].upper(), font=font(30, True), fill=(20, 30, 40))
    d.line([(60, 560), (1340, 120)], fill=(200, 40, 40), width=8)
    d.text((520, 330), "CANCELLED", font=font(70, True), fill=(200, 40, 40))
    d.text((1000, 600), "SAMPLE - FOR TESTING ONLY", font=font(20, True), fill=(200, 40, 40))
    return img


def id_card(p, portrait):
    from app.modules.document import card, qr_sign
    issue = "15/03/2019"
    qr = qr_sign.make_qr_text({"n": p["name"].upper(), "d": p["dob"], "g": p["gender"], "id": p["id_number"], "i": issue})
    return card.render({"name": p["name"].upper(), "dob": p["dob"], "gender": p["gender"], "id_number": p["id_number"], "issue_date": issue}, portrait, qr)


def save(img, path: Path, software=None, ai=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".png":
        info = PngImagePlugin.PngInfo()
        if ai:
            info.add_text("DigitalSourceType", "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia")
        if software:
            info.add_text("Software", software)
        img.save(path, pnginfo=info)
    else:
        exif = Image.Exif()
        if software:
            exif[305] = software
        img.save(path, quality=92, exif=exif)


def index(folder: Path, title: str, items: list[tuple[str, str]]):
    li = "".join(f'<li><a href="{f}" download>{f}</a> - {desc}</li>' for f, desc in items)
    (folder / "index.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>body{{font:15px/1.6 Inter,Segoe UI,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#13202a}}a{{color:#0f766e}}</style>
<h1>{title}</h1><p>Sample documents for testing the Kestrel KYC flow on localhost. Download a file, then upload it at the matching step.</p><ul>{li}</ul>
<p><a href="../">All test documents</a></p>""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", help="a photo of your face for the ID cards (so the live selfie matches)")
    a = ap.parse_args()
    portrait = Image.open(a.photo) if a.photo else None
    last_month = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    people = []
    for p in PEOPLE:
        slug = p["name"].lower().replace(" ", "-")
        f = OUT / slug
        save(id_card(p, portrait), f / "id-card.png")
        save(bill(p, TODAY - timedelta(days=12)), f / "electricity-bill.jpg")
        save(slip(p, last_month), f / "salary-slip.jpg")
        save(statement(p, last_month), f / "bank-statement.jpg")
        save(cheque(p), f / "cancelled-cheque.jpg")
        index(f, p["name"], [("id-card.png", "ID card with an issuer-signed QR"), ("electricity-bill.jpg", f"bill dated {(TODAY - timedelta(days=12)).strftime('%d/%m/%Y')}"),
                             ("salary-slip.jpg", f"payslip for {last_month.strftime('%B %Y')}"), ("bank-statement.jpg", "statement with the salary credit"),
                             ("cancelled-cheque.jpg", "cheque for the same account")])
        people.append((slug, p["name"]))

    r = PEOPLE[0]
    fr = OUT / "fraud-samples"
    save(bill(r, TODAY - timedelta(days=140)), fr / "old-bill-riya.jpg")
    save(bill(r, TODAY - timedelta(days=10), name="Suresh Kamat"), fr / "bill-other-name-riya.jpg")
    save(slip(r, last_month), fr / "edited-slip-riya.jpg", software="Adobe Photoshop 25.1")
    save(statement(r, last_month), fr / "ai-generated-statement-riya.png", ai=True)
    index(fr, "Fraud samples", [
        ("old-bill-riya.jpg", "Riya's bill, 140 days old: fails the RBI 2-month rule"),
        ("bill-other-name-riya.jpg", "bill in another person's name: name check fails unless you declare the relationship"),
        ("edited-slip-riya.jpg", "Riya's slip saved by Photoshop: editing-software check fails"),
        ("ai-generated-statement-riya.png", "statement carrying an AI-generator marker: AI check fails"),
        ("../riya-kamat/electricity-bill.jpg", "use Riya's bill while applying as Arjun: re-use check fails"),
    ])
    (OUT / "index.html").write_text("""<!doctype html><meta charset="utf-8"><title>Test documents</title>
<style>body{font:15px/1.6 Inter,Segoe UI,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#13202a}a{color:#0f766e}</style>
<h1>Test documents</h1><p>Fictional sample documents for the Kestrel home-loan KYC demo.</p><ul>"""
        + "".join(f'<li><a href="{s}/">{n}</a></li>' for s, n in people) + '<li><a href="fraud-samples/">Fraud samples</a></li></ul>',
        encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
