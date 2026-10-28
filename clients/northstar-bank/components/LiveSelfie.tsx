"use client";
import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Camera, Check, X } from "lucide-react";
import { cameraLabels } from "@/lib/device";
import { CHALLENGE_TEXT, type Challenge, getLandmarker, grabFrame, pickChallenges, satisfied, signal } from "@/lib/liveness";

export type LiveResult = {
  selfie: Blob;
  frames: Blob[];
  liveness: Record<string, unknown>;
  cameras: { labels: string[]; active: string };
};

type S = "idle" | "loading" | "ready" | "challenge" | "passed" | "failed";
const SECONDS = 8;

/** Active liveness (same MediaPipe checks as TrueID's own flow): two random challenges, one of them a head turn,
 * with a frame captured after each so TrueID can re-check on the server that it was one live person. */
export function LiveSelfie({ onResult }: { onResult: (r: LiveResult | null) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [state, setState] = useState<S>("idle");
  const [chs, setChs] = useState<Challenge[]>([]);
  const [idx, setIdx] = useState(0);
  const [left, setLeft] = useState(SECONDS);
  const [hint, setHint] = useState("");
  const [err, setErr] = useState("");
  const done = useRef<Challenge[]>([]);

  useEffect(() => () => stream.current?.getTracks().forEach((t) => t.stop()), []);

  async function start() {
    setState("loading"); setErr("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      video.current!.srcObject = stream.current;
      await video.current!.play();
      await getLandmarker();
      setState("ready");
    } catch {
      setErr("We need your camera for the live selfie. Allow camera access in the browser and try again.");
      setState("idle");
    }
  }

  async function run() {
    const lm = await getLandmarker();
    const v = video.current!;
    const list = pickChallenges();
    setChs(list); setIdx(0); setState("challenge"); onResult(null);
    done.current = [];
    const frames = [await grabFrame(v)];
    for (let i = 0; i < list.length; i++) {
      setIdx(i);
      const ok = await new Promise<boolean>((resolve) => {
        const t0 = performance.now();
        const tick = () => {
          const el = (performance.now() - t0) / 1000;
          setLeft(Math.max(0, Math.ceil(SECONDS - el)));
          if (el > SECONDS) return resolve(false);
          const s = signal(lm.detectForVideo(v, performance.now()));
          setHint(s.faces === 0 ? "We can't see your face" : s.faces > 1 ? "Only you should be in the frame" : "");
          if (satisfied(list[i], s)) return resolve(true);
          requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      if (!ok) { setState("failed"); return; }
      done.current.push(list[i]);
      frames.push(await grabFrame(v));
    }
    const cams = await cameraLabels(stream.current!);
    setState("passed");
    onResult({
      selfie: frames[0], frames,
      liveness: { performed: true, challenges: list, completed: done.current, passed: true, virtual_camera: cams.virtual, client: "mediapipe-facelandmarker" },
      cameras: { labels: cams.labels, active: cams.active },
    });
  }

  const current = chs[idx];
  return (
    <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
      <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-[#17221f]">
        <video ref={video} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className={clsx("aspect-[3/4] h-[74%] rounded-[50%] border-[3px] transition-colors",
            state === "passed" ? "border-ok" : state === "failed" ? "border-err" : "border-white/60")} />
        </div>
        {state === "idle" && (
          <div className="absolute inset-0 grid place-items-center">
            <button type="button" className="btn btn-primary" onClick={start}><Camera className="size-4" />Turn on camera</button>
          </div>
        )}
        {state === "loading" && <div className="absolute inset-0 grid place-items-center text-sm text-white/80">Starting camera…</div>}
        {state === "challenge" && current && (
          <div aria-live="assertive" className="absolute inset-x-0 bottom-0 bg-[#0e1715]/80 px-5 py-4 text-white">
            <div className="text-sm text-white/75">{idx + 1} of {chs.length}, {left}s left</div>
            <div className="mt-0.5 text-xl font-semibold">{CHALLENGE_TEXT[current]}</div>
            {hint && <div className="mt-1 text-sm text-[#f4c97a]">{hint}</div>}
          </div>
        )}
      </div>
      <div className="flex flex-col">
        <p className="text-muted">
          Look straight at the camera with your face inside the oval. We&apos;ll ask for two quick movements you can&apos;t
          predict, so a photo or a recording can&apos;t pass.
        </p>
        <ul className="mt-5 space-y-2.5 text-sm">
          {chs.length === 0 && <li className="text-faint">Instructions appear here once you start.</li>}
          {chs.map((c, i) => {
            const ok = state === "passed" || done.current.includes(c);
            const bad = state === "failed" && i === idx;
            return (
              <li key={c} className="flex items-center gap-2.5">
                <span className={clsx("grid size-5 place-items-center rounded-full border",
                  ok ? "border-ok bg-ok text-white" : bad ? "border-err text-err" : "border-line")}>
                  {ok ? <Check className="size-3" /> : bad ? <X className="size-3" /> : null}
                </span>
                <span className={bad ? "text-err" : ok ? "" : "text-muted"}>{CHALLENGE_TEXT[c]}</span>
              </li>
            );
          })}
        </ul>
        {err && <p className="error mt-4">{err}</p>}
        {state === "failed" && <p className="error mt-4">That didn&apos;t register in time. Check your lighting and try again.</p>}
        <div className="mt-auto pt-6">
          {(state === "ready" || state === "failed") && (
            <button type="button" className="btn btn-primary w-full" onClick={run}>{state === "failed" ? "Try again" : "Start live selfie"}</button>
          )}
          {state === "passed" && <p className="text-sm font-medium text-ok">Live selfie captured.</p>}
        </div>
      </div>
    </div>
  );
}
