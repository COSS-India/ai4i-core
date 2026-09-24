// Collapsible sidebar component for navigation

import {
  Box,
  Button,
  Flex,
  Icon,
  Text,
  Tooltip,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useCallback, useMemo, useState } from "react";
import { IconType } from "react-icons";
import { MdPushPin } from "react-icons/md";
import {
  IoCompassOutline,
  IoKeyOutline,
  IoServerOutline,
  IoDocumentTextOutline,
  IoPeopleOutline,
  IoPricetagOutline,
  IoAppsOutline,
  IoPulseOutline,
  IoNotificationsOutline,
  IoFolderOpenOutline,
  IoStatsChartOutline,
} from "react-icons/io5";
import { INSTITUTION, TABS } from "../../config/constants";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
} from "../../hooks/useSidebarPin";
import { getTenantIdFromToken } from "../../utils/helpers";
import { getHomePath, getUsageDashboardOverviewPath } from "../../utils/navigation";
import {
  canAccessInstitutionManagement,
  canAccessServicesManagement,
  canAccessUsageDashboard,
  isPlatformAdminUser,
  isTenantAdminUser,
  isUsageDashboardOnlyUser,
  userHasRole,
  userMayManageApiKeys,
} from "../../utils/rbac";
import AdopterLogo from "./AdopterLogo";

type NavSectionId = "try" | "monitor" | "manage";

interface NavItem {
  id: string;
  label: string;
  shortLabel: string;
  path: string;
  icon: IconType;
  requiresAuth?: boolean;
  section: NavSectionId;
}

const NAV_SECTIONS: { id: NavSectionId; label: string }[] = [
  { id: "try", label: "Try" },
  { id: "monitor", label: "Monitor" },
  { id: "manage", label: "Manage" },
];

// Unsigned-in users only see Explore. Remaining top-nav items are role-gated.
const topNavItems: NavItem[] = [
  {
    id: TABS.home,
    label: "Explore",
    shortLabel: "Explore",
    path: "/",
    icon: IoCompassOutline,
    requiresAuth: false,
    section: "try",
  },
  {
    id: TABS.usageDashboard,
    label: "Usage Dashboard",
    shortLabel: "Usage",
    path: `/${TABS.usageDashboard}`,
    icon: IoStatsChartOutline,
    requiresAuth: true,
    section: "monitor",
  },
  {
    id: TABS.logs,
    label: "Logs Dashboard",
    shortLabel: "Logs",
    path: `/${TABS.logs}`,
    icon: IoDocumentTextOutline,
    requiresAuth: true,
    section: "monitor",
  },
  {
    id: TABS.traces,
    label: "Traces Dashboard",
    shortLabel: "Traces",
    path: `/${TABS.traces}`,
    icon: IoPulseOutline,
    requiresAuth: true,
    section: "monitor",
  },
  {
    id: TABS.modelManagement,
    label: "Model Management",
    shortLabel: "Models",
    path: `/${TABS.modelManagement}`,
    icon: IoServerOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.servicesManagement,
    label: "Services Management",
    shortLabel: "Services",
    path: `/${TABS.servicesManagement}`,
    icon: IoAppsOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.tenantManagement,
    label: `${INSTITUTION} Management`,
    shortLabel: INSTITUTION,
    path: `/${TABS.tenantManagement}`,
    icon: IoPeopleOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.apiKeyManagement,
    label: "API Key Management",
    shortLabel: "API Keys",
    path: `/${TABS.apiKeyManagement}`,
    icon: IoKeyOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.notificationsAlerts,
    label: "Platform Settings",
    shortLabel: "Notifications",
    path: `/${TABS.notificationsAlerts}`,
    icon: IoNotificationsOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.tierManagement,
    label: "Tier Management",
    shortLabel: "Tiers",
    path: `/${TABS.tierManagement}`,
    icon: IoPricetagOutline,
    requiresAuth: true,
    section: "manage",
  },
  {
    id: TABS.policyManagement,
    label: "Policy Management",
    shortLabel: "Policies",
    path: `/${TABS.policyManagement}`,
    icon: IoFolderOpenOutline,
    requiresAuth: true,
    section: "manage",
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
    case TABS.notificationsAlerts:
      return ctx.isAdmin;
    case TABS.tierManagement:
      return ctx.isAdmin;
    default:
      return true;
  }
}

