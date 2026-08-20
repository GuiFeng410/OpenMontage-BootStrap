import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  Video,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FPS = 30;
const SHOT_SECONDS = 4;
const AI_INSERTS_ENABLED = true;

type Shot = {
  id: string;
  image: string;
  start: number;
  aiVideo?: string;
  scale: [number, number];
  x: [number, number];
  y: [number, number];
  objectPosition: string;
  accent: string;
  lightBridge?: boolean;
};

const shots: Shot[] = [
  { id: "01", image: "02.png", start: 0, scale: [1.05, 1.18], x: [0, -1.2], y: [0, -0.6], objectPosition: "50% 55%", accent: "rgba(255,221,168,.12)" },
  { id: "02", image: "02.png", start: 4, scale: [1.14, 1.30], x: [-1.2, .8], y: [-.6, -1.3], objectPosition: "50% 54%", accent: "rgba(248,224,182,.10)" },
  { id: "03", image: "06.png", start: 8, scale: [1.18, 1.34], x: [.8, -1.1], y: [-1.3, -.2], objectPosition: "50% 50%", accent: "rgba(207,237,222,.10)" },
  { id: "04", image: "07.png", start: 12, scale: [1.18, 1.06], x: [-1.1, 1.0], y: [-.2, -.9], objectPosition: "50% 50%", accent: "rgba(248,235,199,.09)" },
  { id: "05", image: "02.png", start: 16, scale: [1.06, 1.20], x: [1.0, -.8], y: [-.9, -.1], objectPosition: "50% 52%", accent: "rgba(247,244,221,.12)", lightBridge: true },
  { id: "06", image: "04.png", start: 20, scale: [1.08, 1.24], x: [-.8, .7], y: [-.1, -.7], objectPosition: "50% 50%", accent: "rgba(213,237,224,.10)" },
  { id: "07", image: "04.png", start: 24, aiVideo: "angle_pale_v3_4s.mp4", scale: [1.04, 1.12], x: [.7, -.2], y: [-.7, -.3], objectPosition: "50% 50%", accent: "rgba(203,231,219,.09)" },
  { id: "08", image: "04.png", start: 28, scale: [1.14, 1.05], x: [-.2, -1.0], y: [-.3, .2], objectPosition: "50% 50%", accent: "rgba(203,231,219,.08)" },
  { id: "09", image: "04.png", start: 32, aiVideo: "diagonal_pale_v3_4s.mp4", scale: [1.04, 1.16], x: [-1.0, .5], y: [.2, -.5], objectPosition: "50% 52%", accent: "rgba(235,221,195,.10)", lightBridge: true },
  { id: "10", image: "09.png", start: 36, scale: [1.06, 1.18], x: [.5, -1.0], y: [-.5, -.1], objectPosition: "50% 50%", accent: "rgba(230,218,197,.08)" },
  { id: "11", image: "08.png", start: 40, scale: [1.08, 1.22], x: [-1.0, .4], y: [-.1, -.8], objectPosition: "50% 50%", accent: "rgba(239,215,188,.08)" },
  { id: "12", image: "09.png", start: 44, scale: [1.06, 1.16], x: [.4, -.5], y: [-.8, -.2], objectPosition: "50% 50%", accent: "rgba(230,218,197,.08)" },
  { id: "13", image: "02.png", start: 48, scale: [1.20, 1.08], x: [-.5, .8], y: [-.2, -.7], objectPosition: "50% 55%", accent: "rgba(247,230,190,.11)", lightBridge: true },
  { id: "14", image: "02.png", start: 52, scale: [1.06, 1.14], x: [.8, -.1], y: [-.7, -.1], objectPosition: "50% 55%", accent: "rgba(255,213,157,.13)" },
  { id: "15", image: "02.png", start: 56, scale: [1.10, 1.03], x: [-.1, 0], y: [-.1, 0], objectPosition: "50% 56%", accent: "rgba(255,221,168,.10)" },
];

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const MotionShot: React.FC<{ shot: Shot; index: number }> = ({ shot, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localSeconds = frame / fps;
  const progress = interpolate(localSeconds, [0, SHOT_SECONDS], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const transitionSeconds = index === 0 ? 0.2 : 0.52;
  const transitionProgress = clamp01(localSeconds / transitionSeconds);
  const scale = interpolate(progress, [0, 1], shot.scale);
  const x = interpolate(progress, [0, 1], shot.x);
  const y = interpolate(progress, [0, 1], shot.y);
  const diagonalClip = index === 0
    ? undefined
    : `polygon(0 0, 100% 0, 100% ${transitionProgress * 100}%, ${transitionProgress * 100}% 100%, 0 100%)`;
  const lightProgress = clamp01(localSeconds / 1.15);
  const lightX = interpolate(lightProgress, [0, 1], [-120, 120], { easing: Easing.inOut(Easing.quad) });
  const imageSrc = staticFile(`bangle-assets/${shot.image}`);
  const videoSrc = shot.aiVideo ? staticFile(`bangle-assets/agnes/${shot.aiVideo}`) : undefined;

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: index === 0 ? "#111714" : "transparent", clipPath: diagonalClip }}>
      <Img
        src={imageSrc}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: shot.objectPosition,
          transform: `translate(${x}%, ${y}%) scale(${scale})`,
          filter: "contrast(1.04) saturate(.94) brightness(.99)",
        }}
      />
      {AI_INSERTS_ENABLED && videoSrc ? (
        <Video
          src={videoSrc}
          muted
          volume={0}
          style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
      <AbsoluteFill style={{ background: shot.accent, mixBlendMode: "screen" }} />
      {shot.lightBridge ? (
        <div
          style={{
            position: "absolute",
            inset: "-30% -45%",
            transform: `translateX(${lightX}%) rotate(-14deg)`,
            background: "linear-gradient(90deg, transparent 39%, rgba(255,249,221,.22) 49%, rgba(255,255,255,.05) 55%, transparent 66%)",
            mixBlendMode: "screen",
            opacity: Math.sin(lightProgress * Math.PI) * .72,
          }}
        />
      ) : null}
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at 50% 46%, transparent 50%, rgba(0,0,0,.30) 100%)",
          opacity: .72,
        }}
      />
    </AbsoluteFill>
  );
};

export const Bangle60sMotionStructureV5: React.FC = () => (
  <AbsoluteFill style={{ background: "#111714" }}>
    {shots.map((shot, index) => (
      <Sequence
        key={shot.id}
        from={shot.start * FPS}
        durationInFrames={Math.round((SHOT_SECONDS + .52) * FPS)}
        premountFor={12}
        style={{ zIndex: index }}
      >
        <MotionShot shot={shot} index={index} />
      </Sequence>
    ))}
  </AbsoluteFill>
);

export const BANGLE_60S_MOTION_STRUCTURE_V5_DURATION = 60 * FPS;
