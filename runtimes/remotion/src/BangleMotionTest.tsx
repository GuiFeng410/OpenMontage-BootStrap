import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FPS = 30;
const ROOT = "bangle-assets/";

type Shot = {
  id: string;
  image: string;
  start: number;
  duration: number;
  scaleFrom: number;
  scaleTo: number;
  xFrom: number;
  xTo: number;
  yFrom: number;
  yTo: number;
  tint: string;
};

const shots: Shot[] = [
  { id: "hero", image: "02.png", start: 0, duration: 2.2, scaleFrom: 1.02, scaleTo: 1.12, xFrom: 0, xTo: -1.5, yFrom: 0, yTo: -1, tint: "rgba(204,224,215,0.08)" },
  { id: "texture", image: "06.png", start: 2.0, duration: 2.0, scaleFrom: 1.16, scaleTo: 1.32, xFrom: 2, xTo: -3, yFrom: 1, yTo: -1, tint: "rgba(231,246,239,0.13)" },
  { id: "lustre", image: "02.png", start: 3.8, duration: 2.0, scaleFrom: 1.08, scaleTo: 1.18, xFrom: -1, xTo: 1, yFrom: 0, yTo: -1, tint: "rgba(249,232,180,0.12)" },
  { id: "upright", image: "04.png", start: 5.6, duration: 2.0, scaleFrom: 1.05, scaleTo: 1.18, xFrom: 2, xTo: -1, yFrom: 1, yTo: -2, tint: "rgba(216,237,227,0.10)" },
  { id: "angle-detail", image: "07.png", start: 7.4, duration: 1.8, scaleFrom: 1.12, scaleTo: 1.26, xFrom: -2, xTo: 2, yFrom: 0, yTo: -1, tint: "rgba(255,240,199,0.11)" },
  { id: "wearable", image: "08.png", start: 9.0, duration: 2.2, scaleFrom: 1.05, scaleTo: 1.12, xFrom: 1, xTo: -1, yFrom: 0, yTo: -1, tint: "rgba(238,213,183,0.08)" },
  { id: "return", image: "02.png", start: 11.0, duration: 3.0, scaleFrom: 1.17, scaleTo: 1.04, xFrom: -1, xTo: 0, yFrom: -1, yTo: 0, tint: "rgba(219,240,230,0.10)" },
];

const opacityForShot = (frame: number, shot: Shot) => {
  const local = frame / FPS - shot.start;
  const fade = 0.28;
  return Math.min(
    interpolate(local, [0, fade], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }),
    interpolate(local, [shot.duration - fade, shot.duration], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) }),
  );
};

const BangleShot: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const local = Math.max(0, frame / FPS - shot.start);
  const progress = interpolate(local, [0, shot.duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const scale = interpolate(progress, [0, 1], [shot.scaleFrom, shot.scaleTo]);
  const x = interpolate(progress, [0, 1], [shot.xFrom, shot.xTo]);
  const y = interpolate(progress, [0, 1], [shot.yFrom, shot.yTo]);
  const lightProgress = interpolate(local, [0, shot.duration], [-35, 135], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });

  return (
    <AbsoluteFill style={{ opacity: opacityForShot(frame, shot), overflow: "hidden", background: "#111714" }}>
      <Img
        src={staticFile(`${ROOT}${shot.image}`)}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translate(${x}%, ${y}%) scale(${scale})`,
          filter: "contrast(1.04) saturate(0.93) brightness(0.98)",
        }}
      />
      <AbsoluteFill style={{ background: shot.tint, mixBlendMode: "screen" }} />
      <div
        style={{
          position: "absolute",
          inset: "-25% -40%",
          transform: `translateX(${lightProgress}%) rotate(-14deg)`,
          background: "linear-gradient(90deg, transparent 38%, rgba(255,248,214,0.22) 48%, rgba(255,255,255,0.06) 53%, transparent 64%)",
          mixBlendMode: "screen",
          opacity: 0.75,
        }}
      />
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at 50% 45%, transparent 48%, rgba(0,0,0,0.36) 100%)",
          opacity: 0.72,
        }}
      />
    </AbsoluteFill>
  );
};

export const BangleMotionTest: React.FC = () => {
  const { durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();
  const flash = interpolate(frame, [0, 18, durationInFrames - 24, durationInFrames], [0, 0.32, 0.08, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: "#111714" }}>
      {shots.map((shot) => <BangleShot key={shot.id} shot={shot} />)}
      <AbsoluteFill style={{ background: "rgba(255,255,255,0.08)", opacity: flash, pointerEvents: "none" }} />
    </AbsoluteFill>
  );
};

export const BANGLE_MOTION_TEST_DURATION = 14 * FPS;
