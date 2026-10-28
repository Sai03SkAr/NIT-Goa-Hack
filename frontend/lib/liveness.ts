"use client";
/** Active liveness in the browser with MediaPipe FaceLandmarker (wasm + model served locally from /public).
 * Two random challenges (always one head turn, so the server can verify different poses), time-limited. */
import { FaceLandmarker, FilesetResolver, type FaceLandmarkerResult } from "@mediapipe/tasks-vision";

export type Challenge = "blink" | "smile" | "turn_left" | "turn_right";
export const CHALLENGE_TEXT: Record<Challenge, string> = {
  blink: "Blink both eyes", smile: "Give a big smile", turn_left: "Turn your head to your left", turn_right: "Turn your head to your right",
};

// MediaPipe's wasm logs "INFO: ..." lines through console.error, which the Next dev overlay shows as errors.
if (typeof window !== "undefined") {
  const err = console.error.bind(console);
  console.error = (...a: unknown[]) => { if (typeof a[0] === "string" && a[0].startsWith("INFO:")) return; err(...a); };
}

let landmarker: Promise<FaceLandmarker> | null = null;
export function getLandmarker() {
  landmarker ??= FilesetResolver.forVisionTasks("/mediapipe/wasm").then((fs) =>
    FaceLandmarker.createFromOptions(fs, {
      baseOptions: { modelAssetPath: "/mediapipe/face_landmarker.task", delegate: "GPU" },
      runningMode: "VIDEO", numFaces: 2, outputFaceBlendshapes: true,
    }));
  return landmarker;
}

export function pickChallenges(): Challenge[] {
  const turn: Challenge = Math.random() < 0.5 ? "turn_left" : "turn_right";
  const expr: Challenge = Math.random() < 0.5 ? "blink" : "smile";
  return Math.random() < 0.5 ? [turn, expr] : [expr, turn];
}

export type FaceSignal = { faces: number; yawRatio: number; blink: number; smile: number };

export function signal(r: FaceLandmarkerResult): FaceSignal {
  const faces = r.faceLandmarks?.length ?? 0;
  if (!faces) return { faces: 0, yawRatio: 0.5, blink: 0, smile: 0 };
  const lm = r.faceLandmarks[0];
  const left = lm[234], right = lm[454], nose = lm[1];
  const yawRatio = (nose.x - left.x) / Math.max(1e-3, right.x - left.x);
  const bs = Object.fromEntries((r.faceBlendshapes?.[0]?.categories ?? []).map((c) => [c.categoryName, c.score]));
  return { faces, yawRatio, blink: Math.min(bs.eyeBlinkLeft ?? 0, bs.eyeBlinkRight ?? 0), smile: ((bs.mouthSmileLeft ?? 0) + (bs.mouthSmileRight ?? 0)) / 2 };
}

/** Raw (unmirrored) camera image: the user turning to THEIR left moves the nose toward image-right. */
export function satisfied(c: Challenge, s: FaceSignal): boolean {
  if (s.faces !== 1) return false;
  if (c === "blink") return s.blink > 0.45;
  if (c === "smile") return s.smile > 0.55;
  if (c === "turn_left") return s.yawRatio > 0.66;
  return s.yawRatio < 0.34;
}

export function grabFrame(video: HTMLVideoElement, quality = 0.9): Promise<Blob> {
  const c = document.createElement("canvas");
  c.width = video.videoWidth; c.height = video.videoHeight;
  c.getContext("2d")!.drawImage(video, 0, 0);
  return new Promise((res) => c.toBlob((b) => res(b!), "image/jpeg", quality));
}
