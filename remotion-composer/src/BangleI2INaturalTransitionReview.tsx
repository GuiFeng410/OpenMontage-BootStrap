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

type Bridge = "soft" | "light" | "arc" | "hold";

type NaturalShot = {
  id: string;
  image: string;
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

// The overlap is intentional: each shot inherits the previous shot's motion
// direction, so the product does not appear to stop and restart at every cut.
const shots: NaturalShot[] = [
  {
    id: "anchor",
    image: "02.png",
    label: "IDENTITY ANCHOR",
    start: 0,
    duration: 4.35,
    scale: [1.02, 1.08],
    x: [0, -0.8],
    y: [0, -0.6],
    objectPosition: "50% 56%",
    accent: "rgba(255, 221, 168, 0.15)",
    bridge: "hold",
  },
  {
    id: "three-quarter",
    image: "angle_controlled_three_quarter.png",
    label: "CONTROLLED THREE-QUARTER",
    start: 3.55,
    duration: 4.15,
    scale: [1.06, 1.12],
    x: [-0.2, -1.0],
    y: [-0.3, -0.8],
    objectPosition: "50% 51%",
    accent: "rgba(206, 235, 220, 0.13)",
    bridge: "soft",
  },
  {
    id: "soft-light",
    image: "light_soft_specular_sweep.png",
    label: "SOFT SPECULAR LIGHT",
    start: 7.10,
    duration: 4.05,
    scale: [1.12, 1.06],
    x: [-1.0, 0.2],
    y: [-0.8, -0.2],
    objectPosition: "50% 51%",
    accent: "rgba(247, 244, 221, 0.16)",
    bridge: "light",
  },
  {
    id: "pale-stone",
    image: "environment_pale_stone.png",
    label: "PALE STONE ENVIRONMENT",
    start: 10.65,
    duration: 4.05,
    scale: [1.06, 1.11],
    x: [0.2, -0.6],
    y: [-0.2, -0.7],
    objectPosition: "50% 52%",
    accent: "rgba(235, 221, 195, 0.13)",
    bridge: "light",
  },
  {
    id: "green-gray",
    image: "environment_green_gray_studio.png",
    label: "GREEN-GRAY STUDIO",
    start: 14.20,
    duration: 4.05,
    scale: [1.10, 1.06],
    x: [-0.6, 0.35],
    y: [-0.7, -0.1],
    objectPosition: "50% 50%",
    accent: "rgba(184, 219, 198, 0.15)",
    bridge: "soft",
  },
  {
    id: "upright-test",
    image: "angle_upright_display.png",
    label: "UPRIGHT DISPLAY TEST",
    start: 17.75,
    duration: 3.75,
    scale: [1.06, 1.11],
    x: [0.35, -0.35],
    y: [-0.1, -0.8],
    objectPosition: "50% 51%",
    accent: "rgba(244, 215, 172, 0.14)",
    bridge: "arc",
  },
  {
    id: "warm-lustre",
    image: "light_warm_diffused_lustre.png",
    label: "WARM DIFFUSED LUSTRE",
    start: 21.00,
    duration: 3.00,
    scale: [1.10, 1.04],
    x: [-0.35, 0],
    y: [-0.8, -0.2],
    objectPosition: "50% 51%",
    accent: "rgba(255, 224, 170, 0.15)",
    bridge: "light",
  },
];

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const NaturalShot: React.FC<{ shot: NaturalShot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localSeconds = frame / fps - shot.start;
  const progress = interpolate(localSeconds, [0, shot.duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const transitionSeconds = 0.9;
  const exitSeconds = 0.72;
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
  const imageSrc = shot.id === "anchor"
    ? staticFile(`bangle-assets/${shot.image}`)
    : staticFile(`${SAMPLE_ROOT}${shot.image}`);

  const softMask = shot.bridge === "arc"
    ? `radial-gradient(ellipse at 50% 50%, black ${Math.max(0, arcRadius - 8)}%, transparent ${Math.min(100, arcRadius + 16)}%)`
    : undefined;
  const labelOpacity = Math.min(
    interpolate(localSeconds, [0.72, 1.08], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }),
    interpolate(localSeconds, [shot.duration - 0.55, shot.duration], [1, 0], {
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
      {shot.bridge === "light" || shot.bridge === "arc" ? (
        <div
          style={{
            position: "absolute",
            inset: "-30% -45%",
            transform: `translateX(${lightX}%) rotate(-14deg)`,
            background: "linear-gradient(90deg, transparent 37%, rgba(255,249,221,0.38) 48%, rgba(255,255,255,0.08) 54%, transparent 66%)",
            mixBlendMode: "screen",
            opacity: bridgeGlow * 0.9,
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
          top: 62,
          left: 78,
          color: "rgba(249,247,237,0.86)",
          opacity: labelOpacity,
          fontFamily: "Arial, sans-serif",
          fontSize: 22,
          fontWeight: 600,
          letterSpacing: "0.13em",
        }}
      >
        {shot.label}
      </div>
      <div
        style={{
          position: "absolute",
          left: 80,
          bottom: 62,
          width: 270,
          height: 2,
          background: "rgba(231, 211, 166, 0.75)",
          opacity: labelOpacity,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 78,
          bottom: 58,
          color: "rgba(249,247,237,0.64)",
          opacity: labelOpacity,
          fontFamily: "Arial, sans-serif",
          fontSize: 16,
          letterSpacing: "0.08em",
        }}
      >
        NATURAL TRANSITION / V2
      </div>
    </AbsoluteFill>
  );
};

export const BangleI2INaturalTransitionReview: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#111714" }}>
      {shots.map((shot) => <NaturalShot key={shot.id} shot={shot} />)}
    </AbsoluteFill>
  );
};

export const BANGLE_I2I_NATURAL_TRANSITION_DURATION = 24 * FPS;
