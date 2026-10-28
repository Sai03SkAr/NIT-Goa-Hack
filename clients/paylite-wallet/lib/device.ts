"use client";
/** 20-line device hash (UA + screen + timezone + canvas) and virtual-camera detection. */

export async function deviceId(): Promise<string> {
  const c = document.createElement("canvas");
  const g = c.getContext("2d");
  if (g) { g.textBaseline = "top"; g.font = "14px Arial"; g.fillStyle = "#f60"; g.fillRect(0, 0, 80, 20); g.fillStyle = "#069"; g.fillText("PayLite₹", 2, 2); }
  const parts = [navigator.userAgent, `${screen.width}x${screen.height}x${screen.colorDepth}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.language, String(navigator.hardwareConcurrency), c.toDataURL()];
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(parts.join("|")));
  return "D" + Array.from(new Uint8Array(buf)).slice(0, 5).map((b) => b.toString(16).padStart(2, "0")).join("");
}

const VIRTUAL = ["virtual", "obs", "manycam", "xsplit", "snap camera", "droidcam", "vcam", "splitcam"];

/** Labels are only visible after camera permission is granted, so call this after getUserMedia.
 * Only the camera actually streaming counts: OBS installed but unused is not an injection. */
export async function cameraLabels(stream: MediaStream): Promise<{ labels: string[]; active: string; virtual: boolean }> {
  const devs = await navigator.mediaDevices.enumerateDevices();
  const labels = devs.filter((d) => d.kind === "videoinput").map((d) => d.label);
  const active = stream.getVideoTracks()[0]?.label ?? "";
  return { labels, active, virtual: VIRTUAL.some((v) => active.toLowerCase().includes(v)) };
}
