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
  const inactiveIconColor = useColorModeValue("ink.500", "gray.300");
  const overlaying = isHovered && !pinned;

  const focusReset = { boxShadow: "none", outline: "none" } as const;
  const focusVisible = {
    boxShadow: "none",
    outline: "2px solid",
    outlineColor: "blue.500",
    outlineOffset: "2px",
  } as const;

  const renderNavButton = (item: NavItem) => {
    const isActive =
      router.pathname === item.path || router.pathname.startsWith(`${item.path}/`);
    const requiresAuth = item.requiresAuth ?? false;
    const label = item.label;

    const button = (
      <Button
        variant="ghost"
        size="sm"
        h="9"
        minH="9"
        w="full"
        position="relative"
        justifyContent={isExpanded ? "flex-start" : "center"}
        gap={2.5}
        px={isExpanded ? 2.5 : 0}
        borderRadius="md"
        bg={isActive ? activeBg : "transparent"}
        color={isActive ? "ink.800" : "ink.700"}
        fontWeight={isActive ? "600" : "500"}
        aria-current={isActive ? "page" : undefined}
        aria-label={isExpanded ? undefined : label}
        onClick={(e) => onTopNavClick(e, item.path, requiresAuth, item.id)}
        _hover={{
          bg: isActive ? activeBg : hoverBgColor,
        }}
        _active={{
          bg: isActive ? activeBg : "ink.100",
        }}
        _focus={focusReset}
        _focusVisible={focusVisible}
        _before={{
          content: '""',
          position: "absolute",
          left: 0,
          top: "7px",
          bottom: "7px",
          width: "2px",
          borderRadius: "full",
          bg: isActive ? "blue.600" : "transparent",
        }}
      >
        <Icon
          as={item.icon}
          boxSize={4}
          color={isActive ? "blue.600" : inactiveIconColor}
          flexShrink={0}
        />
        {isExpanded ? (
          <Text fontSize="sm" color="inherit" fontWeight="inherit" noOfLines={1} textAlign="left">
            {label}
          </Text>
        ) : null}
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
      boxShadow={overlaying ? "sm" : "none"}
      sx={{
        minHeight: "100svh",
        height: "100svh",
      }}
    >
      <VStack spacing={0} h="full" align="stretch">
        <Flex
          as="button"
          type="button"
          aria-label="Home"
          h="3.5rem"
          align="center"
          justify="center"
          flexShrink={0}
          borderBottom="1px"
          borderColor={borderColor}
          cursor="pointer"
          onClick={goHome}
          _hover={{ bg: "ink.50" }}
          _focus={focusReset}
          _focusVisible={focusVisible}
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
          {NAV_SECTIONS.map((section, sectionIndex) => {
            const items = topItems.filter((item) => item.section === section.id);
            if (items.length === 0) return null;
            return (
              <VStack
                key={section.id}
                spacing={1}
                w="full"
                align="stretch"
                pt={sectionIndex === 0 ? 0 : 2}
              >
                {isExpanded ? (
                  <Text
                    px={2.5}
                    pt={1}
                    pb={1}
                    fontSize="xs"
                    fontWeight="600"
                    color="ink.400"
                    textTransform="uppercase"
                    letterSpacing="0.08em"
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
              h="9"
              minH="9"
              w="full"
              justifyContent={isExpanded ? "flex-start" : "center"}
              gap={2.5}
              px={isExpanded ? 2.5 : 0}
              borderRadius="md"
              onClick={onTogglePin}
              aria-pressed={pinned}
              aria-label={pinned ? "Collapse menu" : "Keep menu open"}
              color={pinned ? "ink.800" : "ink.600"}
              bg={pinned ? "ink.50" : "transparent"}
              fontWeight="500"
              _hover={{ bg: "ink.50" }}
              _focus={focusReset}
              _focusVisible={focusVisible}
            >
              <Icon
                as={MdPushPin}
                boxSize={4}
                color={inactiveIconColor}
                flexShrink={0}
                transform={pinned ? undefined : "rotate(45deg)"}
              />
              {isExpanded ? (
                <Text fontSize="sm" color="inherit" fontWeight="inherit" noOfLines={1}>
                  {pinned ? "Menu pinned" : "Keep open"}
                </Text>
              ) : null}
            </Button>
          </Tooltip>
        </Box>
      </VStack>
    </Box>
  );
};

export default Sidebar;
