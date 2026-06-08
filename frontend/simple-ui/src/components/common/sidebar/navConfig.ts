// Sidebar navigation items and service color palette

import { IconType } from "react-icons";
import { FaMicrophone } from "react-icons/fa";
import {
  IoHomeOutline,
  IoKeyOutline,
  IoLanguageOutline,
  IoSparklesOutline,
  IoVolumeHighOutline,
  IoServerOutline,
  IoDocumentTextOutline,
  IoSwapHorizontalOutline,
  IoGlobeOutline,
  IoPeopleOutline,
  IoRadioOutline,
  IoPricetagOutline,
  IoAppsOutline,
  IoPulseOutline,
  IoNotificationsOutline,
  IoShieldCheckmarkOutline,
  IoFolderOpenOutline,
} from "react-icons/io5";
import { TABS } from "../../../config/constants";
import { getServiceTitle } from "../../../config/serviceMetadata";
import DoubleMicrophoneIcon from "../DoubleMicrophoneIcon";

export type NavColorShade = 50 | 300 | 400 | 600;

export const safeColorMap = {
  [TABS.asr]: {
    50: "#FFE9E2",
    300: "#FFB8A4",
    400: "#FF9C86",
    600: "#FF7A61",
  },
  [TABS.tts]: {
    50: "#EAF0FF",
    300: "#B3C7FF",
    400: "#8CAEFF",
    600: "#668FFF",
  },
  [TABS.nmt]: {
    50: "#E7FAF1",
    300: "#B3EFD4",
    400: "#90E6C0",
    600: "#6AD2A7",
  },
  [TABS.llm]: {
    50: "#FFE6FA",
    300: "#FFB3EB",
    400: "#FF8CDE",
    600: "#F061C8",
  },
  [TABS.pipeline]: {
    50: "#F8F0FA",
    300: "#E4C9EE",
    400: "#D8AFE8",
    600: "#C08BD8",
  },
  [TABS.ocr]: {
    50: "#E5F7F7",
    300: "#B5E8E8",
    400: "#90DDDD",
    600: "#6BC7C7",
  },
  [TABS.transliteration]: {
    50: "#E8FCFA",
    300: "#B5F3EC",
    400: "#8DEBDD",
    600: "#6BD2C1",
  },
  [TABS.languageDetection]: {
    50: "#FFE9EE",
    300: "#FFBBC8",
    400: "#FF9EAF",
    600: "#FF7A8F",
  },
  [TABS.speakerDiarization]: {
    50: "#FFF9E6",
    300: "#FEE5A8",
    400: "#FFDA7A",
    600: "#F5C554",
  },
  [TABS.languageDiarization]: {
    50: "#F3FFE8",
    300: "#D4FFAA",
    400: "#C0FF85",
    600: "#99F45A",
  },
  [TABS.audioLanguageDetection]: {
    50: "#E7F7FF",
    300: "#B3E4FF",
    400: "#89D6FF",
    600: "#63C5FF",
  },
  [TABS.ner]: {
    50: "#F1E8FF",
    300: "#D0BBFF",
    400: "#BA9AFF",
    600: "#9D72FF",
  },
  [TABS.modelManagement]: {
    50: "#FFF1F2",
    300: "#FFC1C7",
    400: "#FF9FA8",
    600: "#FF6B7A",
  },
  [TABS.servicesManagement]: {
    50: "#E0F7FA",
    300: "#80DEEA",
    400: "#4DD0E1",
    600: "#00ACC1",
  },
  [TABS.tenantManagement]: {
    50: "#E0F2F1",
    300: "#80CBC4",
    400: "#4DB6AC",
    600: "#00897B",
  },
  [TABS.logs]: {
    50: "#E8F5E9",
    300: "#81C784",
    400: "#66BB6A",
    600: "#43A047",
  },
  [TABS.traces]: {
    50: "#F3E5F5",
    300: "#BA68C8",
    400: "#AB47BC",
    600: "#8E24AA",
  },
  [TABS.alertsManagement]: {
    50: "#FFF8E1",
    300: "#FFD54F",
    400: "#FFCA28",
    600: "#F9A825",
  },
  [TABS.piiManagement]: {
    50: "#E8EAF6",
    300: "#9FA8DA",
    400: "#7986CB",
    600: "#5C6BC0",
  },
  [TABS.policyManagement]: {
    50: "#E3F2FD",
    300: "#64B5F6",
    400: "#42A5F5",
    600: "#1E88E5",
  },
} as const;

