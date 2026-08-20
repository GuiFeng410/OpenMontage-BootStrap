import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type ChangeDirection = "up" | "down" | "neutral";

export interface ComparisonColumn {
  label: string;
  value: string;
  color?: string;
}

const DEFAULT_COLUMN_COLORS = [
  "#2563EB",
  "#10B981",
  "#F59E0B",
  "#EC4899",
];

const MAX_COLUMNS = 4;

interface ComparisonCardProps {
  /** Dual-column API (compat). Required unless `columns` has length >= 2. */
  leftLabel?: string;
  rightLabel?: string;
  leftValue?: string;
  rightValue?: string;
  leftColor?: string;
  rightColor?: string;
  /**
   * Multi-column layout. When length >= 2, overrides dual-column API.
   * Hard cap: 4 columns (extras sliced with console warning).
   */
  columns?: ComparisonColumn[];
  title?: string;
  changeIndicator?: string;
  changeDirection?: ChangeDirection;
  backgroundColor?: string;
  cardBackgroundColor?: string;
  textColor?: string;
  fontFamily?: string;
  titleFontSize?: number;
  labelFontSize?: number;
  valueFontSize?: number;
}

function resolveColumns(props: ComparisonCardProps): ComparisonColumn[] | null {
  if (props.columns && props.columns.length >= 2) {
    if (props.columns.length > MAX_COLUMNS) {
      console.warn(
        `[ComparisonCard] columns.length=${props.columns.length} exceeds max ${MAX_COLUMNS}; slicing extras.`
      );
    }
    return props.columns.slice(0, MAX_COLUMNS);
  }
  if (
    props.leftLabel &&
    props.rightLabel &&
    props.leftValue !== undefined &&
    props.rightValue !== undefined
  ) {
    return [
      {
        label: props.leftLabel,
        value: props.leftValue,
        color: props.leftColor ?? DEFAULT_COLUMN_COLORS[0],
      },
      {
        label: props.rightLabel,
        value: props.rightValue,
        color: props.rightColor ?? DEFAULT_COLUMN_COLORS[1],
      },
    ];
  }
  return null;
}

