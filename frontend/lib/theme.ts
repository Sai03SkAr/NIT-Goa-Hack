/** Colors for canvas/SVG code (charts, identity graph) that can't read CSS variables. Mirrors app/globals.css. */
export const INK = "#15181d";
export const MUTED = "#677080";
export const GRID = "#e6e9ee";
export const BRAND = "#2445a8";
export const APPROVE = "#17733f";
export const REVIEW = "#9a5800";
export const REJECT = "#b42318";

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
  contentStyle: { background: "#fdfdfe", border: "1px solid #cfd5dd", borderRadius: 8, fontSize: 12, color: INK, boxShadow: "0 2px 8px rgba(21,24,29,.08)" },
  labelStyle: { color: INK, fontWeight: 500 },
} as const;
