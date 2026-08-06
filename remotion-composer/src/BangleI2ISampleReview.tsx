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

type ReviewShot = {
  id: string;
  image: string;
  label: string;
  plan: string;
  start: number;
  duration: number;
  scaleFrom: number;
  scaleTo: number;
  xFrom: number;
  xTo: number;
  yFrom: number;
  yTo: number;
  accent: string;
  status: "ANCHOR" | "CANDIDATE";
};

const shots: ReviewShot[] = [
  {
    id: "anchor",
    image: "02.png",
    label: "IDENTITY ANCHOR / 02.PNG",
    plan: "商品身份基准",
    start: 0,
    duration: 3.8,
    scaleFrom: 1.02,
    scaleTo: 1.09,
    xFrom: 0,
    xTo: -1,
    yFrom: 0,
    yTo: -1,
    accent: "rgba(255, 221, 168, 0.24)",
    status: "ANCHOR",
  },
  {
    id: "angle-three-quarter",
    image: "angle_controlled_three_quarter.png",
    label: "I2I / CONTROLLED THREE-QUARTER",
    plan: "计划角度：受控三分之四低机位",
    start: 3.4,
    duration: 3.8,
    scaleFrom: 1.03,
    scaleTo: 1.1,
    xFrom: 1,
    xTo: -1,
    yFrom: 0,
    yTo: -1,
    accent: "rgba(204, 238, 222, 0.20)",
    status: "CANDIDATE",
  },
  {
    id: "light-soft",
    image: "light_soft_specular_sweep.png",
    label: "I2I / SOFT SPECULAR LIGHT",
    plan: "计划变化：柔和白光与高光",
    start: 6.8,
    duration: 3.8,
    scaleFrom: 1.06,
    scaleTo: 1.14,
    xFrom: -1,
    xTo: 1,
    yFrom: 0,
    yTo: -1,
    accent: "rgba(248, 244, 220, 0.24)",
    status: "CANDIDATE",
  },
  {
    id: "environment-pale",
    image: "environment_pale_stone.png",
    label: "I2I / PALE STONE ENVIRONMENT",
    plan: "计划变化：浅色石材环境",
    start: 10.2,
    duration: 3.8,
    scaleFrom: 1.04,
    scaleTo: 1.11,
    xFrom: 1,
    xTo: -1,
    yFrom: 1,
    yTo: -1,
    accent: "rgba(235, 220, 191, 0.21)",
    status: "CANDIDATE",
  },
  {
    id: "environment-green-gray",
    image: "environment_green_gray_studio.png",
    label: "I2I / GREEN-GRAY STUDIO",
    plan: "计划变化：深绿灰棚拍环境",
    start: 13.6,
    duration: 3.8,
    scaleFrom: 1.03,
    scaleTo: 1.1,
    xFrom: -1,
    xTo: 1,
    yFrom: 0,
    yTo: -1,
    accent: "rgba(185, 222, 196, 0.23)",
    status: "CANDIDATE",
  },
  {
    id: "angle-upright",
    image: "angle_upright_display.png",
    label: "I2I / UPRIGHT DISPLAY TEST",
    plan: "计划角度：竖立展示（当前输出仍为平放）",
    start: 17.0,
    duration: 3.8,
    scaleFrom: 1.04,
    scaleTo: 1.12,
    xFrom: 1,
    xTo: -1,
    yFrom: -1,
    yTo: 1,
    accent: "rgba(242, 213, 163, 0.22)",
    status: "CANDIDATE",
  },
  {
    id: "light-warm",
    image: "light_warm_diffused_lustre.png",
    label: "I2I / WARM DIFFUSED LUSTRE",
    plan: "计划变化：暖色漫射光泽",
    start: 20.4,
    duration: 3.6,
    scaleFrom: 1.03,
    scaleTo: 1.08,
    xFrom: -1,
    xTo: 0,
    yFrom: 0,
    yTo: 0,
    accent: "rgba(255, 224, 170, 0.25)",
    status: "CANDIDATE",
  },
];

const ReviewShot: React.FC<{ shot: ReviewShot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localSeconds = frame / fps - shot.start;
  const progress = interpolate(localSeconds, [0, shot.duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const fadeSeconds = 0.38;
  const fadeIn = interpolate(localSeconds, [0, fadeSeconds], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    localSeconds,
    [shot.duration - fadeSeconds, shot.duration],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = Math.min(fadeIn, fadeOut);
  const scale = interpolate(progress, [0, 1], [shot.scaleFrom, shot.scaleTo]);
  const x = interpolate(progress, [0, 1], [shot.xFrom, shot.xTo]);
  const y = interpolate(progress, [0, 1], [shot.yFrom, shot.yTo]);
  const lightX = interpolate(localSeconds, [0, shot.duration], [-35, 130], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });
  const imageSrc = shot.status === "ANCHOR"
    ? staticFile(`bangle-assets/${shot.image}`)
    : staticFile(`${SAMPLE_ROOT}${shot.image}`);

  return (
    <AbsoluteFill style={{ opacity, overflow: "hidden", background: "#111714" }}>
      <Img
        src={imageSrc}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translate(${x}%, ${y}%) scale(${scale})`,
          filter: "contrast(1.04) saturate(0.94) brightness(0.98)",
        }}
      />
      <AbsoluteFill style={{ background: shot.accent, mixBlendMode: "screen" }} />
      <div
        style={{
          position: "absolute",
          inset: "-25% -40%",
          transform: `translateX(${lightX}%) rotate(-14deg)`,
          background:
            "linear-gradient(90deg, transparent 38%, rgba(255,248,214,0.20) 48%, rgba(255,255,255,0.05) 53%, transparent 64%)",
          mixBlendMode: "screen",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 45%, transparent 48%, rgba(0,0,0,0.34) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 68,
          left: 82,
          color: "rgba(249,247,237,0.94)",
          fontFamily: "Arial, sans-serif",
          fontSize: 27,
          fontWeight: 600,
          letterSpacing: "0.08em",
        }}
      >
        {shot.label}
      </div>
      <div
        style={{
          position: "absolute",
          top: 112,
          left: 84,
          color: "rgba(249,247,237,0.76)",
          fontFamily: "Arial, sans-serif",
          fontSize: 21,
          letterSpacing: "0.04em",
        }}
      >
        {shot.plan}
      </div>
      <div
        style={{
          position: "absolute",
          right: 82,
          top: 72,
          color: shot.status === "ANCHOR" ? "rgba(255,225,168,0.94)" : "rgba(213,239,226,0.92)",
          fontFamily: "Arial, sans-serif",
          fontSize: 18,
          letterSpacing: "0.14em",
        }}
      >
        {shot.status}
      </div>
      <div
        style={{
          position: "absolute",
          left: 84,
          bottom: 68,
          width: 360,
          height: 2,
          background: shot.status === "ANCHOR" ? "#f2c97d" : "#b7dfca",
          opacity: 0.82,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 82,
          bottom: 64,
          color: "rgba(249,247,237,0.72)",
          fontFamily: "Arial, sans-serif",
          fontSize: 17,
          letterSpacing: "0.08em",
        }}
      >
        I2I SAMPLE REVIEW / NO BRAND LAYER
      </div>
    </AbsoluteFill>
  );
};

export const BangleI2ISampleReview: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#111714" }}>
      {shots.map((shot) => <ReviewShot key={shot.id} shot={shot} />)}
    </AbsoluteFill>
  );
};

export const BANGLE_I2I_SAMPLE_REVIEW_DURATION = 24 * FPS;