export function getNavItemColor(
  serviceId: string,
  shade: NavColorShade
): string | undefined {
  if (!serviceId) return undefined;
  const entry = safeColorMap[serviceId as keyof typeof safeColorMap];
  if (entry?.[shade]) return entry[shade];
  return shade === 50
    ? "#F7FAFC"
    : shade === 300
      ? "#CBD5E1"
      : shade === 400
        ? "#A0AEC0"
        : "#1A202C";
}

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: IconType;
  iconSize: number;
  iconColor: string;
  requiresAuth?: boolean;
}

export const topNavItems: NavItem[] = [
  {
    id: TABS.home,
    label: "Home",
    path: "/",
    icon: IoHomeOutline,
    iconSize: 10,
    iconColor: "black.500",
    requiresAuth: false,
  },
  {
    id: TABS.modelManagement,
    label: "Model Management",
    path: `/${TABS.modelManagement}`,
    icon: IoServerOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.servicesManagement,
    label: "Services Management",
    path: `/${TABS.servicesManagement}`,
    icon: IoAppsOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.tenantManagement,
    label: "Tenant Management",
    path: `/${TABS.tenantManagement}`,
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.apiKeyManagement,
    label: "API Key Management",
    path: `/${TABS.apiKeyManagement}`,
    icon: IoKeyOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.logs,
    label: "Logs Dashboard",
    path: `/${TABS.logs}`,
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.traces,
    label: "Traces Dashboard",
    path: `/${TABS.traces}`,
    icon: IoPulseOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.alertsManagement,
    label: "Alerts Management",
    path: `/${TABS.alertsManagement}`,
    icon: IoNotificationsOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.piiManagement,
    label: "PII Guardrail",
    path: `/${TABS.piiManagement}`,
    icon: IoShieldCheckmarkOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.policyManagement,
    label: "Policy Management",
    path: `/${TABS.policyManagement}`,
    icon: IoFolderOpenOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
];

export const baseNavItems: NavItem[] = [
  {
    id: TABS.nmt,
    label: getServiceTitle(TABS.nmt),
    path: `/${TABS.nmt}`,
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: false,
  },
  {
    id: TABS.asr,
    label: getServiceTitle(TABS.asr),
    path: `/${TABS.asr}`,
    icon: FaMicrophone,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.tts,
    label: getServiceTitle(TABS.tts),
    path: `/${TABS.tts}`,
    icon: IoVolumeHighOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.llm,
    label: getServiceTitle(TABS.llm),
    path: `/${TABS.llm}`,
    icon: IoSparklesOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.pipeline,
    label: getServiceTitle(TABS.pipeline),
    path: `/${TABS.pipeline}`,
    icon: DoubleMicrophoneIcon,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.ocr,
    label: getServiceTitle(TABS.ocr),
    path: `/${TABS.ocr}`,
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.transliteration,
    label: getServiceTitle(TABS.transliteration),
    path: `/${TABS.transliteration}`,
    icon: IoSwapHorizontalOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.languageDetection,
    label: getServiceTitle(TABS.languageDetection),
    path: `/${TABS.languageDetection}`,
    icon: IoGlobeOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.speakerDiarization,
    label: getServiceTitle(TABS.speakerDiarization),
    path: `/${TABS.speakerDiarization}`,
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.languageDiarization,
    label: getServiceTitle(TABS.languageDiarization),
    path: `/${TABS.languageDiarization}`,
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.audioLanguageDetection,
    label: getServiceTitle(TABS.audioLanguageDetection),
    path: `/${TABS.audioLanguageDetection}`,
    icon: IoRadioOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.ner,
    label: getServiceTitle(TABS.ner),
    path: `/${TABS.ner}`,
    icon: IoPricetagOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
];
