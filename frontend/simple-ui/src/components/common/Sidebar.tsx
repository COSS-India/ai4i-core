// Collapsible sidebar component for navigation

import {
  Box,
  Button,
  Divider,
  Heading,
  Icon,
  useColorModeValue,
  VStack,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useCallback, useMemo, useState } from "react";
import { IconType } from "react-icons";
import {
  IoCompassOutline,
  IoKeyOutline,
  IoServerOutline,
  IoDocumentTextOutline,
  IoPeopleOutline,
  IoPricetagOutline,
  IoAppsOutline,
  IoPulseOutline,
  // Restore with Alerts / PII Guardrail nav items
  // IoNotificationsOutline,
  // IoShieldCheckmarkOutline,
  IoFolderOpenOutline,
  IoStatsChartOutline,
} from "react-icons/io5";
import { INSTITUTION, TABS } from "../../config/constants";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import { getTenantIdFromToken } from "../../utils/helpers";
import { getHomePath, getUsageDashboardOverviewPath } from "../../utils/navigation";
import {
  canAccessInstitutionManagement,
  canAccessServicesManagement,
  canAccessUsageDashboard,
  isPlatformAdminUser,
  isTenantAdminUser,
  isUsageDashboardOnlyUser,
  userMayManageApiKeys,
} from "../../utils/rbac";
import AdopterLogo from "./AdopterLogo";

