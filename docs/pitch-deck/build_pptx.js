// TrueID Shield — PS3 pitch deck as a native, editable PowerPoint (structured: theme + layouts + sections).
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");
const { applyTheme } = require(process.env.SKILL_DIR + "/scripts/apply_theme.js");

const OUT = process.argv[2];
const THEME = {
  name: "TrueID Evidence Desk",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14161A", lt1: "FBFBF8", dk2: "4A4F59", lt2: "F2F3EF",
    accent1: "2B3BE6", accent2: "0F7B52", accent3: "B4690E", accent4: "C8361F", accent5: "A9B1FF", accent6: "3FB984",
    hlink: "2B3BE6", folHlink: "1E2BB3",
  },
};
const H = THEME.colors; // hex, only where pptxgenjs needs hex (shadows, chart colors, gridlines)
const INK2 = "1E2026", LINE_DARK = "33363E", MUTED_DARK = "BFC3CC", MUTED = "6E7380", CARD_LINE = "E3E4DF";

async function icon(name, color, size = 256) {
  const Comp = lu[name] || lu.LuCircle;
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
const shadow = () => ({ type: "outer", color: "14161A", opacity: 0.08, blur: 8, offset: 2, angle: 90 });

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  pres.title = "TrueID Shield — PS3 Pitch";
  pres.subject = "Synthetic identity fraud detection in automated KYC";
  pres.author = "TrueID Shield team";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------- layouts ----------
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.75, y: 2.3, w: 8.6, h: 1.3, fontSize: 60, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.75, y: 3.7, w: 8.2, h: 0.8, fontSize: 24, color: "C9CCD3", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  const contentLayout = (name, dark) => pres.defineSlideMaster({
    title: name,
    background: { color: dark ? C.text1 : C.background2 },
    margin: [0.5, 0.75, 0.6, 0.75],
    slideNumber: { x: 12.08, y: 6.95, w: 0.5, h: 0.3, fontSize: 10, color: dark ? "8A8F99" : MUTED, align: "right" },
    objects: [
      { text: { text: "TrueID Shield", options: { x: 0.75, y: 6.95, w: 4, h: 0.3, fontSize: 10, color: dark ? "8A8F99" : MUTED, margin: 0 } } },
      { placeholder: { options: { name: "kicker", type: "body", x: 0.75, y: 0.5, w: 9, h: 0.35, fontSize: 12, bold: true, charSpacing: 3, color: dark ? C.accent5 : C.accent1, margin: 0, valign: "middle" }, text: "" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.75, y: 0.88, w: 11.83, h: 0.8, fontSize: 32, bold: true, color: dark ? C.background1 : C.text1, margin: 0, valign: "middle", align: "left" }, text: "" } },
    ],
  });
  contentLayout("CONTENT_LIGHT", false);
  contentLayout("CONTENT_DARK", true);

  const head = (slide, kicker, title) => {
    slide.addText(kicker.toUpperCase(), { placeholder: "kicker" });
    slide.addText(title, { placeholder: "title" });
  };
  const iconCircle = async (slide, x, y, d, iconName, fill, fg, name) => {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: name + " circle" });
    const p = d * 0.56;
    slide.addImage({ data: await icon(iconName, fg), x: x + (d - p) / 2, y: y + (d - p) / 2, w: p, h: p, altText: "", objectName: name + " icon" });
  };
  const stamp = (slide, x, y, w, h, size, name) => slide.addText("13 / 13 CHECKS", {
    x, y, w, h, fontSize: size, bold: true, charSpacing: 2, color: C.accent6, align: "center", valign: "middle",
    fontFace: THEME.headFontFace, line: { color: H.accent6, width: 3 }, rectRadius: 0.1, shape: pres.shapes.ROUNDED_RECTANGLE,
    rotate: -6, isTextBox: true, objectName: name, margin: 0,
  });

  // ---------- 1. cover ----------
  pres.addSection({ title: "The problem" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "The problem" });
  s.addShape(pres.shapes.OVAL, { x: 8.6, y: -1.2, w: 6.4, h: 6.4, fill: { color: C.accent1, transparency: 72 }, line: { type: "none" }, objectName: "glow" });
  s.addText("HACKSPLOIT 2026 · PROBLEM STATEMENT 3", { x: 0.75, y: 1.75, w: 8, h: 0.4, fontSize: 14, bold: true, charSpacing: 3, color: C.accent5, margin: 0, isTextBox: true, objectName: "kicker" });
  s.addText("TrueID Shield", { placeholder: "title" });
  s.addText("Detecting synthetic identity fraud in automated KYC", { placeholder: "body" });
  s.addText("Trust no single check.", { x: 0.75, y: 4.75, w: 3.9, h: 0.6, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.3, fill: { color: C.accent1 }, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle", isTextBox: true, objectName: "tagline", margin: 0 });
  stamp(s, 9.3, 2.75, 3.1, 0.85, 24, "verdict stamp");
  s.addText("NIT Goa · October 2026", { x: 0.75, y: 6.85, w: 6, h: 0.35, fontSize: 12, color: "8A8F99", margin: 0, isTextBox: true, objectName: "footer" });
  s.addNotes("TrueID Shield answers PS3: synthetic identity fraud in automated KYC. One idea runs through the whole system: trust no single check. A case is approved only when every required check passes.");

  // ---------- 2. problem ----------
  s = pres.addSlide({ masterName: "CONTENT_LIGHT", sectionTitle: "The problem" });
  head(s, "The problem", "A synthetic identity passes every check on its own");
  s.addText([
    { text: "PS3: ", options: { bold: true, color: C.text1 } },
    { text: "detect identities that are part real, part invented, in automated KYC, where no person ever looks at the documents." },
  ], { x: 0.75, y: 1.85, w: 11, h: 0.7, fontSize: 18, color: C.text2, margin: 0, isTextBox: true, objectName: "definition" });
  const probCards = [
    ["Real + invented", "A valid ID number, a real-looking card, a face that matches its own photo.", "LuFingerprint"],
    ["Cheap to make", "Image generators and deepfakes produce cards and selfies on demand.", "LuSparkles"],
    ["Built to scale", "Rings and mule accounts reuse faces, devices and phones across banks.", "LuNetwork"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.75 + i * (3.677 + 0.4), y = 2.95;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.677, h: 3.4, rectRadius: 0.15, fill: { color: C.background1 }, line: { color: CARD_LINE, width: 1 }, shadow: shadow(), objectName: `card ${i + 1}` });
    await iconCircle(s, x + 0.4, y + 0.4, 0.75, probCards[i][2], H.accent1, H.lt1, `card ${i + 1}`);
    s.addText(probCards[i][0], { x: x + 0.4, y: y + 1.4, w: 2.9, h: 0.5, fontSize: 22, bold: true, color: C.text1, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, objectName: `card ${i + 1} title` });
    s.addText(probCards[i][1], { x: x + 0.4, y: y + 2.0, w: 2.9, h: 1.1, fontSize: 16, color: C.text2, valign: "top", margin: 0, isTextBox: true, objectName: `card ${i + 1} body` });
  }
  s.addNotes("Each check alone can be beaten: the document looks right, the face matches its own photo, the ID number is valid. What a fraudster can't easily do is stay consistent across every source at once. That is the gap PS3 asks us to close.");

  // ---------- 3. hierarchy ----------
  s = pres.addSlide({ masterName: "CONTENT_LIGHT", sectionTitle: "The problem" });
  head(s, "The problem, broken down", "Three ways a fake identity gets through");
  s.addText("Synthetic identity fraud in automated KYC", { x: 3.667, y: 1.9, w: 6, h: 0.62, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, fill: { color: C.text1 }, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", isTextBox: true, objectName: "root", margin: 0 });
  const lineOpts = (arrow) => ({ line: { color: "8A8F99", width: 2, ...(arrow ? { endArrowType: "triangle" } : {}) } });
  s.addShape(pres.shapes.LINE, { x: 6.667, y: 2.52, w: 0, h: 0.28, ...lineOpts(false), objectName: "trunk" });
  s.addShape(pres.shapes.LINE, { x: 2.589, y: 2.8, w: 8.156, h: 0, ...lineOpts(false), objectName: "branch bar" });
  const branches = [
    ["01", "Forged identity", ["AI-made or edited ID card", "Real ID number, someone else’s face"], "Issuer-signed QR and the issuer’s own photo", H.accent4],
    ["02", "Faked presence", ["Deepfake or replayed selfie", "Bots filling in the form"], "Head-turn liveness, AI-provenance and typing rhythm", H.accent3],
    ["03", "Fraud at scale", ["Rings sharing a face, device or phone", "One ID used at several banks"], "Identity graph and a hashed bank network", H.accent1],
  ];
  for (let i = 0; i < 3; i++) {
    const [num, title, leaves, answer, col] = branches[i];
    const x = 0.75 + i * (3.677 + 0.4), y = 3.1, cx = x + 3.677 / 2;
    s.addShape(pres.shapes.LINE, { x: cx, y: 2.8, w: 0, h: 0.28, ...lineOpts(true), objectName: `branch ${i + 1} arrow` });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.677, h: 3.6, rectRadius: 0.15, fill: { color: C.background1 }, line: { color: CARD_LINE, width: 1 }, shadow: shadow(), objectName: `branch ${i + 1}` });
    s.addText(num, { x: x + 0.35, y: y + 0.35, w: 0.6, h: 0.6, shape: pres.shapes.OVAL, fill: { color: col }, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle", isTextBox: true, margin: 0, objectName: `branch ${i + 1} number` });
    s.addText(title, { x: x + 1.1, y: y + 0.35, w: 2.4, h: 0.6, fontSize: 20, bold: true, color: C.text1, fontFace: THEME.headFontFace, valign: "middle", margin: 0, isTextBox: true, objectName: `branch ${i + 1} title` });
    s.addText(leaves.map((t, k) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: k < leaves.length - 1 } })),
      { x: x + 0.35, y: y + 1.15, w: 3.0, h: 1.0, fontSize: 15, color: C.text2, valign: "top", paraSpaceAfter: 4, margin: 0, isTextBox: true, objectName: `branch ${i + 1} threats` });
    s.addShape(pres.shapes.LINE, { x: x + 0.35, y: y + 2.3, w: 2.98, h: 0, line: { color: CARD_LINE, width: 1 }, objectName: `branch ${i + 1} divider` });
    s.addText("OUR ANSWER", { x: x + 0.35, y: y + 2.42, w: 3.0, h: 0.3, fontSize: 11, bold: true, charSpacing: 2, color: C.accent1, margin: 0, isTextBox: true, objectName: `branch ${i + 1} label` });
    s.addText(answer, { x: x + 0.35, y: y + 2.75, w: 3.0, h: 0.7, fontSize: 15, bold: true, color: C.text1, valign: "top", margin: 0, isTextBox: true, objectName: `branch ${i + 1} answer` });
  }
  s.addNotes("Top level: synthetic identity fraud. It gets through in three ways. A forged identity: an AI-made or edited card, or a real ID with someone else's face; we trust the issuer's signed QR and the issuer's photo, not the pixels. Faked presence: deepfakes, replayed selfies, bots; we use a server-issued head-turn challenge, C2PA AI-provenance and typing rhythm. Fraud at scale: rings and repeat use across banks; we link applications in an identity graph and share keyed hashes between banks.");

  // ---------- 4. pipeline ----------
  pres.addSection({ title: "The solution" });
  s = pres.addSlide({ masterName: "CONTENT_LIGHT", sectionTitle: "The solution" });
  head(s, "End-to-end pipeline", "From upload to decision in one pass");
  const W = (11.833 - 4 * 0.4) / 5, top = 1.95, hgt = 4.45;
  const stages = [
    ["01", "Capture", ["Form and typing rhythm", "ID card photo", "Selfie and head-turn video burst", "Consent and geo-tag"]],
    ["02", "Check", null],
    ["03", "Fuse", ["A model ranks the risk", "SHAP shows why", "A genuine-only profile flags unseen fraud"]],
    ["04", "Decide", null],
    ["05", "Explain", ["Analyst console and audit trail", "Ask TrueID answers from data", "Learning loop proposes, analyst approves", "Applicant gets fixable tips"]],
  ];
  for (let i = 0; i < 5; i++) {
    const x = 0.75 + i * (W + 0.4), dark = i === 3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: top, w: W, h: hgt, rectRadius: 0.15, fill: { color: dark ? C.text1 : C.background1 }, line: dark ? { type: "none" } : { color: CARD_LINE, width: 1 }, shadow: shadow(), objectName: `stage ${i + 1}` });
    s.addText(stages[i][0], { x: x + 0.25, y: top + 0.25, w: 1, h: 0.3, fontSize: 12, bold: true, color: dark ? C.accent5 : C.accent1, margin: 0, isTextBox: true, objectName: `stage ${i + 1} number` });
    s.addText(stages[i][1], { x: x + 0.25, y: top + 0.55, w: W - 0.5, h: 0.5, fontSize: 22, bold: true, color: dark ? C.background1 : C.text1, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, objectName: `stage ${i + 1} title` });
    if (stages[i][2]) {
      const items = stages[i][2];
      s.addText(items.map((t, k) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: k < items.length - 1 } })),
        { x: x + 0.25, y: top + 1.2, w: W - 0.4, h: 3.0, fontSize: 14, color: C.text2, valign: "top", paraSpaceAfter: 8, margin: 0, isTextBox: true, objectName: `stage ${i + 1} steps` });
    }
    if (i < 4) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + W + 0.07, y: top + hgt / 2 - 0.14, w: 0.26, h: 0.28, fill: { color: "8A8F99" }, line: { type: "none" }, objectName: `arrow ${i + 1}` });
  }
  const chips = ["Document", "Face, liveness", "Behaviour", "Registries", "Identity graph", "Bank network", "Footprint, opt-in"];
  chips.forEach((t, k) => s.addText(t, { x: 0.75 + 1 * (W + 0.4) + 0.25, y: top + 1.2 + k * 0.44, w: W - 0.5, h: 0.36, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.08, fill: { color: "ECEEFF" }, fontSize: 14, color: C.text1, valign: "middle", margin: 5, isTextBox: true, objectName: `check ${k + 1}` }));
  const dx = 0.75 + 3 * (W + 0.4);
  s.addText("All 13 required checks must pass", { x: dx + 0.25, y: top + 1.2, w: W - 0.45, h: 0.75, fontSize: 14, color: "C9CCD3", valign: "top", margin: 0, isTextBox: true, objectName: "decide rule" });
  [["Approve", "7FD6AC"], ["Review", "F2C27A"], ["Reject", "F29A85"]].forEach(([t, c], k) => s.addText(t, { x: dx + 0.25, y: top + 2.1 + k * 0.55, w: W - 0.5, h: 0.42, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.08, fill: { color: c }, fontSize: 14, bold: true, color: C.text1, valign: "middle", margin: 5, isTextBox: true, objectName: `band ${t}` }));
  s.addText("Partner banks keep their own KYC journey and call the same pipeline through a keyed API.", { x: 0.75, y: 6.5, w: 11, h: 0.35, fontSize: 14, color: C.text2, margin: 0, isTextBox: true, objectName: "partner note" });
  s.addNotes("One pass from upload to decision. Capture the form with typing rhythm, the card, a selfie with a server-issued head-turn burst, consent and geo-tag. Seven checks run in parallel. A model ranks risk and SHAP explains it; a profile learnt from genuine applicants only catches fraud types the model never saw. The decision is an evidence policy: all 13 required checks must pass to approve. Analysts see everything with an audit trail; the learning loop proposes changes they approve; applicants get tips only for fixable issues.");

  // ---------- 5. innovation ----------
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "The solution" });
  head(s, "What’s new", "What makes TrueID different");
  const inno = [
    ["Signature is the truth", "The issuer’s signed QR decides, not the pixels. Real Aadhaar is verified offline through UIDAI’s Secure QR.", "LuBadgeCheck"],
    ["Fair social scoring", "Opt-in footprint check that counts only contradictions.", "LuUsers"],
    ["Cross-bank network", "Banks share keyed hashes only. The same ID under another name elsewhere is held for review.", "LuGlobe"],
    ["Catches the unseen", "A profile learnt from genuine applicants catches 94% of bots the model never saw.", "LuLightbulb"],
    ["Learns, with a human", "Analyst decisions become proposals. Nothing changes until approved; every change rolls back.", "LuActivity"],
    ["AI-provenance", "C2PA content credentials are read on every upload; Ask TrueID answers from live data.", "LuScanSearch"],
  ];
  for (let i = 0; i < 6; i++) {
    const col = i % 3, row = Math.floor(i / 3), hi = i === 1;
    const x = 0.75 + col * (3.677 + 0.4), y = 1.95 + row * (2.3 + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.677, h: 2.3, rectRadius: 0.15, fill: { color: hi ? C.accent1 : INK2 }, line: hi ? { type: "none" } : { color: LINE_DARK, width: 1 }, objectName: `idea ${i + 1}` });
    await iconCircle(s, x + 0.3, y + 0.3, 0.55, inno[i][2], hi ? H.lt1 : H.accent1, hi ? H.accent1 : H.lt1, `idea ${i + 1}`);
    s.addText(inno[i][0], { x: x + 1.0, y: y + 0.3, w: 2.5, h: 0.55, fontSize: 17, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "middle", margin: 0, isTextBox: true, objectName: `idea ${i + 1} title` });
    s.addText(inno[i][1], { x: x + 0.3, y: y + 1.0, w: 3.1, h: hi ? 0.62 : 1.15, fontSize: 14, color: hi ? "E4E7FF" : MUTED_DARK, valign: "top", margin: 0, isTextBox: true, objectName: `idea ${i + 1} body` });
    if (hi) {
      s.addText("1.4% vs 20.3%", { x: x + 0.3, y: y + 1.5, w: 3.1, h: 0.42, fontSize: 24, bold: true, color: C.background1, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, objectName: "footprint stat" });
      s.addText("genuine people flagged: ours vs a naive score", { x: x + 0.3, y: y + 1.92, w: 3.2, h: 0.28, fontSize: 11, color: "E4E7FF", margin: 0, isTextBox: true, objectName: "footprint stat label" });
    }
  }
  s.addNotes("Six differences. The issuer's signature decides, not pixels, and that extends to real Aadhaar through UIDAI's Secure QR. Our social scoring is fair by design: opt-in, and it only counts contradictions. A naive social score would flag 20.3% of genuine applicants; ours flags 1.4%. Banks share keyed hashes, never customer data. A profile learnt only from genuine applicants catches fraud types the model never saw. The system learns from analysts but never changes itself without approval. And every upload is checked for AI-provenance credentials.");

  // ---------- 6. proof ----------
  pres.addSection({ title: "Proof and readiness" });
  s = pres.addSlide({ masterName: "CONTENT_LIGHT", sectionTitle: "Proof and readiness" });
  head(s, "Measured", "Fraud has to fool every layer at once");
  const stats = [["100%", "of fraud caught (recall)", C.accent2], ["0.998", "ROC-AUC fused (document alone: 0.78)", C.accent1], ["95%", "of rejections were real fraud", C.text1], ["0/85", "frauds slipped past an adaptive attacker", C.accent4]];
  stats.forEach(([n, l, c], i) => {
    const x = 0.75 + i * (2.77 + 0.25);
    s.addText(n, { x, y: 1.9, w: 2.77, h: 0.95, fontSize: 48, bold: true, color: c, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, objectName: `stat ${i + 1}` });
    s.addText(l, { x, y: 2.85, w: 2.6, h: 0.6, fontSize: 14, color: C.text2, valign: "top", margin: 0, isTextBox: true, objectName: `stat ${i + 1} label` });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.75, y: 3.65, w: 11.83, h: 2.65, rectRadius: 0.15, fill: { color: C.background1 }, line: { color: CARD_LINE, width: 1 }, objectName: "comparison card" });
  s.addChart(pres.charts.BAR, [{ name: "Edited DOBs caught", labels: ["Best pixel detector (TruFor)", "Our signed-QR check"], values: [49, 95] }], {
    x: 0.95, y: 3.75, w: 7.3, h: 2.45, barDir: "bar", chartColors: [H.accent1],
    showTitle: true, title: "An edited date of birth on a real card: % caught", titleFontSize: 14, titleColor: H.dk1, titleFontFace: "+mj-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 14, dataLabelColor: H.dk1, dataLabelFontFace: "+mn-lt",
    valAxisMaxVal: 100, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLabelColor: H.dk2, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", showLegend: false, barGapWidthPct: 60,
    objectName: "edited DOB chart",
  });
  s.addText([
    { text: "Pixel forensics is at chance (0.49) ", options: { bold: true, color: C.text1, breakLine: true } },
    { text: "on a cleanly edited date of birth. The issuer’s signature can’t be fooled: the QR still holds the true date." },
  ], { x: 8.55, y: 4.0, w: 3.8, h: 1.9, fontSize: 16, color: C.text2, valign: "middle", margin: 0, isTextBox: true, objectName: "comparison takeaway" });
  s.addText("Synthetic population · 444 test applications (85 fraud) · time-based split, 95% intervals, leakage checks. We claim the relative gains.", { x: 0.75, y: 6.45, w: 11.83, h: 0.35, fontSize: 11, color: MUTED, margin: 0, isTextBox: true, objectName: "method note" });
  s.addNotes("On a time-based test split of 444 applications with 85 fraud cases, every fraud was caught. The fused system reaches ROC-AUC 0.998 against 0.78 for the document check alone. 95% of rejections were real fraud. An adaptive attacker got 0 of 85 frauds through. Headline comparison: a state-of-the-art pixel forgery detector is at chance on an edited date of birth, while the signed-QR check catches about 95%. The data is synthetic, so we claim relative gains, not real-world accuracy.");

  // ---------- 7. close ----------
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Proof and readiness" });
  head(s, "Built for banks", "Ready for a bank’s own KYC journey");
  const closing = [
    ["Partner API", "The bank keeps its own website; its server calls TrueID with a partner key. Three demo banks run on it.", "LuKeyRound", H.accent1],
    ["Regulation first", "RBI V-CIP geo-tag and consent, DPDP erasure, a hash-chained audit trail and four-eyes approval.", "LuLock", H.accent1],
    ["Honest limits", "Synthetic test data, mock registries, liveness not yet PAD-certified, SynthID needs Google’s API.", "LuTriangleAlert", H.accent3],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.75 + i * (3.677 + 0.4), y = 1.95;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.677, h: 2.3, rectRadius: 0.15, fill: { color: INK2 }, line: { color: LINE_DARK, width: 1 }, objectName: `pillar ${i + 1}` });
    await iconCircle(s, x + 0.3, y + 0.3, 0.55, closing[i][2], closing[i][3], H.lt1, `pillar ${i + 1}`);
    s.addText(closing[i][0], { x: x + 1.0, y: y + 0.3, w: 2.5, h: 0.55, fontSize: 17, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "middle", margin: 0, isTextBox: true, objectName: `pillar ${i + 1} title` });
    s.addText(closing[i][1], { x: x + 0.3, y: y + 1.0, w: 3.1, h: 1.15, fontSize: 14, color: MUTED_DARK, valign: "top", margin: 0, isTextBox: true, objectName: `pillar ${i + 1} body` });
  }
  s.addText("Trust no single check.", { x: 0.75, y: 4.75, w: 7.6, h: 0.9, fontSize: 40, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "middle", margin: 0, isTextBox: true, objectName: "closing line" });
  stamp(s, 8.9, 4.8, 2.9, 0.8, 22, "verdict stamp");
  s.addText("github.com/Sai03SkAr/NIT-Goa-Hack · start at docs/EVALUATION.md", { x: 0.75, y: 6.0, w: 9, h: 0.35, fontSize: 14, color: "8A8F99", margin: 0, isTextBox: true, objectName: "repo link" });
  s.addNotes("TrueID is built to plug into a bank's existing journey: the bank keeps its website and calls TrueID server to server. It follows RBI V-CIP and the DPDP Act, with an audit trail that can't be edited silently. We are upfront about the limits: synthetic data, mock registries, liveness that isn't PAD-certified yet, and SynthID only through Google's API. One idea throughout: trust no single check.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