interface SidebarProps {
  pinned: boolean;
  onTogglePin: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ pinned, onTogglePin }) => {
  const router = useRouter();
  const { isLoading, user, isAuthenticated } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const [isHovered, setIsHovered] = useState(false);

  const isExpanded = pinned || isHovered;

  const isGuest = userHasRole(user?.roles, "GUEST");
  const isUser = userHasRole(user?.roles, "USER");
  const isAdmin = isPlatformAdminUser(user?.roles);
  const isTenantAdmin = isTenantAdminUser(user?.roles);
  const showTenantManagement = canAccessInstitutionManagement(user?.roles);
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

  const bgColor = useColorModeValue("white", "dark.100");
  const borderColor = useColorModeValue("ink.200", "gray.700");
  const hoverBgColor = useColorModeValue("ink.50", "gray.900");
  const activeBg = useColorModeValue("brand.50", "whiteAlpha.200");
  const activeColor = useColorModeValue("ink.800", "ink.100");
  const iconColor = useColorModeValue("ink.500", "gray.300");
  const overlaying = isHovered && !pinned;

  const renderNavButton = (item: NavItem) => {
    const isActive =
      router.pathname === item.path || router.pathname.startsWith(`${item.path}/`);
    const requiresAuth = item.requiresAuth ?? false;
    const label = item.label;
    const itemIconColor = isActive ? "brand.700" : iconColor;

    const button = (
      <Button
        variant="ghost"
        size="sm"
        h="2.375rem"
        minH="2.375rem"
        w="full"
        position="relative"
        justifyContent={isExpanded ? "flex-start" : "center"}
        leftIcon={
          isExpanded ? (
            <Icon as={item.icon} boxSize={4} color={itemIconColor} />
          ) : undefined
        }
        bg={isActive ? activeBg : "transparent"}
        color={isActive ? activeColor : "ink.700"}
        aria-current={isActive ? "page" : undefined}
        onClick={(e) => onTopNavClick(e, item.path, requiresAuth, item.id)}
        _hover={{
          bg: isActive ? activeBg : hoverBgColor,
        }}
        _before={{
          content: '""',
          position: "absolute",
          left: 0,
          top: "6px",
          bottom: "6px",
          width: "3px",
          borderRadius: "full",
          bg: isActive ? "brand.600" : "transparent",
        }}
        px={isExpanded ? 3 : 0}
        borderRadius="md"
        fontWeight={isActive ? "semibold" : "medium"}
      >
        {isExpanded ? (
          <Text fontSize="sm" color="inherit" fontWeight="inherit" noOfLines={1}>
            {label}
          </Text>
        ) : (
          <Icon as={item.icon} boxSize={4} color={itemIconColor} />
        )}
      </Button>
    );

    if (isExpanded) return button;

    return (
      <Tooltip key={item.id} label={item.label} placement="right" openDelay={200} hasArrow>
        {button}
      </Tooltip>
    );
  };

  return (
    <Box
      position="fixed"
      left={0}
      top={0}
      minH="100vh"
      h="100%"
      w={isExpanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH}
      bg={bgColor}
      zIndex={60}
      transition="width 0.2s ease"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      borderRight="1px"
      borderColor={borderColor}
      boxShadow={overlaying ? "lg" : "none"}
      sx={{
        minHeight: "100svh",
        height: "100svh",
      }}
    >
      <VStack spacing={0} h="full" align="stretch">
        <Flex
          h="3.5rem"
          align="center"
          justify="center"
          flexShrink={0}
          borderBottom="1px"
          borderColor={borderColor}
          cursor="pointer"
          onClick={goHome}
          _hover={{ bg: "ink.50" }}
          px={3}
        >
          <AdopterLogo
            boxSize={isExpanded ? 10 : 8}
            transition="all 0.2s ease"
          />
        </Flex>

        <VStack
          spacing={2}
          p={2}
          overflowY="auto"
          overflowX="hidden"
          flex="1"
          minH={0}
          align="stretch"
        >
          {NAV_SECTIONS.map((section) => {
            const items = topItems.filter((item) => item.section === section.id);
            if (items.length === 0) return null;
            return (
              <VStack key={section.id} spacing={0.5} w="full" align="stretch">
                {isExpanded ? (
                  <Text
                    px={3}
                    pt={2}
                    pb={1}
                    fontSize="11px"
                    fontWeight="semibold"
                    color="ink.500"
                    textTransform="uppercase"
                    letterSpacing="0.06em"
                  >
                    {section.label}
                  </Text>
                ) : null}
                {items.map((item) => (
                  <React.Fragment key={item.id}>{renderNavButton(item)}</React.Fragment>
                ))}
              </VStack>
            );
          })}
        </VStack>

        <Box px={2} py={2} borderTop="1px" borderColor={borderColor}>
          <Tooltip
            label={pinned ? "Collapse menu" : "Keep menu open"}
            placement="right"
            openDelay={200}
            hasArrow
          >
            <Button
              variant="ghost"
              size="sm"
              h="2.5rem"
              w="full"
              justifyContent={isExpanded ? "flex-start" : "center"}
              leftIcon={
                isExpanded ? (
                  <Icon as={MdPushPin} boxSize={4} transform={pinned ? undefined : "rotate(45deg)"} />
                ) : undefined
              }
              onClick={onTogglePin}
              aria-pressed={pinned}
              aria-label={pinned ? "Collapse menu" : "Keep menu open"}
              color={pinned ? "ink.800" : "ink.500"}
              bg={pinned ? "ink.50" : "transparent"}
              px={isExpanded ? 3 : 0}
            >
              {isExpanded ? (
                <Text fontSize="sm">{pinned ? "Menu pinned" : "Keep open"}</Text>
              ) : (
                <Icon as={MdPushPin} boxSize={4} transform={pinned ? undefined : "rotate(45deg)"} />
              )}
            </Button>
          </Tooltip>
        </Box>
      </VStack>
    </Box>
  );
};

export default Sidebar;
