import { METERING } from "../constants";

type MeteringChartColorKey = keyof typeof METERING.COLORS.CHART;
type ServiceCssKey = keyof typeof METERING.SERVICE_CSS_KEYS;
type ServiceColorKey = keyof typeof METERING.COLORS.SERVICE;

function colorAt(colors: readonly string[], index: number): string {
  if (colors.length === 0) return "";
  return colors[index % colors.length] ?? colors[0];
}

export function getMeteringChartColor(key: MeteringChartColorKey): string {
  return METERING.COLORS.CHART[key];
}

export function meteringColorAt(index: number): string {
  return colorAt(METERING.COLORS.RANK, index);
}

export function meteringServiceColor(name: string, index: number): string {
  const serviceKey = METERING.SERVICE_CSS_KEYS[name as ServiceCssKey];
  if (serviceKey) {
    const serviceColor = METERING.COLORS.SERVICE[serviceKey as ServiceColorKey];
    if (serviceColor) return serviceColor;
  }
  return colorAt(METERING.COLORS.PALETTE, index);
}

export function heatmapIntensityColor(intensity: number): string {
  const palette = METERING.COLORS.HEATMAP;
  if (intensity <= 0) return colorAt(palette, 0);
  const idx = Math.min(
    palette.length - 1,
    Math.ceil(intensity * (palette.length - 1)),
  );
  return colorAt(palette, idx);
}

export function heatmapTextColor(intensity: number): string {
  return intensity >= METERING.HEATMAP.INTENSITY_TEXT_THRESHOLD
    ? METERING.COLORS.HEATMAP_TEXT_HIGH
    : "gray.800";
}

/** Legend swatches for the heatmap intensity scale. */
export function getHeatmapLegendColors(): readonly string[] {
  return METERING.HEATMAP.LEGEND_INDICES.map((i) => colorAt(METERING.COLORS.HEATMAP, i));
}
