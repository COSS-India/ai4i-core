// Collapsible sidebar component for navigation

import {
  Box,
  Button,
  Collapse,
  Divider,
  Heading,
  Icon,
  Image,
  Text,
  useColorModeValue,
  useMediaQuery,
  VStack,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useState } from "react";
import { IconType } from "react-icons";
import { FaMicrophone } from "react-icons/fa";
import {
  IoGitNetworkOutline,
  IoHomeOutline,
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
  IoChevronDownOutline,
  IoAnalyticsOutline,
  IoPulseOutline,
  IoNotificationsOutline,
} from "react-icons/io5";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import { useFeatureFlag } from "../../hooks/useFeatureFlag";
import { getTenantIdFromToken } from "../../utils/helpers";
import DoubleMicrophoneIcon from "./DoubleMicrophoneIcon";

const safeColorMap = {
  asr: { // Coral → Pastel Coral
    50:  "#FFE9E2",
    300: "#FFB8A4",
    400: "#FF9C86",
    600: "#FF7A61",
  },
  tts: { // Royal Blue → Pastel Blue
    50:  "#EAF0FF",
    300: "#B3C7FF",
    400: "#8CAEFF",
    600: "#668FFF",
  },
  nmt: { // Emerald → Pastel Mint
    50:  "#E7FAF1",
    300: "#B3EFD4",
    400: "#90E6C0",
    600: "#6AD2A7",
  },
  llm: { // Magenta → Pastel Pink/Magenta
    50:  "#FFE6FA",
    300: "#FFB3EB",
    400: "#FF8CDE",
    600: "#F061C8",
  },
  pipeline: { // Purple → Pastel Lilac
    50:  "#F8F0FA",
    300: "#E4C9EE",
    400: "#D8AFE8",
    600: "#C08BD8",
  },
  ocr: { // Teal → Pastel Aqua
    50:  "#E5F7F7",
    300: "#B5E8E8",
    400: "#90DDDD",
    600: "#6BC7C7",
  },
  transliteration: { // Turquoise → Pastel Turquoise
    50:  "#E8FCFA",
    300: "#B5F3EC",
    400: "#8DEBDD",
    600: "#6BD2C1",
  },
  "language-detection": { // Crimson → Pastel Red
    50:  "#FFE9EE",
    300: "#FFBBC8",
    400: "#FF9EAF",
    600: "#FF7A8F",
  },
  "speaker-diarization": { // Amber → Pastel Yellow/Amber
    50:  "#FFF9E6",
    300: "#FEE5A8",
    400: "#FFDA7A",
    600: "#F5C554",
  },
  "language-diarization": { // Lime → Pastel Lime Green
    50:  "#F3FFE8",
    300: "#D4FFAA",
    400: "#C0FF85",
    600: "#99F45A",
  },
  "audio-language-detection": { // Replace gray → Pastel Electric Blue
    50:  "#E7F7FF",
    300: "#B3E4FF",
    400: "#89D6FF",
    600: "#63C5FF",
  },
  ner: { // Indigo → Pastel Indigo/Violet
    50:  "#F1E8FF",
    300: "#D0BBFF",
    400: "#BA9AFF",
    600: "#9D72FF",
  },
  "model-management": { // Rose → Pastel Rose
    50:  "#FFF1F2",
    300: "#FFC1C7",
    400: "#FF9FA8",
    600: "#FF6B7A",
  },
  "services-management": { // Cyan → Pastel Cyan
    50:  "#E0F7FA",
    300: "#80DEEA",
    400: "#4DD0E1",
    600: "#00ACC1",
  },
  "logs": { // Green → Pastel Green
    50:  "#E8F5E9",
    300: "#81C784",
    400: "#66BB6A",
    600: "#43A047",
  },
  "traces": { // Purple → Pastel Purple
    50:  "#F3E5F5",
    300: "#BA68C8",
    400: "#AB47BC",
    600: "#8E24AA",
  },
  "alerts-management": { // Amber/Yellow → Pastel Amber
    50:  "#FFF8E1",
    300: "#FFD54F",
    400: "#FFCA28",
    600: "#F9A825",
  },
};

const getColor = (serviceId: string, shade: 50 | 300 | 400 | 600) => {
  if (!serviceId) return undefined;
  
  // prefer safeColorMap hex values (most robust)
  if (safeColorMap[serviceId as keyof typeof safeColorMap] && safeColorMap[serviceId as keyof typeof safeColorMap][shade]) {
    return safeColorMap[serviceId as keyof typeof safeColorMap][shade];
  }
  
  // final fallback to sensible neutral
  return shade === 50 ? "#F7FAFC" : shade === 300 ? "#CBD5E1" : shade === 400 ? "#A0AEC0" : "#1A202C";
};

interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: IconType;
  iconSize: Number;
  iconColor: string;
  requiresAuth?: boolean;
  featureFlag?: string; // Feature flag name to check
}

// Home and Model Management (always visible)
const topNavItems: NavItem[] = [
  {
    id: "home",
    label: "Home",
    path: "/",
    icon: IoHomeOutline,
    iconSize: 10,
    iconColor: "black.500",
    requiresAuth: false,
  },
  {
    id: "model-management",
    label: "Model Management",
    path: "/model-management",
    icon: IoServerOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "model-management-enabled",
  },
  {
    id: "services-management",
    label: "Services Management",
    path: "/services-management",
    icon: IoAppsOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "services-management-enabled",
  },
  {
    id: "logs",
    label: "Logs Dashboard",
    path: "/logs",
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "traces",
    label: "Traces Dashboard",
    path: "/traces",
    icon: IoPulseOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "alerts-management",
    label: "Alerts Management",
    path: "/alerts-management",
    icon: IoNotificationsOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
];

// Services (grouped under Services section)
const baseNavItems: NavItem[] = [
  {
    id: "asr",
    label: "Automatic Speech Recognition (ASR)",
    path: "/asr",
    icon: FaMicrophone,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "asr-enabled",
  },
  {
    id: "tts",
    label: "Text-to-Speech (TTS)",
    path: "/tts",
    icon: IoVolumeHighOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "tts-enabled",
  },
  {
    id: "nmt",
    label: "Neural Machine Translation (NMT)",
    path: "/nmt",
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: false, // Allow anonymous access with rate limiting
    featureFlag: "nmt-enabled",
  },
  {
    id: "llm",
    label: "Large Language Model (LLM)",
    path: "/llm",
    icon: IoSparklesOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "llm-enabled",
  },
  {
    id: "pipeline",
    label: "Speech to Speech-Pipeline",
    path: "/pipeline",
    icon: DoubleMicrophoneIcon,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "pipeline-enabled",
  },
  {
    id: "ocr",
    label: "Optical Character Recognition (OCR)",
    path: "/ocr",
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "ocr-enabled",
  },
  {
    id: "transliteration",
    label: "Transliteration Service",
    path: "/transliteration",
    icon: IoSwapHorizontalOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "transliteration-enabled",
  },
  {
    id: "language-detection",
    label: "Language Detection",
    path: "/language-detection",
    icon: IoGlobeOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "language-detection-enabled",
  },
  {
    id: "speaker-diarization",
    label: "Speaker Diarization",
    path: "/speaker-diarization",
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "speaker-diarization-enabled",
  },
  {
    id: "language-diarization",
    label: "Language Diarization",
    path: "/language-diarization",
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "language-diarization-enabled",
  },
  {
    id: "audio-language-detection",
    label: "Audio Language Detection",
    path: "/audio-language-detection",
    icon: IoRadioOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "audio-language-detection-enabled",
  },
  {
    id: "ner",
    label: "Named Entity Recognition (NER)",
    path: "/ner",
    icon: IoPricetagOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
    featureFlag: "ner-enabled",
  },
];

const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isServicesExpanded, setIsServicesExpanded] = useState(false);
  const [isMobile] = useMediaQuery("(max-width: 1080px)");
  
  // Check if user is GUEST or USER
  const isGuest = user?.roles?.includes('GUEST') || false;
  const isUser = user?.roles?.includes('USER') || false;

  // Check if user is ADMIN
  const isAdmin = user?.roles?.includes('ADMIN') || false;

  // Feature flags for each service
  const asrEnabled = useFeatureFlag({ flagName: "asr-enabled" });
  const ttsEnabled = useFeatureFlag({ flagName: "tts-enabled" });
  const nmtEnabled = useFeatureFlag({ flagName: "nmt-enabled" });
  const llmEnabled = useFeatureFlag({ flagName: "llm-enabled" });
  const pipelineEnabled = useFeatureFlag({ flagName: "pipeline-enabled" });
  const modelManagementEnabled = useFeatureFlag({ flagName: "model-management-enabled" });
  const servicesManagementEnabled = useFeatureFlag({ flagName: "services-management-enabled" });
  const ocrEnabled = useFeatureFlag({ flagName: "ocr-enabled" });
  const transliterationEnabled = useFeatureFlag({ flagName: "transliteration-enabled" });
  const languageDetectionEnabled = useFeatureFlag({ flagName: "language-detection-enabled" });
  const speakerDiarizationEnabled = useFeatureFlag({ flagName: "speaker-diarization-enabled" });
  const languageDiarizationEnabled = useFeatureFlag({ flagName: "language-diarization-enabled" });
  const audioLanguageDetectionEnabled = useFeatureFlag({ flagName: "audio-language-detection-enabled" });
  const nerEnabled = useFeatureFlag({ flagName: "ner-enabled" });

  // Map feature flags to service IDs
  const featureFlagMap: Record<string, boolean> = {
    "asr-enabled": asrEnabled.isEnabled,
    "tts-enabled": ttsEnabled.isEnabled,
    "nmt-enabled": nmtEnabled.isEnabled,
    "llm-enabled": llmEnabled.isEnabled,
    "pipeline-enabled": pipelineEnabled.isEnabled,
    "model-management-enabled": modelManagementEnabled.isEnabled,
    "services-management-enabled": servicesManagementEnabled.isEnabled,
    "ocr-enabled": ocrEnabled.isEnabled,
    "transliteration-enabled": transliterationEnabled.isEnabled,
    "language-detection-enabled": languageDetectionEnabled.isEnabled,
    "speaker-diarization-enabled": speakerDiarizationEnabled.isEnabled,
    "language-diarization-enabled": languageDiarizationEnabled.isEnabled,
    "audio-language-detection-enabled": audioLanguageDetectionEnabled.isEnabled,
    "ner-enabled": nerEnabled.isEnabled,
  };

  // Get tenant_id from JWT token
  const tenantId = getTenantIdFromToken();

  // Filter top nav items (Home and Model Management)
  const topItems = topNavItems.filter((item) => {
    if (item.id === "home") return true;
    // Hide Model Management and Services Management for GUEST and USER users
    if ((isGuest || isUser) && (item.id === "model-management" || item.id === "services-management")) {
      return false;
    }
    // Hide admin-only items for non-ADMIN users (only alerts-management is admin-only now)
    if (item.id === "alerts-management" && !isAdmin) {
      return false;
    }
    // Hide logs for users without tenant_id (but allow admins to see it)
    if (item.id === "logs" && !tenantId && !isAdmin) {
      return false;
    }
    if (item.featureFlag) {
      return featureFlagMap[item.featureFlag] ?? true;
    }
    return true;
  });

  // Filter service items based on feature flags
  const serviceItems = baseNavItems.filter((item) => {
    if (item.featureFlag) {
      return featureFlagMap[item.featureFlag] ?? true;
    }
    return true;
  });


  const bgColor = useColorModeValue("light.100", "dark.100");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const hoverBgColor = useColorModeValue("gray.50", "gray.900");

  // Hide sidebar on mobile
  if (isMobile) {
    return null;
  }

  return (
    <Box
      position="fixed"
      left={0}
      top={0}
      h="100vh"
      w={isExpanded ? "350px" : "4.5rem"}
      bg={bgColor}
      boxShadow="md"
      zIndex={60}
      transition="width 0.2s ease"
      onMouseEnter={() => {
        setIsExpanded(true);
        setIsServicesExpanded(true);
      }}
      onMouseLeave={() => {
        setIsExpanded(false);
        setIsServicesExpanded(false);
      }}
      borderRight="1px"
      borderColor={borderColor}
    >
      <VStack spacing={3} p={3} h="calc(100vh - 3.5rem)" overflowY="auto">
        {/* Logo Section */}
        <VStack spacing={2} w="full">
          <Box
            cursor="pointer"
            onClick={() => router.push("/")}
            _hover={{ opacity: 0.8 }}
            transition="opacity 0.2s"
            display="flex"
            alignItems="center"
            justifyContent="center"
          >
            <Image
              src="/AI4Inclusion_Logo.svg"
              alt="AI4Inclusion Logo"
              boxSize={isExpanded ? 16 : 10}
              objectFit="contain"
              transition="all 0.2s ease"
            />
          </Box>
        </VStack>

        <Divider />

        {/* Top Navigation Items (Home and Model Management) */}
        <VStack spacing={2} w="full" align="stretch">
          {topItems.map((item) => {
            const isActive = router.pathname === item.path;
            const requiresAuth = item.requiresAuth ?? false;

            const handleClick = async (e: React.MouseEvent) => {
              e.preventDefault();
              if (isLoading) return;
              if (item.path === "/") {
                router.push("/");
                return;
              }
              // Check session expiry before navigation for authenticated routes
              if (requiresAuth) {
                if (!checkSessionExpiry()) return;
              }
              router.push(item.path);
            };

            return (
              <Button
                key={item.id}
                variant="ghost"
                size="sm"
                h="3rem"
                minH="3rem"
                w="full"
                justifyContent={isExpanded ? "flex-start" : "center"}
                leftIcon={
                  isExpanded ? (
                    <Icon
                      as={item.icon}
                      boxSize={5}
                      color={item.id === "home" ? "black" : getColor(item.id, 600)}
                    />
                  ) : undefined
                }
                bg={isActive ? "gray.200" : "transparent"}
                color={isActive ? "gray.800" : "gray.700"}
                boxShadow={isActive ? "sm" : "none"}
                onClick={handleClick}
                _hover={{
                  bg: isActive ? "gray.200" : hoverBgColor,
                  transform: "translateY(-1px)",
                }}
                transition="all 0.2s"
                px={isExpanded ? 3 : 0}
              >
                {isExpanded ? (
                  <Heading size="sm" color="gray.800" fontWeight="medium" whiteSpace="pre-line">
                    {item.label}
                  </Heading>
                ) : (
                  <Icon
                    as={item.icon}
                    boxSize={6}
                    color={item.id === "home" ? "black" : getColor(item.id, 600)}
                  />
                )}
              </Button>
            );
          })}
        </VStack>

        <Divider />

        {/* Services Section */}
        <VStack spacing={2} w="full" align="stretch" flex={1}>
          {/* Services Header */}
          <Box
            onMouseEnter={() => {
              if (isExpanded) {
                setIsServicesExpanded(true);
              }
            }}
            onMouseLeave={() => {
              if (!isExpanded) {
                setIsServicesExpanded(false);
              }
            }}
          >
            <Button
              variant="ghost"
              size="sm"
              h="3rem"
              minH="3rem"
              w="full"
              justifyContent={isExpanded ? "flex-start" : "center"}
              leftIcon={
                isExpanded ? (
                  <Icon as={IoAppsOutline} boxSize={5} color="gray.600" />
                ) : undefined
              }
              rightIcon={
                isExpanded ? (
                  <Icon
                    as={IoChevronDownOutline}
                    boxSize={4}
                    color="gray.600"
                    transform={isServicesExpanded ? "rotate(180deg)" : "rotate(0deg)"}
                    transition="transform 0.2s"
                  />
                ) : undefined
              }
              bg="transparent"
              color="gray.700"
              _hover={{
                bg: hoverBgColor,
                transform: "translateY(-1px)",
              }}
              transition="all 0.2s"
              px={isExpanded ? 3 : 0}
              onClick={() => isExpanded && setIsServicesExpanded(!isServicesExpanded)}
            >
              {isExpanded ? (
                <Heading size="sm" color="gray.800" fontWeight="medium">
                  Services
                </Heading>
              ) : (
                <Icon as={IoAppsOutline} boxSize={6} color="gray.600" />
              )}
            </Button>
          </Box>

          {/* Services List */}
          <Collapse in={isExpanded && isServicesExpanded} animateOpacity style={{ paddingTop: "10px" }}>
            <VStack spacing={1} w="full" align="stretch" pl={isExpanded ? 4 : 0}>
              {serviceItems.map((item) => {
                const isActive = router.pathname === item.path;
                const requiresAuth = item.requiresAuth ?? false;

                const handleClick = async (e: React.MouseEvent) => {
                  e.preventDefault();
                  if (isLoading) return;
                  // Check session expiry before navigation for authenticated routes
                  if (requiresAuth) {
                    if (!checkSessionExpiry()) return;
                  }
                  router.push(item.path);
                };

                return (
                  <Button
                    key={item.id}
                    variant="ghost"
                    size="sm"
                    h="2.5rem"
                    minH="2.5rem"
                    w="full"
                    justifyContent="flex-start"
                    leftIcon={
                      <Icon
                        as={item.icon}
                        boxSize={4}
                        color={getColor(item.id, 600)}
                      />
                    }
                    bg={isActive ? "gray.200" : "transparent"}
                    color={isActive ? "gray.800" : "gray.700"}
                    boxShadow={isActive ? "sm" : "none"}
                    borderLeft={isActive ? "3px solid" : "3px solid transparent"}
                    borderLeftColor={isActive ? getColor(item.id, 600) : "transparent"}
                    borderRadius="md"
                    onClick={handleClick}
                    _hover={{
                      bg: isActive ? "gray.200" : hoverBgColor,
                      transform: "translateY(-1px)",
                      borderLeftColor: getColor(item.id, 600),
                      borderLeft: "3px solid",
                    }}
                    transition="all 0.2s"
                    px={1}
                  >
                    <Text fontSize="sm" color="gray.800" fontWeight="medium" whiteSpace="pre-line">
                      {item.label}
                    </Text>
                  </Button>
                );
              })}
            </VStack>
          </Collapse>
        </VStack>
      </VStack>
    </Box>
  );
};

export default Sidebar;
