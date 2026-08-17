import { METERING } from "../config/meteringConstants";

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
