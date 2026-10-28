"use client";
import { useEffect, useRef, useState } from "react";
import { Camera, RotateCcw, Upload } from "lucide-react";

const RATIO = 1.586; // ID-1 card

/** Live capture of the ID card inside a card-shaped guide (the photo is cropped to the guide so the card fills it).
 * Upload is allowed only for the e-ID image downloaded from DigiLocker; the source is reported to the bank. */
export function DocCapture({ onCapture }: { onCapture: (b: Blob | null, source: "camera" | "digilocker_file" | null) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [state, setState] = useState<"idle" | "live" | "done">("idle");
  const [preview, setPreview] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => () => stream.current?.getTracks().forEach((t) => t.stop()), []);

  async function start() {
    setErr("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720, facingMode: "environment" } });
      video.current!.srcObject = stream.current;
      await video.current!.play();
      setState("live");
    } catch {
      setErr("We couldn't open your camera. Allow camera access in the browser, or upload your e-ID file instead.");
    }
  }

  function snap() {
    const v = video.current!;
    const W = v.videoWidth, H = v.videoHeight;
    const gw = Math.min(W * 0.8, H * 0.8 * RATIO), gh = gw / RATIO;
    const c = document.createElement("canvas");
    c.width = 1012; c.height = Math.round(1012 / RATIO);
    c.getContext("2d")!.drawImage(v, (W - gw) / 2, (H - gh) / 2, gw, gh, 0, 0, c.width, c.height);
    c.toBlob((b) => {
      if (!b) return;
      setPreview(URL.createObjectURL(b)); setState("done"); onCapture(b, "camera");
      stream.current?.getTracks().forEach((t) => t.stop());
    }, "image/jpeg", 0.92);
  }

  function upload(f: File) {
    setPreview(URL.createObjectURL(f)); setState("done"); onCapture(f, "digilocker_file");
    stream.current?.getTracks().forEach((t) => t.stop());
  }

  function retake() { setPreview(null); setState("idle"); onCapture(null, null); }

  return (
    <div>
      <div className="relative aspect-[16/10] overflow-hidden rounded-xl bg-[#17221f]">
        {state === "done" && preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="Captured ID card" className="h-full w-full object-contain" />
        ) : (
          <>
            <video ref={video} muted playsInline className="h-full w-full object-cover" />
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <div className="aspect-[1.586] w-[80%] max-h-[80%] rounded-[14px] border-2 border-dashed border-white/70 shadow-[0_0_0_999px_rgba(10,20,18,.45)]" />
            </div>
            {state === "idle" && (
              <div className="absolute inset-0 grid place-items-center">
                <button type="button" className="btn btn-primary" onClick={start}><Camera className="size-4" />Turn on camera</button>
              </div>
            )}
          </>
        )}
      </div>
      {err && <p className="error mt-3">{err}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {state === "live" && <button type="button" className="btn btn-primary" onClick={snap}><Camera className="size-4" />Take photo</button>}
        {state === "done" && <button type="button" className="btn" onClick={retake}><RotateCcw className="size-4" />Retake</button>}
        {state !== "done" && (
          <label className="btn cursor-pointer">
            <Upload className="size-4" />Upload e-ID from DigiLocker
            <input type="file" accept="image/jpeg,image/png" className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        )}
      </div>
    </div>
  );
}