const safeColorMap = {
  [TABS.modelManagement]: { // Rose → Pastel Rose
    50:  "#FFF1F2",
    300: "#FFC1C7",
    400: "#FF9FA8",
    600: "#FF6B7A",
  },
  [TABS.servicesManagement]: { // Cyan → Pastel Cyan
    50:  "#E0F7FA",
    300: "#80DEEA",
    400: "#4DD0E1",
    600: "#00ACC1",
  },
  [TABS.tenantManagement]: { // Teal → Pastel Teal
    50:  "#E0F2F1",
    300: "#80CBC4",
    400: "#4DB6AC",
    600: "#00897B",
  },
  [TABS.logs]: { // Green → Pastel Green
    50:  "#E8F5E9",
    300: "#81C784",
    400: "#66BB6A",
    600: "#43A047",
  },
  [TABS.usageDashboard]: {
    50:  "#FFF7ED",
    300: "#FDBA74",
    400: "#FB923C",
    600: "#EA580C",
  },
  [TABS.traces]: { // Purple → Pastel Purple
    50:  "#F3E5F5",
    300: "#BA68C8",
    400: "#AB47BC",
    600: "#8E24AA",
  },
  // Alerts Management removed from UI — uncomment to restore
  // [TABS.alertsManagement]: { // Amber/Yellow → Pastel Amber
  //   50:  "#FFF8E1",
  //   300: "#FFD54F",
  //   400: "#FFCA28",
  //   600: "#F9A825",
  // },
  // PII Guardrail removed from UI — uncomment to restore
  // [TABS.piiManagement]: {
  //   50:  "#E8EAF6",
  //   300: "#9FA8DA",
  //   400: "#7986CB",
  //   600: "#5C6BC0",
  // },
  [TABS.tierManagement]: {
    50:  "#E3F2FD",
    300: "#90CAF9",
    400: "#42A5F5",
    600: "#1565C0",
  },
  [TABS.policyManagement]: {
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

// Unsigned-in users only see Explore. Remaining top-nav items are role-gated.
const topNavItems: NavItem[] = [
  {
    id: TABS.home,
    label: "Explore",
    path: "/",
    icon: IoCompassOutline,
    iconSize: 10,
    iconColor: "black.500",
    requiresAuth: false,
  },
  // Usage Dashboard placed after Explore — to restore previous order (after Logs),
  // move this block back below Logs (see commented copy there) and remove this entry.
  {
    id: TABS.usageDashboard,
    label: "Usage Dashboard",
    path: `/${TABS.usageDashboard}`,
    icon: IoStatsChartOutline,
    iconSize: 10,
    iconColor: "",
    requiresAuth: true,
  },
  {
    id: TABS.modelManagement,
    label: "Model Management",
    path: `/${TABS.modelManagement}`,
    icon: IoServerOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: TABS.servicesManagement,
    label: "Services Management",
    path: `/${TABS.servicesManagement}`,
    icon: IoAppsOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: TABS.tenantManagement,
    label: `${INSTITUTION} Management`,
    path: `/${TABS.tenantManagement}`,
    icon: IoPeopleOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: TABS.apiKeyManagement,
    label: "API Key Management",
    path: `/${TABS.apiKeyManagement}`,
    icon: IoKeyOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  {
    id: TABS.logs,
    label: "Logs Dashboard",
    path: `/${TABS.logs}`,
    icon: IoDocumentTextOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  // Previous Usage Dashboard position (after Logs) — uncomment and remove the
  // entry after Explore above to restore the original sidebar order.
  // {
  //   id: TABS.usageDashboard,
  //   label: "Usage Dashboard",
  //   path: `/${TABS.usageDashboard}`,
  //   icon: IoStatsChartOutline,
  //   iconSize: 10,
  //   iconColor: "",
  //   requiresAuth: true,
  // },
  {
    id: TABS.traces,
    label: "Traces Dashboard",
    path: `/${TABS.traces}`,
    icon: IoPulseOutline,
    iconSize: 10,
    iconColor: "", // Will be computed from safeColorMap
    requiresAuth: true,
  },
  // Alerts Management removed from UI — uncomment to restore
  // {
  //   id: TABS.alertsManagement,
  //   label: "Alerts Management",
  //   path: `/${TABS.alertsManagement}`,
  //   icon: IoNotificationsOutline,
  //   iconSize: 10,
  //   iconColor: "", // Will be computed from safeColorMap
  //   requiresAuth: true,
  // },
  // PII Guardrail removed from UI — uncomment to restore
  // {
  //   id: TABS.piiManagement,
  //   label: "PII Guardrail",
  //   path: `/${TABS.piiManagement}`,
  //   icon: IoShieldCheckmarkOutline,
  //   iconSize: 10,
  //   iconColor: "",
  //   requiresAuth: true,
  // },
  {
    id: TABS.tierManagement,
    label: "Tier Management",
    path: `/${TABS.tierManagement}`,
    icon: IoPricetagOutline,
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

interface TopNavFilterContext {
  isAuthenticated: boolean;
  isGuest: boolean;
  isUser: boolean;
  isAdmin: boolean;
  isTenantAdmin: boolean;
  showTenantManagement: boolean;
  tenantId: string | null;
  userRoles?: string[];
}

function isTopNavItemVisible(itemId: string, ctx: TopNavFilterContext): boolean {
  if (!ctx.isAuthenticated) {
    return itemId === TABS.home;
  }

  if (isUsageDashboardOnlyUser(ctx.userRoles)) {
    return itemId === TABS.usageDashboard;
  }

  switch (itemId) {
    case TABS.home:
      return true;
    case TABS.traces:
    case TABS.policyManagement:
      return false;
    case TABS.modelManagement:
      return !ctx.isGuest && !ctx.isUser;
    case TABS.servicesManagement:
      return !ctx.isGuest && !ctx.isUser && canAccessServicesManagement(ctx.userRoles);
    case TABS.tenantManagement:
      return ctx.showTenantManagement;
    case TABS.apiKeyManagement:
      return userMayManageApiKeys(ctx.userRoles);
    case TABS.logs:
      return !ctx.isUser && !ctx.isGuest && Boolean(ctx.tenantId || ctx.isAdmin);
    case TABS.usageDashboard:
      return canAccessUsageDashboard(ctx.userRoles);
    // Alerts Management removed from UI — uncomment to restore
    // case TABS.alertsManagement:
    //   return ctx.isAdmin;
    // PII Guardrail removed from UI — uncomment to restore
    // case TABS.piiManagement:
    //   return ctx.isAdmin || ctx.isTenantAdmin;
    case TABS.tierManagement:
      return ctx.isAdmin;
    default:
      return true;
  }
}

const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isLoading, user, isAuthenticated } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const [isExpanded, setIsExpanded] = useState(false);

  // Check if user is GUEST or USER
  const isGuest = user?.roles?.includes('GUEST') || false;
  const isUser = user?.roles?.includes('USER') || false;

  // Check if user is ADMIN
  const isAdmin = isPlatformAdminUser(user?.roles);
  const isTenantAdmin = isTenantAdminUser(user?.roles);

  const showTenantManagement = canAccessInstitutionManagement(user?.roles);

  // Get tenant_id from JWT token
  const tenantId = getTenantIdFromToken();

  const topNavFilterContext = useMemo<TopNavFilterContext>(
    () => ({
      isAuthenticated,
      isGuest,
      isUser,
      isAdmin,
      isTenantAdmin,
      showTenantManagement,
      tenantId,
      userRoles: user?.roles,
    }),
    [
      isAuthenticated,
      isGuest,
      isUser,
      isAdmin,
      isTenantAdmin,
      showTenantManagement,
      tenantId,
      user?.roles,
    ],
  );

  const topItems = useMemo(
    () => topNavItems.filter((item) => isTopNavItemVisible(item.id, topNavFilterContext)),
    [topNavFilterContext],
  );

  const handleSidebarMouseEnter = useCallback(() => {
    setIsExpanded(true);
  }, []);

  const handleSidebarMouseLeave = useCallback(() => {
    setIsExpanded(false);
  }, []);

  // Role-aware: the Usage-Dashboard-only role has no access to "/".
  const goHome = useCallback(() => {
    router.push(getHomePath(user?.roles));
  }, [router, user?.roles]);

  const onTopNavClick = useCallback(
    (e: React.MouseEvent, path: string, requiresAuth: boolean, itemId: string) => {
      e.preventDefault();
      if (isLoading) return;
      if (requiresAuth && !checkSessionExpiry()) return;
      if (itemId === TABS.usageDashboard) {
        router.push(getUsageDashboardOverviewPath());
        return;
      }
      router.push(path);
    },
    [checkSessionExpiry, isLoading, router],
  );

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
            <AdopterLogo
              boxSize={isExpanded ? 16 : 10}
              transition="all 0.2s ease"
            />
          </Box>
        </VStack>

        <Divider />

        {/* Top Navigation Items (Explore and management pages) */}
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
                      color={item.id === TABS.home ? "black" : getColor(item.id, 600)}
                    />
                  ) : undefined
                }
                bg={isActive ? "gray.200" : "transparent"}
                color={isActive ? "gray.800" : "gray.700"}
                boxShadow={isActive ? "sm" : "none"}
                onClick={(e) => onTopNavClick(e, item.path, requiresAuth, item.id)}
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
                    color={item.id === TABS.home ? "black" : getColor(item.id, 600)}
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
