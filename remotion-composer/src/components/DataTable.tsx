import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/** Visual rows = 1 header + up to 5 data rows. */
export const DATA_TABLE_MAX_COLS = 5;
export const DATA_TABLE_MAX_DATA_ROWS = 5;

export interface DataTableProps {
  /** Column headers (required). Cap: 5. */
  headers: string[];
  /** Data rows (required). Cap: 5 rows; each row cells aligned to headers. */
  rows: string[][];
  title?: string;
  backgroundColor?: string;
  /** Table surface — pass theme.surfaceColor for dark themes (avoid bare #1F2937 text defaults). */
  cardBackgroundColor?: string;
  textColor?: string;
  mutedTextColor?: string;
  accentColor?: string;
  headerBackgroundColor?: string;
  fontFamily?: string;
  titleFontSize?: number;
  cellFontSize?: number;
  headerFontSize?: number;
}

function clampTable(
  headers: string[],
  rows: string[][]
): { headers: string[]; rows: string[][] } {
  let nextHeaders = headers;
  if (headers.length > DATA_TABLE_MAX_COLS) {
    console.warn(
      `[DataTable] headers.length=${headers.length} exceeds max ${DATA_TABLE_MAX_COLS}; slicing extras.`
    );
    nextHeaders = headers.slice(0, DATA_TABLE_MAX_COLS);
  }
  let nextRows = rows;
  if (rows.length > DATA_TABLE_MAX_DATA_ROWS) {
    console.warn(
      `[DataTable] rows.length=${rows.length} exceeds max ${DATA_TABLE_MAX_DATA_ROWS}; slicing extras.`
    );
    nextRows = rows.slice(0, DATA_TABLE_MAX_DATA_ROWS);
  }
  const colCount = nextHeaders.length;
  nextRows = nextRows.map((row, ri) => {
    if (row.length > colCount) {
      console.warn(
        `[DataTable] row[${ri}].length=${row.length} exceeds headers (${colCount}); slicing extras.`
      );
    }
    const padded = [...row];
    while (padded.length < colCount) padded.push("");
    return padded.slice(0, colCount);
  });
  return { headers: nextHeaders, rows: nextRows };
}

export const DataTable: React.FC<DataTableProps> = ({
  headers: headersProp,
  rows: rowsProp,
  title,
  backgroundColor = "#FFFFFF",
  cardBackgroundColor = "#F3F4F6",
  textColor = "#1F2937",
  mutedTextColor = "#6B7280",
  accentColor = "#2563EB",
  headerBackgroundColor,
  fontFamily = "Inter, system-ui, sans-serif",
  titleFontSize = 40,
  cellFontSize = 26,
  headerFontSize = 24,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const { headers, rows } = clampTable(headersProp || [], rowsProp || []);
  const colCount = Math.max(headers.length, 1);

  const titleOpacity = spring({
    frame,
    fps,
    config: { damping: 20 },
  });

  const headerOpacity = spring({
    frame: frame - 6,
    fps,
    config: { damping: 18 },
  });
  const headerSlide = spring({
    frame: frame - 6,
    fps,
    config: { damping: 14, stiffness: 90 },
    from: -16,
    to: 0,
  });

  const headerBg = headerBackgroundColor || cardBackgroundColor;
  const borderColor = "rgba(148, 163, 184, 0.35)";

  if (headers.length === 0) {
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
          width: "88%",
          maxWidth: 1600,
          gap: 28,
        }}
      >
        {title ? (
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
        ) : null}

        <div
          style={{
            width: "100%",
            borderRadius: 16,
            backgroundColor: cardBackgroundColor,
            overflow: "hidden",
            boxShadow: "0 2px 12px rgba(0,0,0,0.12)",
            border: `1px solid ${borderColor}`,
          }}
        >
          {/* Header row — enters first */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))`,
              backgroundColor: headerBg,
              boxShadow: `inset 0 -2px 0 ${accentColor}`,
              opacity: headerOpacity,
              transform: `translateY(${headerSlide}px)`,
            }}
          >
            {headers.map((h, i) => (
              <div
                key={`h-${i}`}
                style={{
                  fontFamily,
                  fontWeight: 700,
                  fontSize: headerFontSize,
                  color: mutedTextColor,
                  padding: "18px 20px",
                  textAlign: "left",
                  letterSpacing: "0.04em",
                  textTransform: "uppercase" as const,
                  borderRight:
                    i < colCount - 1 ? `1px solid ${borderColor}` : undefined,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap" as const,
                }}
              >
                {h}
              </div>
            ))}
          </div>

          {/* Data rows — stagger top → bottom */}
          {rows.map((row, ri) => {
            const stagger = 16 + ri * 8;
            const opacity = spring({
              frame: frame - stagger,
              fps,
              config: { damping: 18 },
            });
            const slide = spring({
              frame: frame - stagger,
              fps,
              config: { damping: 14, stiffness: 90 },
              from: -20,
              to: 0,
            });
            return (
              <div
                key={`r-${ri}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))`,
                  backgroundColor:
                    ri % 2 === 1 ? "rgba(148, 163, 184, 0.08)" : "transparent",
                  borderBottom:
                    ri < rows.length - 1
                      ? `1px solid ${borderColor}`
                      : undefined,
                  opacity,
                  transform: `translateY(${slide}px)`,
                }}
              >
                {row.map((cell, ci) => (
                  <div
                    key={`c-${ri}-${ci}`}
                    style={{
                      fontFamily,
                      fontWeight: 500,
                      fontSize: cellFontSize,
                      color: textColor,
                      padding: "16px 20px",
                      textAlign: "left",
                      borderRight:
                        ci < colCount - 1
                          ? `1px solid ${borderColor}`
                          : undefined,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap" as const,
                    }}
                  >
                    {cell}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
