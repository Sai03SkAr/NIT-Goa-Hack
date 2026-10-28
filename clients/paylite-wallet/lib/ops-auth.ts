/** Tiny passcode gate for the operations console (demo scope). The cookie holds a hash, never the passcode. */
export const OPS_COOKIE = "pl_ops";
const PASSCODE = process.env.OPS_PASSCODE ?? "paylite-ops";

export async function opsToken(passcode = PASSCODE): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`paylite-ops:${passcode}`));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function isOps(cookie: string | undefined): Promise<boolean> {
  return !!cookie && cookie === (await opsToken());
}