export const ComparisonCard: React.FC<ComparisonCardProps> = ({
  leftLabel,
  rightLabel,
  leftValue,
  rightValue,
  leftColor = "#2563EB",
  rightColor = "#10B981",
  columns: columnsProp,
  title,
  changeIndicator,
  changeDirection = "neutral",
  backgroundColor = "#FFFFFF",
  cardBackgroundColor = "#F3F4F6",
  textColor = "#1F2937",
  fontFamily = "Inter, system-ui, sans-serif",
  titleFontSize = 44,
  labelFontSize = 28,
  valueFontSize = 72,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const columns = resolveColumns({
    leftLabel,
    rightLabel,
    leftValue,
    rightValue,
    leftColor,
    rightColor,
    columns: columnsProp,
  });

  const titleOpacity = spring({
    frame,
    fps,
    config: { damping: 20 },
  });

  // Dual-column change indicator only (legacy)
  const isDual = columns !== null && columns.length === 2 && !columnsProp;
  const dividerDraw = spring({
    frame: frame - 16,
    fps,
    config: { damping: 14, stiffness: 80 },
  });
  const indicatorOpacity = spring({
    frame: frame - 32,
    fps,
    config: { damping: 15 },
  });
  const indicatorScale = spring({
    frame: frame - 32,
    fps,
    config: { damping: 10, stiffness: 130 },
    from: 0.6,
    to: 1,
  });

  const directionArrow =
    changeDirection === "up"
      ? "\u2191"
      : changeDirection === "down"
        ? "\u2193"
        : "\u2194";
  const directionColor =
    changeDirection === "up"
      ? "#10B981"
      : changeDirection === "down"
        ? "#EF4444"
        : "#9CA3AF";

  const scaledValueFontSize =
    columns && columns.length >= 3
      ? Math.round(valueFontSize * (columns.length === 4 ? 0.72 : 0.85))
      : valueFontSize;
  const scaledLabelFontSize =
    columns && columns.length >= 3
      ? Math.round(labelFontSize * 0.9)
      : labelFontSize;

  if (!columns) {
    return (
      <AbsoluteFill
        style={{
          background: backgroundColor,
          justifyContent: "center",
          alignItems: "center",
        }}
      />
    );
  }

  const useMultiLayout = Boolean(columnsProp && columnsProp.length >= 2);

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: "80%",
          maxWidth: 1540,
          gap: 32,
        }}
      >
        {title && (
          <div
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: titleFontSize,
              color: textColor,
              textAlign: "center",
              opacity: titleOpacity,
              letterSpacing: "-0.02em",
            }}
          >
            {title}
          </div>
        )}

        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "stretch",
            width: "100%",
            borderRadius: 16,
            backgroundColor: cardBackgroundColor,
            overflow: "hidden",
            boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
            minHeight: 280,
          }}
        >
          {columns.map((col, idx) => {
            const color =
              col.color || DEFAULT_COLUMN_COLORS[idx % DEFAULT_COLUMN_COLORS.length];
            const stagger = 6 + idx * 10;
            const opacity = spring({
              frame: frame - stagger,
              fps,
              config: { damping: 18 },
            });
            const slide = spring({
              frame: frame - stagger,
              fps,
              config: { damping: 14, stiffness: 90 },
              from: -28,
              to: 0,
            });
            const scale = spring({
              frame: frame - stagger,
              fps,
              config: { damping: 12, stiffness: 100 },
              from: 0.9,
              to: 1,
            });

            const showLegacyDivider =
              !useMultiLayout && isDual && idx === 0 && columns.length === 2;

            return (
              <div
                key={`col-${idx}-${col.label}`}
                style={{
                  display: "flex",
                  flexDirection: "row",
                  flex: 1,
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                    alignItems: "center",
                    padding: columns.length >= 4 ? "40px 16px" : "48px 32px",
                    opacity,
                    transform: `translateX(${slide}px) scale(${scale})`,
                    gap: 16,
                  }}
                >
                  <div
                    style={{
                      width: 48,
                      height: 4,
                      backgroundColor: color,
                      borderRadius: 2,
                      marginBottom: 8,
                    }}
                  />
                  <div
                    style={{
                      fontFamily,
                      fontWeight: 600,
                      fontSize: scaledLabelFontSize,
                      color: textColor,
                      opacity: 0.7,
                      textTransform: "uppercase" as const,
                      letterSpacing: "0.05em",
                      textAlign: "center",
                    }}
                  >
                    {col.label}
                  </div>
                  <div
                    style={{
                      fontFamily,
                      fontWeight: 800,
                      fontSize: scaledValueFontSize,
                      color,
                      lineHeight: 1.1,
                      textAlign: "center",
                    }}
                  >
                    {col.value}
                  </div>
                </div>

                {/* Legacy dual-column center divider + change indicator */}
                {showLegacyDivider && (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 80,
                      position: "relative",
                      flexShrink: 0,
                    }}
                  >
                    <div
                      style={{
                        width: 2,
                        height: `${dividerDraw * 100}%`,
                        backgroundColor: "#D1D5DB",
                        position: "absolute",
                        top: `${((1 - dividerDraw) / 2) * 100}%`,
                      }}
                    />
                    {changeIndicator && (
                      <div
                        style={{
                          position: "relative",
                          zIndex: 1,
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          gap: 4,
                          opacity: indicatorOpacity,
                          transform: `scale(${indicatorScale})`,
                        }}
                      >
                        <div
                          style={{
                            width: 48,
                            height: 48,
                            borderRadius: 24,
                            backgroundColor,
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                            boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
                          }}
                        >
                          <span
                            style={{
                              fontFamily,
                              fontWeight: 700,
                              fontSize: 24,
                              color: directionColor,
                            }}
                          >
                            {directionArrow}
                          </span>
                        </div>
                        <div
                          style={{
                            fontFamily,
                            fontWeight: 700,
                            fontSize: 18,
                            color: directionColor,
                            whiteSpace: "nowrap" as const,
                          }}
                        >
                          {changeIndicator}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Thin dividers between multi-columns */}
                {useMultiLayout && idx < columns.length - 1 && (
                  <div
                    style={{
                      width: 1,
                      alignSelf: "stretch",
                      backgroundColor: "rgba(148,163,184,0.35)",
                      flexShrink: 0,
                      opacity: spring({
                        frame: frame - (stagger + 8),
                        fps,
                        config: { damping: 16 },
                      }),
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
