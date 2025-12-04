// Collapsible sidebar component for navigation

import {
  Box,
  Button,
  Divider,
  Heading,
  Icon,
  Image,
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
} from "react-icons/io5";
import { useAuth } from "../../hooks/useAuth";
import { useFeatureFlag } from "../../hooks/useFeatureFlag";

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

// Base navigation items (without feature flag checks)
const baseNavItems: NavItem[] = [
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
    id: "asr",
    label: "ASR",
    path: "/asr",
    icon: FaMicrophone,
    iconSize: 10,
    iconColor: "orange.500",
    requiresAuth: true,
    featureFlag: "asr-enabled",
  },
  {
    id: "tts",
    label: "TTS",
    path: "/tts",
    icon: IoVolumeHighOutline,
    iconSize: 10,
    iconColor: "blue.500",
    requiresAuth: true,
    featureFlag: "tts-enabled",
  },
  {
    id: "nmt",
    label: "NMT",
    path: "/nmt",
    icon: IoLanguageOutline,
    iconSize: 10,
    iconColor: "green.500",
    requiresAuth: true,
    featureFlag: "nmt-enabled",
  },
  {
    id: "llm",
    label: "LLM",
    path: "/llm",
    icon: IoSparklesOutline,
    iconSize: 10,
    iconColor: "pink.500",
    requiresAuth: true,
    featureFlag: "llm-enabled",
  },
  {
    id: "pipeline",
    label: "Pipeline",
    path: "/pipeline",
    icon: IoGitNetworkOutline,
    iconSize: 10,
    iconColor: "purple.500",
    requiresAuth: true,
    featureFlag: "pipeline-enabled",
  },
  {
    id: "model-management",
    label: "Model Management",
    path: "/model-management",
    icon: IoServerOutline,
    iconSize: 10,
    iconColor: "cyan.500",
    requiresAuth: true,
    featureFlag: "model-management-enabled",
  },
];

const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isMobile] = useMediaQuery("(max-width: 1080px)");

  // Feature flags for each service
  const asrEnabled = useFeatureFlag({ flagName: "asr-enabled" });
  const ttsEnabled = useFeatureFlag({ flagName: "tts-enabled" });
  const nmtEnabled = useFeatureFlag({ flagName: "nmt-enabled" });
  const llmEnabled = useFeatureFlag({ flagName: "llm-enabled" });
  const pipelineEnabled = useFeatureFlag({ flagName: "pipeline-enabled" });
  const modelManagementEnabled = useFeatureFlag({ flagName: "model-management-enabled" });

  // Map feature flags to service IDs
  const featureFlagMap: Record<string, boolean> = {
    "asr-enabled": asrEnabled.isEnabled,
    "tts-enabled": ttsEnabled.isEnabled,
    "nmt-enabled": nmtEnabled.isEnabled,
    "llm-enabled": llmEnabled.isEnabled,
    "pipeline-enabled": pipelineEnabled.isEnabled,
    "model-management-enabled": modelManagementEnabled.isEnabled,
  };

  // Filter nav items based on feature flags
  const navItems = baseNavItems.filter((item) => {
    // Always show home
    if (item.id === "home") return true;
    // Show service if feature flag is enabled (or if no feature flag is set)
    if (item.featureFlag) {
      return featureFlagMap[item.featureFlag] ?? true; // Default to enabled if flag not found
    }
    return true; // Show items without feature flags
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
      w={isExpanded ? "240px" : "4.5rem"}
      bg={bgColor}
      boxShadow="md"
      zIndex={40}
      transition="width 0.2s ease"
      onMouseEnter={() => setIsExpanded(true)}
      onMouseLeave={() => setIsExpanded(false)}
      borderRight="1px"
      borderColor={borderColor}
      pt="3.5rem"
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
            {isExpanded ? (
              <Image
                src="/AI4Inclusion_Logo.svg"
                alt="AI4Inclusion Logo"
                boxSize={16}
                objectFit="contain"
                fallback={
                  <Box
                    boxSize={12}
                    bg="orange.500"
                    borderRadius="md"
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    color="white"
                    fontWeight="bold"
                    fontSize="md"
                  >
                    AI
                  </Box>
                }
              />
            ) : (
              <Box
                boxSize={10}
                bg="orange.500"
                borderRadius="md"
                display="flex"
                alignItems="center"
                justifyContent="center"
                color="white"
                fontWeight="bold"
                fontSize="sm"
              >
                AI
              </Box>
            )}
          </Box>
        </VStack>

        <Divider />

        {/* Navigation Items */}
        <VStack spacing={2} w="full" align="stretch" flex={1}>
          {navItems.map((item) => {
            const isActive = router.pathname === item.path;
            const requiresAuth = item.requiresAuth ?? false;

            const handleClick = async (e: React.MouseEvent) => {
              e.preventDefault();

              // Wait for auth to finish loading before checking
              if (isLoading) {
                console.log("Sidebar: Auth still loading, waiting...");
                return;
              }

              if (item.path === "/") {
                router.push("/");
                return;
              }

              // If route requires auth and user is not authenticated, redirect to auth
              if (requiresAuth && !isAuthenticated) {
                console.log(
                  "Sidebar: User not authenticated, redirecting to /auth for:",
                  item.path
                );
                // Store the intended destination
                if (typeof window !== 'undefined') {
                  sessionStorage.setItem('redirectAfterAuth', item.path);
                }
                router.push("/auth");
                return;
              }

              // Navigate to the route (either authenticated or route doesn't require auth)
              console.log("Sidebar: Navigating to:", item.path, {
                isAuthenticated,
                requiresAuth
              });
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
                      color={`${item.iconColor}`}
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
                  <Heading size="sm" color="gray.800" fontWeight="medium">
                    {item.label}
                  </Heading>
                ) : (
                  <Icon
                    as={item.icon}
                    boxSize={6}
                    color={`${item.iconColor}`}
                  />
                )}
              </Button>
            );
          })}
        </VStack>
      </VStack>
    </Box>
  );
};

export default Sidebar;
