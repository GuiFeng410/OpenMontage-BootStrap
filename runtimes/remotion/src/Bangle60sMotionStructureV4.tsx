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
const SAMPLE_ROOT = "bangle-assets/i2i_samples_20260804/";

type Source = "base" | "sample";
type Bridge = "hold" | "soft" | "light" | "arc" | "match";

type StructureShot = {
  id: string;
  image: string;
  source: Source;
  label: string;
  start: number;
  duration: number;
  scale: [number, number];
  x: [number, number];
  y: [number, number];
  objectPosition: string;
  accent: string;
  bridge: Bridge;
};

// Fifteen four-second beats form the approved 60s structure. The 0.55s
// overlap lets motion and light hand off between scenes without inventing
// product geometry.
const shots: StructureShot[] = [
  {
    id: "scene01",
    image: "02.png",
    source: "base",
    label: "01 / IDENTITY ANCHOR",
    start: 0,
    duration: 4.55,
    scale: [1.02, 1.07],
    x: [0, -0.8],
    y: [0, -0.5],
    objectPosition: "50% 56%",
    accent: "rgba(255, 221, 168, 0.14)",
    bridge: "hold",
  },
  {
    id: "scene02",
    image: "02.png",
    source: "base",
    label: "02 / HERO CROP",
    start: 4,
    duration: 4.55,
    scale: [1.16, 1.27],
    x: [-0.8, 0.5],
    y: [-0.5, -1.2],
    objectPosition: "50% 54%",
    accent: "rgba(248, 224, 182, 0.13)",
    bridge: "match",
  },
  {
    id: "scene03",
    image: "06.png",
    source: "base",
    label: "03 / TEXTURE ANGLE A",
    start: 8,
    duration: 4.55,
    scale: [1.14, 1.26],
    x: [0.5, -0.6],
    y: [-1.2, -0.3],
    objectPosition: "50% 50%",
    accent: "rgba(207, 237, 222, 0.13)",
    bridge: "arc",
  },
  {
    id: "scene04",
    image: "07.png",
    source: "base",
    label: "04 / TEXTURE ANGLE B",
    start: 12,
    duration: 4.55,
    scale: [1.16, 1.05],
    x: [-0.6, 0.6],
    y: [-0.3, -0.8],
    objectPosition: "50% 50%",
    accent: "rgba(248, 235, 199, 0.12)",
    bridge: "soft",
  },
  {
    id: "scene05",
    image: "light_soft_specular_sweep.png",
    source: "sample",
    label: "05 / SOFT SPECULAR",
    start: 16,
    duration: 4.55,
    scale: [1.04, 1.10],
    x: [0.6, -0.3],
    y: [-0.8, -0.2],
    objectPosition: "50% 51%",
    accent: "rgba(247, 244, 221, 0.15)",
    bridge: "light",
  },
  {
    id: "scene06",
    image: "02.png",
    source: "base",
    label: "06 / LUSTRE BRIDGE",
    start: 20,
    duration: 4.55,
    scale: [1.10, 1.05],
    x: [-0.3, 0.7],
    y: [-0.2, -0.7],
    objectPosition: "50% 55%",
    accent: "rgba(255, 228, 173, 0.16)",
    bridge: "light",
  },
  {
    id: "scene07",
    image: "04.png",
    source: "base",
    label: "07 / ANGLE REVEAL",
    start: 24,
    duration: 4.55,
    scale: [1.05, 1.12],
    x: [0.7, 0],
    y: [-0.7, -0.3],
    objectPosition: "50% 50%",
    accent: "rgba(213, 237, 224, 0.13)",
    bridge: "arc",
  },
  {
    id: "scene08",
    image: "04.png",
    source: "base",
    label: "08 / ANGLE HOLD",
    start: 28,
    duration: 4.55,
    scale: [1.14, 1.05],
    x: [0, -0.6],
    y: [-0.3, 0.2],
    objectPosition: "50% 50%",
    accent: "rgba(203, 231, 219, 0.11)",
    bridge: "soft",
  },
  {
    id: "scene09",
    image: "environment_pale_stone.png",
    source: "sample",
    label: "09 / PALE STONE SET",
    start: 32,
    duration: 4.55,
    scale: [1.04, 1.10],
    x: [-0.6, 0.2],
    y: [0.2, -0.5],
    objectPosition: "50% 52%",
    accent: "rgba(235, 221, 195, 0.14)",
    bridge: "light",
  },
  {
    id: "scene10",
    image: "environment_green_gray_studio.png",
    source: "sample",
    label: "10 / GREEN-GRAY SET",
    start: 36,
    duration: 4.55,
    scale: [1.10, 1.04],
    x: [0.2, 0.8],
    y: [-0.5, 0],
    objectPosition: "50% 50%",
    accent: "rgba(184, 219, 198, 0.15)",
    bridge: "light",
  },
  {
    id: "scene11",
    image: "08.png",
    source: "base",
    label: "11 / WEARABLE CLOSE",
    start: 40,
    duration: 4.55,
    scale: [1.06, 1.16],
    x: [0.8, -0.2],
    y: [0, -0.8],
    objectPosition: "50% 50%",
    accent: "rgba(239, 215, 188, 0.11)",
    bridge: "match",
  },
  {
    id: "scene12",
    image: "09.png",
    source: "base",
    label: "12 / WEARABLE CONTEXT",
    start: 44,
    duration: 4.55,
    scale: [1.04, 1.08],
    x: [-0.2, 0.5],
    y: [-0.8, -0.2],
    objectPosition: "50% 50%",
    accent: "rgba(230, 218, 197, 0.10)",
    bridge: "soft",
  },
  {
    id: "scene13",
    image: "02.png",
    source: "base",
    label: "13 / RETURN TO PRODUCT",
    start: 48,
    duration: 4.55,
    scale: [1.18, 1.08],
    x: [0.5, -0.2],
    y: [-0.2, -0.6],
    objectPosition: "50% 55%",
    accent: "rgba(247, 230, 190, 0.14)",
    bridge: "arc",
  },
  {
    id: "scene14",
    image: "02.png",
    source: "base",
    label: "14 / WARM LUSTRE",
    start: 52,
    duration: 4.55,
    scale: [1.06, 1.11],
    x: [-0.2, 0.4],
    y: [-0.6, -0.1],
    objectPosition: "50% 55%",
    accent: "rgba(255, 213, 157, 0.20)",
    bridge: "light",
  },
  {
    id: "scene15",
    image: "02.png",
    source: "base",
    label: "15 / FINAL HERO HOLD",
    start: 56,
    duration: 4,
    scale: [1.06, 1.02],
    x: [0.4, 0],
    y: [-0.1, 0],
    objectPosition: "50% 56%",
    accent: "rgba(255, 221, 168, 0.15)",
    bridge: "hold",
  },
];

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const StructureShot: React.FC<{ shot: StructureShot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localSeconds = frame / fps - shot.start;
  const progress = interpolate(localSeconds, [0, shot.duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const transitionSeconds = shot.bridge === "hold" ? 0.25 : 0.85;
  const exitSeconds = shot.id === "scene15" ? 0.65 : 0.58;
  const fadeIn = interpolate(localSeconds, [0, transitionSeconds], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const fadeOut = interpolate(
    localSeconds,
    [shot.duration - exitSeconds, shot.duration],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) },
  );
  const opacity = Math.min(fadeIn, fadeOut);
  const scale = interpolate(progress, [0, 1], shot.scale);
  const x = interpolate(progress, [0, 1], shot.x);
  const y = interpolate(progress, [0, 1], shot.y);
  const bridgeProgress = clamp01(localSeconds / transitionSeconds);
  const bridgeGlow = Math.sin(bridgeProgress * Math.PI);
  const arcRadius = interpolate(bridgeProgress, [0, 1], [8, 145]);
  const lightX = interpolate(bridgeProgress, [0, 1], [-115, 115], {
    easing: Easing.inOut(Easing.quad),
  });
  const imageSrc = shot.source === "base"
    ? staticFile(`bangle-assets/${shot.image}`)
    : staticFile(`${SAMPLE_ROOT}${shot.image}`);
  const softMask = shot.bridge === "arc"
    ? `radial-gradient(ellipse at 50% 50%, black ${Math.max(0, arcRadius - 8)}%, transparent ${Math.min(100, arcRadius + 16)}%)`
    : undefined;
  const labelOpacity = Math.min(
    interpolate(localSeconds, [0.68, 1.04], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }),
    interpolate(localSeconds, [shot.duration - 0.48, shot.duration], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.in(Easing.cubic),
    }),
  );

  return (
    <AbsoluteFill style={{ opacity, overflow: "hidden", background: "#111714" }}>
      <Img
        src={imageSrc}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: shot.objectPosition,
          transform: `translate(${x}%, ${y}%) scale(${scale})`,
          maskImage: softMask,
          WebkitMaskImage: softMask,
          filter: "contrast(1.035) saturate(0.92) brightness(0.99)",
        }}
      />
      <AbsoluteFill style={{ background: shot.accent, mixBlendMode: "screen" }} />
      {shot.bridge === "light" || shot.bridge === "arc" || shot.bridge === "match" ? (
        <div
          style={{
            position: "absolute",
            inset: "-30% -45%",
            transform: `translateX(${lightX}%) rotate(-14deg)`,
            background: "linear-gradient(90deg, transparent 37%, rgba(255,249,221,0.34) 48%, rgba(255,255,255,0.08) 54%, transparent 66%)",
            mixBlendMode: "screen",
            opacity: bridgeGlow * (shot.bridge === "match" ? 0.50 : 0.86),
          }}
        />
      ) : null}
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at 50% 46%, transparent 48%, rgba(0,0,0,0.32) 100%)",
          opacity: 0.74,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 58,
          left: 76,
          color: "rgba(249,247,237,0.84)",
          opacity: labelOpacity,
          fontFamily: "Arial, sans-serif",
          fontSize: 21,
          fontWeight: 600,
          letterSpacing: "0.12em",
        }}
      >
        {shot.label}
      </div>
      <div
        style={{
          position: "absolute",
          left: 78,
          bottom: 60,
          width: 260,
          height: 2,
          background: "rgba(231, 211, 166, 0.70)",
          opacity: labelOpacity,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 76,
          bottom: 56,
          color: "rgba(249,247,237,0.60)",
          opacity: labelOpacity,
          fontFamily: "Arial, sans-serif",
          fontSize: 15,
          letterSpacing: "0.08em",
        }}
      >
        60S MOTION STRUCTURE / NO BRAND LAYER
      </div>
    </AbsoluteFill>
  );
};

export const Bangle60sMotionStructureV4: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#111714" }}>
      {shots.map((shot) => <StructureShot key={shot.id} shot={shot} />)}
    </AbsoluteFill>
  );
};

export const BANGLE_60S_MOTION_STRUCTURE_V4_DURATION = 60 * FPS;
