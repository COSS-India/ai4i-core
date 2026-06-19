import { METERING } from "../config/meteringConstants";

type MeteringChartColorKey = keyof typeof METERING.COLORS.CHART;

export function getMeteringChartColor(key: MeteringChartColorKey): string {
  return METERING.COLORS.CHART[key];
}

export function meteringColorAt(index: number): string {
  const colors = METERING.COLORS.RANK;
  return colors[index % colors.length]!;
}

export function meteringServiceColor(name: string, index: number): string {
  const cssKey = METERING.SERVICE_CSS_KEYS[name as keyof typeof METERING.SERVICE_CSS_KEYS];
  if (cssKey) {
    const serviceColor = METERING.COLORS.SERVICE[cssKey as keyof typeof METERING.COLORS.SERVICE];
    if (serviceColor) return serviceColor;
  }
  const palette = METERING.COLORS.PALETTE;
  return palette[index % palette.length]!;
}

export function heatmapIntensityColor(intensity: number): string {
  const palette = METERING.COLORS.HEATMAP;
  if (intensity <= 0) return palette[0]!;
  const idx = Math.min(
    palette.length - 1,
    Math.ceil(intensity * (palette.length - 1)),
  );
  return palette[idx]!;
}

export function heatmapTextColor(intensity: number): string {
  return intensity >= METERING.HEATMAP.INTENSITY_TEXT_THRESHOLD
    ? METERING.COLORS.HEATMAP_TEXT_HIGH
    : "gray.800";
}

/** Legend swatches for the heatmap intensity scale. */
export function getHeatmapLegendColors(): readonly string[] {
  return METERING.HEATMAP.LEGEND_INDICES.map((i) => METERING.COLORS.HEATMAP[i]!);
}
