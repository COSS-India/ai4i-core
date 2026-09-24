import {
  HStack,
  IconButton,
  Image,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Tooltip,
} from "@chakra-ui/react";
import { ChevronDownIcon, DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import React from "react";
import {
  FiMail,
  FiMinusCircle,
  FiPauseCircle,
  FiPower,
} from "react-icons/fi";
import {
  INSTITUTION,
  TENANT,
  isTenantStatus,
  type TenantUserStatusValue,
} from "../../config/constants";
import { isDefaultTenant } from "../../utils/defaultTenant";
import type { TenantUserView, TenantView } from "../../types/tenant";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";

type TenantManagement = ReturnType<typeof useTenantManagement>;

type RowActionMenuItem = {
  key: string;
  label: string;
  onSelect: () => void;
  color: string;
  hoverBg: string;
  icon: React.ReactNode;
  isDisabled?: boolean;
};

function renderOverflowActionMenu(
  items: RowActionMenuItem[],
  stopRowClick: (e: React.MouseEvent) => void,
  menuAriaLabel: string,
) {
  if (items.length === 0) return null;
  return (
    <Menu>
      <MenuButton
        as={IconButton}
        aria-label={menuAriaLabel}
        icon={<ChevronDownIcon />}
        size="sm"
        variant="ghost"
        colorScheme="gray"
        _hover={{ bg: "ink.100" }}
        onClick={stopRowClick}
      />
      <MenuList minW="auto" w="auto" py={1}>
        {items.map((item) => (
          <Tooltip
            key={item.key}
            label={item.label}
            placement="left"
            hasArrow
            openDelay={300}
          >
            <MenuItem
              aria-label={item.label}
              color={item.color}
              _hover={{ bg: item.hoverBg }}
              isDisabled={item.isDisabled}
              px={2}
              py={2}
              minH="8"
              w="auto"
              onClick={(e) => {
                stopRowClick(e);
                item.onSelect();
              }}
            >
              {item.icon}
            </MenuItem>
          </Tooltip>
        ))}
      </MenuList>
    </Menu>
  );
}

type InstitutionTenantRowActionsProps = {
  tm: TenantManagement;
  tenant: TenantView;
  onOpenPlan: (tenant: TenantView) => void;
};

export function InstitutionTenantRowActions({
  tm,
  tenant: t,
  onOpenPlan,
}: InstitutionTenantRowActionsProps) {
  const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
  const isProtectedDefaultOrg = isDefaultTenant(t);
  const hasTier = Boolean(t.tier_id);
  const planActionLabel = hasTier ? "Manage Tier" : "Assign Tier";

  const items: RowActionMenuItem[] = (() => {
    if (isTenantStatus(t.status, TENANT.STATUS.PENDING)) {
      const pendingItems: RowActionMenuItem[] = [
        {
          key: "resend-verification",
          label: "Resend verification email",
          onSelect: () => void tm.handleResendTenantVerificationEmail(t),
          color: "blue.600",
          hoverBg: "blue.50",
          icon: <FiMail size={16} />,
          isDisabled: tm.resendVerificationTenantId === t.tenant_id,
        },
      ];
      if (!isProtectedDefaultOrg) {
        pendingItems.push({
          key: "deactivate",
          label: "Deactivate",
          onSelect: () =>
            tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <FiMinusCircle size={16} />,
        });
      }
      return pendingItems;
    }

    if (isTenantStatus(t.status, TENANT.STATUS.ACTIVE)) {
      if (isProtectedDefaultOrg) return [];
      return [
        {
          key: "suspend",
          label: "Suspend",
          onSelect: () =>
            tm.handleOpenTenantStatus(t, TENANT.STATUS.SUSPENDED),
          color: "orange.600",
          hoverBg: "orange.50",
          icon: <FiPauseCircle size={16} />,
        },
        {
          key: "deactivate",
          label: "Deactivate",
          onSelect: () =>
            tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <FiMinusCircle size={16} />,
        },
      ];
    }

    if (isTenantStatus(t.status, TENANT.STATUS.SUSPENDED)) {
      const suspendedItems: RowActionMenuItem[] = [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
      ];
      if (!isProtectedDefaultOrg) {
        suspendedItems.push({
          key: "deactivate",
          label: "Deactivate",
          onSelect: () =>
            tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <FiMinusCircle size={16} />,
        });
      }
      return suspendedItems;
    }

    // DEACTIVATED — previous behavior (Activate) unless this tenant was
    // soft-deleted from PENDING verification (terminal, no actions).
    if (tm.isPendingSoftDeletedTenant(t)) {
      return [];
    }
    return [
      {
        key: "activate",
        label: "Activate",
        onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
        color: "green.600",
        hoverBg: "green.50",
        icon: <FiPower size={16} />,
      },
    ];
  })();

  return (
    <HStack spacing={2}>
      <IconButton
        aria-label={`View ${INSTITUTION.toLowerCase()}`}
        icon={<ViewIcon />}
        size="sm"
        variant="ghost"
        onClick={(e) => {
          stopRowClick(e);
          tm.handleViewTenant(t);
        }}
      />
      <IconButton
        aria-label={`Edit ${INSTITUTION.toLowerCase()}`}
        icon={<EditIcon />}
        size="sm"
        variant="ghost"
        onClick={(e) => {
          stopRowClick(e);
          tm.handleOpenEditTenant(t);
        }}
      />
      <Tooltip label={planActionLabel}>
        <IconButton
          aria-label={planActionLabel}
          icon={
            <Image
              src={
                hasTier
                  ? "/assests/icons/tier-assigned.svg"
                  : "/assests/icons/tier-unassigned.svg"
              }
              alt=""
              boxSize="24px"
            />
          }
          size="sm"
          variant="ghost"
          colorScheme="gray"
          borderRadius="full"
          _hover={{ bg: "ink.100" }}
          onClick={(e) => {
            stopRowClick(e);
            onOpenPlan(t);
          }}
        />
      </Tooltip>

      {renderOverflowActionMenu(items, stopRowClick, `${INSTITUTION} actions`)}
    </HStack>
  );
}

type InstitutionUserRowActionsProps = {
  tm: TenantManagement;
  user: TenantUserView;
  resolveUserDisplayStatus: (user: TenantUserView) => TenantUserStatusValue;
};

export function InstitutionUserRowActions({
  tm,
  user: u,
  resolveUserDisplayStatus,
}: InstitutionUserRowActionsProps) {
  const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
  const displayStatus = resolveUserDisplayStatus(u);

  const items: RowActionMenuItem[] = (() => {
    if (
      displayStatus === TENANT.USER_STATUS.PENDING ||
      displayStatus === TENANT.USER_STATUS.PENDING_ACTIVATION
    ) {
      return [
        {
          key: "resend-verification",
          label: "Resend setup link",
          onSelect: () => void tm.handleResendTenantUserVerification(u),
          color: "blue.600",
          hoverBg: "blue.50",
          icon: <FiMail size={16} />,
          isDisabled: tm.resendVerificationUserId === u.user_id,
        },
        {
          key: "delete",
          label: "Delete",
          onSelect: () => tm.handleOpenDeleteUser(u),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    }

    if (displayStatus === TENANT.USER_STATUS.ACTIVE) {
      return [
        {
          key: "suspend",
          label: "Suspend",
          onSelect: () =>
            tm.handleOpenUserStatus(u, TENANT.USER_STATUS.SUSPENDED),
          color: "orange.600",
          hoverBg: "orange.50",
          icon: <FiPauseCircle size={16} />,
        },
        {
          key: "delete",
          label: "Delete",
          onSelect: () => tm.handleOpenDeleteUser(u),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    }

    // SUSPENDED
    return [
      {
        key: "activate",
        label: "Activate",
        onSelect: () => tm.handleOpenUserStatus(u, TENANT.USER_STATUS.ACTIVE),
        color: "green.600",
        hoverBg: "green.50",
        icon: <FiPower size={16} />,
      },
      {
        key: "delete",
        label: "Delete",
        onSelect: () => tm.handleOpenDeleteUser(u),
        color: "red.600",
        hoverBg: "red.50",
        icon: <DeleteIcon boxSize={4} />,
      },
    ];
  })();

  return (
    <HStack spacing={2}>
      <IconButton
        aria-label="View user"
        icon={<ViewIcon />}
        size="sm"
        variant="ghost"
        onClick={(e) => {
          stopRowClick(e);
          tm.handleViewUser(u);
        }}
      />
      <IconButton
        aria-label="Edit user"
        icon={<EditIcon />}
        size="sm"
        variant="ghost"
        onClick={(e) => {
          stopRowClick(e);
          tm.handleOpenEditUser(u);
        }}
      />

      {renderOverflowActionMenu(items, stopRowClick, "User actions")}
    </HStack>
  );
}
