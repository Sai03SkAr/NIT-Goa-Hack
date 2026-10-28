"use client";
/** Liveness guidance in the browser with MediaPipe FaceLandmarker (wasm + model served locally from /public).
 * The SERVER picks the challenge (head turns in a random order) and verifies the returned frames itself.
 * Nothing computed here decides anything; it only tells the person when to hold still for a frame. */
import { FaceLandmarker, FilesetResolver, type FaceLandmarkerResult } from "@mediapipe/tasks-vision";

export type Challenge = "turn_left" | "turn_right";
export const CHALLENGE_TEXT: Record<Challenge, string> = {
  turn_left: "Turn your head to your left", turn_right: "Turn your head to your right",
};
export type ServerChallenge = { challenge_id: string; sequence: Challenge[]; expires_in: number };

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
      runningMode: "VIDEO", numFaces: 2,
    }));
  return landmarker;
}

export type FaceSignal = { faces: number; yawRatio: number };

export function signal(r: FaceLandmarkerResult): FaceSignal {
  const faces = r.faceLandmarks?.length ?? 0;
  if (!faces) return { faces: 0, yawRatio: 0.5 };
  const lm = r.faceLandmarks[0];
  const left = lm[234], right = lm[454], nose = lm[1];
  const yawRatio = (nose.x - left.x) / Math.max(1e-3, right.x - left.x);
  return { faces, yawRatio };
}

/** Raw (unmirrored) camera image: the user turning to THEIR left moves the nose toward image-right.
 * Same convention the server uses on the frames, so a guided turn is a turn the server will accept. */
export function satisfied(c: Challenge, s: FaceSignal): boolean {
  if (s.faces !== 1) return false;
  if (c === "turn_left") return s.yawRatio > 0.66;
  return s.yawRatio < 0.34;
}

export function grabFrame(video: HTMLVideoElement, quality = 0.9): Promise<Blob> {
  const c = document.createElement("canvas");
  c.width = video.videoWidth; c.height = video.videoHeight;
  c.getContext("2d")!.drawImage(video, 0, 0);
  return new Promise((res) => c.toBlob((b) => res(b!), "image/jpeg", quality));
}
