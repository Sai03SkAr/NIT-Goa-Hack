// Serves MediaPipe locally (no CDN at runtime): wasm from the npm package, face model from the main TrueID frontend.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "mediapipe");
mkdirSync(out, { recursive: true });
const wasm = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
if (existsSync(wasm)) cpSync(wasm, join(out, "wasm"), { recursive: true });
else console.warn("[mediapipe] run npm install first: wasm files not found");
const model = join(root, "..", "..", "frontend", "public", "mediapipe", "face_landmarker.task");
if (existsSync(model)) cpSync(model, join(out, "face_landmarker.task"));
else console.warn("[mediapipe] face_landmarker.task not found in ../../frontend/public/mediapipe; liveness will not load");
