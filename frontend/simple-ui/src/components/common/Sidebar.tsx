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
  VStack,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useCallback, useMemo, useState } from "react";
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
  IoChevronDownOutline,
  IoPulseOutline,
  IoNotificationsOutline,
  IoShieldCheckmarkOutline,
  IoFolderOpenOutline,
} from "react-icons/io5";
import { getServiceTitle } from "../../config/serviceMetadata";
import { useAuth } from "../../hooks/useAuth";
import { useGuestServices } from "../../hooks/useGuestServices";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
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
  "tenant-management": { // Teal → Pastel Teal
    50:  "#E0F2F1",
    300: "#80CBC4",
    400: "#4DB6AC",
    600: "#00897B",
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
  "pii-management": {
    50:  "#E8EAF6",
    300: "#9FA8DA",
    400: "#7986CB",
    600: "#5C6BC0",
  },
  "policy-management": {
    50:  "#E3F2FD",
    300: "#64B5F6",
    400: "#42A5F5",
    600: "#1E88E5",
  },
};

const getColor = (serviceId: string, shade: 50 | 300 | 400 | 600) => {
  if (!serviceId) return undefined;
  const entry = safeColorMap[serviceId as keyof typeof safeColorMap];
  if (entry?.[shade]) return entry[shade];
  return shade === 50 ? "#F7FAFC" : shade === 300 ? "#CBD5E1" : shade === 400 ? "#A0AEC0" : "#1A202C";
};

interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: IconType;
  iconSize: number;
  iconColor: string;
  requiresAuth?: boolean;
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
  },
  {
    id: "services-management",
    label: "Services Management",
    path: "/services-management",
    icon: IoAppsOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "tenant-management",
    label: "Tenant Management",
    path: "/tenant-management",
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "api-key-management",
    label: "API Key Management",
    path: "/api-key-management",
    icon: IoKeyOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
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
  {
    id: "pii-management",
    label: "PII Guardrail",
    path: "/pii-management",
    icon: IoShieldCheckmarkOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: "policy-management",
    label: "Policy Management",
    path: "/policy-management",
    icon: IoFolderOpenOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
];

// Services (grouped under Services section) — order matches homepage (index.tsx services array)
const baseNavItems: NavItem[] = [
  {
    id: "nmt",
    label: getServiceTitle("nmt"),
    path: "/nmt",
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: false, // Allow anonymous access with rate limiting
  },
  {
    id: "asr",
    label: getServiceTitle("asr"),
    path: "/asr",
    icon: FaMicrophone,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "tts",
    label: getServiceTitle("tts"),
    path: "/tts",
    icon: IoVolumeHighOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "llm",
    label: getServiceTitle("llm"),
    path: "/llm",
    icon: IoSparklesOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "pipeline",
    label: getServiceTitle("pipeline"),
    path: "/pipeline",
    icon: DoubleMicrophoneIcon,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "ocr",
    label: getServiceTitle("ocr"),
    path: "/ocr",
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "transliteration",
    label: getServiceTitle("transliteration"),
    path: "/transliteration",
    icon: IoSwapHorizontalOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "language-detection",
    label: getServiceTitle("language-detection"),
    path: "/language-detection",
    icon: IoGlobeOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "speaker-diarization",
    label: getServiceTitle("speaker-diarization"),
    path: "/speaker-diarization",
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "language-diarization",
    label: getServiceTitle("language-diarization"),
    path: "/language-diarization",
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "audio-language-detection",
    label: getServiceTitle("audio-language-detection"),
    path: "/audio-language-detection",
    icon: IoRadioOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: "ner",
    label: getServiceTitle("ner"),
    path: "/ner",
    icon: IoPricetagOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
];

const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isLoading, user } = useAuth();
  const { isGuest: isGuestFromAccess, isLoading: guestServicesLoading, allowedServiceIds } = useGuestServices();
  const { checkSessionExpiry } = useSessionExpiry();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isServicesExpanded, setIsServicesExpanded] = useState(false);

  // Check if user is GUEST or USER
  const isGuest = user?.roles?.includes('GUEST') || false;
  const isUser = user?.roles?.includes('USER') || false;

  // Check if user is ADMIN
  const isAdmin = user?.roles?.includes('ADMIN') || false;

  // Check if user is TENANT ADMIN
  const isTenantAdmin = user?.roles?.some((role) => (role ?? "").trim().toUpperCase() === 'TENANT ADMIN') || false;

  // Show Tenant Management to admins and tenant admins
  const showTenantManagement = isAdmin || isTenantAdmin;

  // Get tenant_id from JWT token
  const tenantId = getTenantIdFromToken();

  const topItems = useMemo(
    () =>
      topNavItems.filter((item) => {
        if (item.id === "home") return true;
        if (item.id === "traces") return false;
        if (
          (isGuest || isUser || isTenantAdmin) &&
          (item.id === "model-management" || item.id === "services-management")
        ) {
          return false;
        }
        if (item.id === "tenant-management" && !showTenantManagement) return false;
        if (item.id === "alerts-management" && !isAdmin) return false;
        if (item.id === "pii-management" && !(isAdmin || isTenantAdmin)) return false;
        if (item.id === "policy-management" && !isAdmin) return false;
        if (item.id === "api-key-management" && !(isAdmin || isTenantAdmin)) return false;
        if (item.id === "logs" && (isUser || isGuest)) return false;
        if (item.id === "logs" && !tenantId && !isAdmin) return false;
        return true;
      }),
    [
      isAdmin,
      isGuest,
      isUser,
      isTenantAdmin,
      showTenantManagement,
      tenantId,
    ],
  );

  const serviceItems = useMemo(
    () =>
      baseNavItems.filter((item) => {
        if (isGuestFromAccess || isGuest) {
          if (guestServicesLoading) return false;
          if (!allowedServiceIds?.has(item.id)) return false;
        }
        return true;
      }),
    [
      allowedServiceIds,
      guestServicesLoading,
      isGuest,
      isGuestFromAccess,
    ],
  );

  const handleSidebarMouseEnter = useCallback(() => {
    setIsExpanded(true);
    setIsServicesExpanded(true);
  }, []);

  const handleSidebarMouseLeave = useCallback(() => {
    setIsExpanded(false);
    setIsServicesExpanded(false);
  }, []);

  const goHome = useCallback(() => {
    router.push("/");
  }, [router]);

  const onTopNavClick = useCallback(
    (e: React.MouseEvent, path: string, requiresAuth: boolean) => {
      e.preventDefault();
      if (isLoading) return;
      if (path === "/") {
        router.push("/");
        return;
      }
      if (requiresAuth && !checkSessionExpiry()) return;
      router.push(path);
    },
    [checkSessionExpiry, isLoading, router],
  );

  const onServiceNavClick = useCallback(
    (e: React.MouseEvent, path: string, requiresAuth: boolean) => {
      e.preventDefault();
      if (isLoading) return;
      if (requiresAuth && !checkSessionExpiry()) return;
      router.push(path);
    },
    [checkSessionExpiry, isLoading, router],
  );

  const handleServicesSectionMouseEnter = useCallback(() => {
    if (isExpanded) setIsServicesExpanded(true);
  }, [isExpanded]);

  const handleServicesSectionMouseLeave = useCallback(() => {
    if (!isExpanded) setIsServicesExpanded(false);
  }, [isExpanded]);

  const toggleServicesExpanded = useCallback(() => {
    if (isExpanded) setIsServicesExpanded((open) => !open);
  }, [isExpanded]);

  const bgColor = useColorModeValue("light.100", "dark.100");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const hoverBgColor = useColorModeValue("gray.50", "gray.900");

  return (
    <Box
      position="fixed"
      left={0}
      top={0}
      minH="100vh"
      h="100%"
      w={isExpanded ? "350px" : "4.5rem"}
      bg={bgColor}
      boxShadow="md"
      zIndex={60}
      transition="width 0.2s ease"
      onMouseEnter={handleSidebarMouseEnter}
      onMouseLeave={handleSidebarMouseLeave}
      borderRight="1px"
      borderColor={borderColor}
      sx={{
        /* Small viewport height so sidebar never extends past visible area (1312×848, scaled Mac) */
        minHeight: '100svh',
        height: '100svh',
      }}
    >
      <VStack spacing={3} p={3} overflowY="auto" overflowX="hidden" sx={{ height: 'calc(100svh - 3.5rem)', minHeight: 0 }}>
        {/* Logo Section */}
        <VStack spacing={2} w="full">
          <Box
            cursor="pointer"
            onClick={goHome}
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
                onClick={(e) => onTopNavClick(e, item.path, requiresAuth)}
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
          <Box onMouseEnter={handleServicesSectionMouseEnter} onMouseLeave={handleServicesSectionMouseLeave}>
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
              onClick={toggleServicesExpanded}
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
                    onClick={(e) => onServiceNavClick(e, item.path, requiresAuth)}
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
