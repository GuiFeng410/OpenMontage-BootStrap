import { useEffect, useRef } from "react";

type Saved = { time: number; playing: boolean };

const playbackBySrc = new Map<string, Saved>();

function restoreTo(el: HTMLVideoElement, src: string) {
  const saved = playbackBySrc.get(src);
  if (!saved) return;
  try {
    el.currentTime = saved.time;
  } catch {
    /* sparse/invalid media must not break the board */
  }
  if (saved.playing) el.play().catch(() => {});
}

export function PersistentVideo({
  src,
  className,
  muted,
  controls = true,
}: {
  src: string;
  className?: string;
  muted?: boolean;
  controls?: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !src) return;
    let last = playbackBySrc.get(src) || { time: 0, playing: false };
    const save = () => {
      last = {
        time: Number.isFinite(el.currentTime) ? el.currentTime : last.time,
        playing: !el.paused && !el.ended,
      };
      if (last.time > 0.05 || last.playing) playbackBySrc.set(src, last);
    };
    const restore = () => restoreTo(el, src);
    el.addEventListener("loadedmetadata", restore);
    el.addEventListener("timeupdate", save);
    el.addEventListener("pause", save);
    el.addEventListener("play", save);
    if (el.readyState >= 1) restore();
    return () => {
      if (el.currentTime > 0.05) save();
      else if (last.time > 0.05) playbackBySrc.set(src, last);
      el.removeEventListener("loadedmetadata", restore);
      el.removeEventListener("timeupdate", save);
      el.removeEventListener("pause", save);
      el.removeEventListener("play", save);
    };
  }, [src]);

  return (
    <video
      ref={ref}
      className={className}
      src={src}
      controls={controls}
      preload="metadata"
      playsInline
      muted={muted}
    />
  );
}
