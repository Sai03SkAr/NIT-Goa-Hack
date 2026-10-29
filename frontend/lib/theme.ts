/** Colors for canvas/SVG code (charts, identity graph) that can't read CSS variables. Mirrors app/globals.css. */
export const INK = "#14161a";
export const MUTED = "#6e7380";
export const GRID = "#ebece7";
export const BRAND = "#2b3be6";
export const BRAND_2 = "#a9b1ff";  // secondary series next to BRAND
export const APPROVE = "#0f7b52";
export const REVIEW = "#b4690e";
export const REJECT = "#c8361f";

/** Categorical colors for fraud patterns, distinct from the decision colors and readable on white. */
export const TYPE_COLORS: Record<string, string> = {
  none: "#8a93a2", first_party: "#a03d8a", third_party: "#5160b8", ring: "#c2410c", bot: "#8a6a00",
  tampered: "#0e6f86", injection: "#4d7c0f", mule: "#7c4a1e", inconclusive: "#6b7280",
};

/** Identity-graph link kinds, strongest evidence in the strongest colors. */
export const LINK_COLORS: Record<string, string> = {
  face: "#c2410c", id_hash: "#b42318", device: "#8a6a00", keystroke: "#5160b8", email_stem: "#a03d8a",
  phone: "#0e6f86", address: "#9aa2ae", ip: "#c9ced6",
};

export const AXIS = { stroke: MUTED, fontSize: 11, tickLine: false } as const;
export const TOOLTIP = {
  contentStyle: { background: "#ffffff", border: "1px solid #e3e4df", borderRadius: 10, fontSize: 12, color: INK, boxShadow: "0 2px 8px rgba(21,24,29,.08)" },
  labelStyle: { color: INK, fontWeight: 500 },
} as const;
