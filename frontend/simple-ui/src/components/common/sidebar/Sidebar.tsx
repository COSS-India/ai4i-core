// Collapsible sidebar — collapse state and layout shell

import {
  Box,
  Button,
  Collapse,
  Divider,
  Heading,
  Icon,
  Image,
  useColorModeValue,
  VStack,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useCallback, useMemo, useState } from "react";
import { IoAppsOutline, IoChevronDownOutline } from "react-icons/io5";
import { TABS } from "../../../config/constants";
import { useAuth } from "../../../hooks/useAuth";
import { useGuestServices } from "../../../hooks/useGuestServices";
import { useSessionExpiry } from "../../../hooks/useSessionExpiry";
import { getTenantIdFromToken } from "../../../utils/helpers";
import { canAccessServicesManagement } from "../../../utils/rbac";
import { baseNavItems, topNavItems } from "./navConfig";
import SidebarNavItem from "./SidebarNavItem";

const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isLoading, user } = useAuth();
  const { isGuest: isGuestFromAccess, isLoading: guestServicesLoading, allowedServiceIds } =
    useGuestServices();
  const { checkSessionExpiry } = useSessionExpiry();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isServicesExpanded, setIsServicesExpanded] = useState(false);

  const isGuest = user?.roles?.includes("GUEST") || false;
  const isUser = user?.roles?.includes("USER") || false;
  const isAdmin = user?.roles?.includes("ADMIN") || false;
  const isTenantAdmin =
    user?.roles?.some((role) => (role ?? "").trim().toUpperCase() === "TENANT ADMIN") || false;
  const showTenantManagement = isAdmin || isTenantAdmin;
  const tenantId = getTenantIdFromToken();

  const topItems = useMemo(
    () =>
      topNavItems.filter((item) => {
        if (item.id === TABS.home) return true;
        if (item.id === TABS.traces) return false;
        if (
          (isGuest || isUser) &&
          (item.id === TABS.modelManagement || item.id === TABS.servicesManagement)
        ) {
          return false;
        }
        if (item.id === TABS.servicesManagement && !canAccessServicesManagement(user?.roles)) {
          return false;
        }
        if (item.id === TABS.tenantManagement && !showTenantManagement) return false;
        if (item.id === TABS.alertsManagement && !isAdmin) return false;
        if (item.id === TABS.piiManagement && !(isAdmin || isTenantAdmin)) return false;
        if (item.id === TABS.policyManagement) return false;
        if (item.id === TABS.apiKeyManagement && !(isAdmin || isTenantAdmin)) return false;
        if (item.id === TABS.logs && (isUser || isGuest)) return false;
        if (item.id === TABS.logs && !tenantId && !isAdmin) return false;
        return true;
      }),
    [isAdmin, isGuest, isUser, isTenantAdmin, showTenantManagement, tenantId, user?.roles]
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
    [allowedServiceIds, guestServicesLoading, isGuest, isGuestFromAccess]
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
    [checkSessionExpiry, isLoading, router]
  );

  const onServiceNavClick = useCallback(
    (e: React.MouseEvent, path: string, requiresAuth: boolean) => {
      e.preventDefault();
      if (isLoading) return;
      if (requiresAuth && !checkSessionExpiry()) return;
      router.push(path);
    },
    [checkSessionExpiry, isLoading, router]
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
        minHeight: "100svh",
        height: "100svh",
      }}
    >
      <VStack
        spacing={3}
        p={3}
        overflowY="auto"
        overflowX="hidden"
        sx={{ height: "calc(100svh - 3.5rem)", minHeight: 0 }}
      >
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

        <VStack spacing={2} w="full" align="stretch">
          {topItems.map((item) => (
            <SidebarNavItem
              key={item.id}
              item={item}
              isActive={router.pathname === item.path}
              isExpanded={isExpanded}
              variant="top"
              hoverBgColor={hoverBgColor}
              onClick={onTopNavClick}
            />
          ))}
        </VStack>

        <Divider />

        <VStack spacing={2} w="full" align="stretch" flex={1}>
          <Box
            onMouseEnter={handleServicesSectionMouseEnter}
            onMouseLeave={handleServicesSectionMouseLeave}
          >
            <Button
              variant="ghost"
              size="sm"
              h="3rem"
              minH="3rem"
              w="full"
              justifyContent={isExpanded ? "flex-start" : "center"}
              leftIcon={
                isExpanded ? <Icon as={IoAppsOutline} boxSize={5} color="gray.600" /> : undefined
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

          <Collapse
            in={isExpanded && isServicesExpanded}
            animateOpacity
            style={{ paddingTop: "10px" }}
          >
            <VStack spacing={1} w="full" align="stretch" pl={isExpanded ? 4 : 0}>
              {serviceItems.map((item) => (
                <SidebarNavItem
                  key={item.id}
                  item={item}
                  isActive={router.pathname === item.path}
                  isExpanded={isExpanded}
                  variant="service"
                  hoverBgColor={hoverBgColor}
                  onClick={onServiceNavClick}
                />
              ))}
            </VStack>
          </Collapse>
        </VStack>
      </VStack>
    </Box>
  );
};

export default Sidebar;
