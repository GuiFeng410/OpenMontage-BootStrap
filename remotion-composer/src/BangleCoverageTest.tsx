import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

const FPS = 30;
const asset = (name: string) => staticFile(`bangle-assets/${name}`);
type Shot = { image: string; start: number; duration: number; scale: [number, number]; x: [number, number]; y: [number, number]; accent: string };

const shots: Shot[] = [
  { image: "02.png", start: 0, duration: 2.4, scale: [1.02, 1.12], x: [0, -1], y: [0, -1], accent: "rgba(222,241,231,0.12)" },
  { image: "02.png", start: 2.1, duration: 1.8, scale: [1.24, 1.38], x: [-2, 2], y: [0, -2], accent: "rgba(250,235,191,0.10)" },
  { image: "06.png", start: 3.7, duration: 1.9, scale: [1.15, 1.36], x: [2, -3], y: [1, -1], accent: "rgba(226,246,236,0.14)" },
  { image: "07.png", start: 5.4, duration: 1.8, scale: [1.2, 1.38], x: [-2, 2], y: [0, -1], accent: "rgba(255,245,213,0.10)" },
  { image: "02.png", start: 7.0, duration: 1.9, scale: [1.06, 1.17], x: [1, -1], y: [1, -1], accent: "rgba(246,224,165,0.15)" },
  { image: "04.png", start: 8.7, duration: 2.0, scale: [1.02, 1.18], x: [2, -2], y: [1, -2], accent: "rgba(213,237,224,0.11)" },
  { image: "07.png", start: 10.5, duration: 1.8, scale: [1.3, 1.16], x: [2, -1], y: [-1, 1], accent: "rgba(255,235,189,0.10)" },
  { image: "08.png", start: 12.1, duration: 2.1, scale: [1.03, 1.13], x: [1, -1], y: [0, -1], accent: "rgba(239,215,188,0.08)" },
  { image: "09.png", start: 14.0, duration: 1.8, scale: [1.08, 1.18], x: [-1, 1], y: [0, -1], accent: "rgba(225,236,222,0.09)" },
  { image: "02.png", start: 15.6, duration: 2.0, scale: [1.18, 1.05], x: [-1, 0], y: [-1, 0], accent: "rgba(236,244,224,0.11)" },
  { image: "02.png", start: 17.4, duration: 4.0, scale: [1.07, 1.02], x: [0, 0], y: [0, 0], accent: "rgba(244,226,181,0.08)" },
];

const CoverageShot: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const local = frame / FPS - shot.start;
  const p = interpolate(local, [0, shot.duration], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const opacity = Math.min(
    interpolate(local, [0, 0.24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
    interpolate(local, [shot.duration - 0.24, shot.duration], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
  );
  const lightX = interpolate(local, [0, shot.duration], [-35, 130], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) });
  return <AbsoluteFill style={{ opacity, overflow: "hidden", background: "#111714" }}>
    <Img src={asset(shot.image)} style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover", transform: `translate(${interpolate(p, [0, 1], shot.x)}%, ${interpolate(p, [0, 1], shot.y)}%) scale(${interpolate(p, [0, 1], shot.scale)})`, filter: "contrast(1.05) saturate(0.94) brightness(0.98)" }} />
    <AbsoluteFill style={{ background: shot.accent, mixBlendMode: "screen" }} />
    <div style={{ position: "absolute", inset: "-25% -40%", transform: `translateX(${lightX}%) rotate(-14deg)`, background: "linear-gradient(90deg, transparent 38%, rgba(255,248,214,0.22) 48%, rgba(255,255,255,0.06) 53%, transparent 64%)", mixBlendMode: "screen" }} />
    <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 45%, transparent 48%, rgba(0,0,0,0.34) 100%)" }} />
  </AbsoluteFill>;
};

export const BangleCoverageTest: React.FC = () => {
  const { durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();
  const opening = interpolate(frame, [0, 15, 65, 85], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const closingInfo = interpolate(frame, [540, 585, durationInFrames], [0, 0.85, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ background: "#111714" }}>
    {shots.map((shot, index) => <CoverageShot key={`${shot.image}-${shot.start}-${index}`} shot={shot} />)}
    <div style={{ position: "absolute", left: 92, top: 84, opacity: opening, color: "rgba(249,247,237,0.9)", fontFamily: "Arial, sans-serif", letterSpacing: "0.16em", fontSize: 24, textTransform: "uppercase" }}>Brand / Product Info</div>
    <div style={{ position: "absolute", left: 92, top: 124, width: 210, height: 1, background: "rgba(245,220,165,0.8)", opacity: opening }} />
    <div style={{ position: "absolute", left: 92, bottom: 96, opacity: closingInfo, color: "rgba(249,247,237,0.85)", fontFamily: "Arial, sans-serif", letterSpacing: "0.12em", fontSize: 20 }}>LOGO / COPY RESERVED</div>
  </AbsoluteFill>;
};

export const BANGLE_COVERAGE_TEST_DURATION = 22 * FPS;
