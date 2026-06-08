import { HStack, IconButton } from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { FiMail, FiPauseCircle, FiPower } from "react-icons/fi";
import { isTenantStatus, TENANT } from "../../../config/constants";
import type { TenantView } from "../../../types/tenant";
import type { TenantManagementState } from "./types";
import TenantOverflowActionMenu, { type RowActionMenuItem } from "./TenantOverflowActionMenu";

interface TenantRowActionsProps {
  tenant: TenantView;
  tm: TenantManagementState;
}

export default function TenantRowActions({ tenant: t, tm }: TenantRowActionsProps) {
  const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();

  const items: RowActionMenuItem[] = (() => {
    if (isTenantStatus(t.status, TENANT.STATUS.PENDING)) {
      return [
        {
          key: "resend-verification",
          label: "Resend verification email",
          onSelect: () => void tm.handleResendTenantVerificationEmail(t),
          color: "blue.600",
          hoverBg: "blue.50",
          icon: <FiMail size={16} />,
          isDisabled: tm.resendVerificationTenantId === t.tenant_id,
        },
        {
          key: "deactivate",
          label: "Deactivate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    }

    if (isTenantStatus(t.status, TENANT.STATUS.ACTIVE)) {
      return [
        {
          key: "suspend",
          label: "Suspend",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.SUSPENDED),
          color: "orange.600",
          hoverBg: "orange.50",
          icon: <FiPauseCircle size={16} />,
        },
        {
          key: "deactivate",
          label: "Deactivate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    }

    if (isTenantStatus(t.status, TENANT.STATUS.SUSPENDED)) {
      return [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
        {
          key: "deactivate",
          label: "Deactivate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
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
        aria-label="View tenant"
        icon={<ViewIcon />}
        size="sm"
        variant="ghost"
        colorScheme="blue"
        _hover={{ bg: "blue.50" }}
        onClick={(e) => {
          stopRowClick(e);
          tm.handleViewTenant(t);
        }}
      />
      <IconButton
        aria-label="Edit tenant"
        icon={<EditIcon />}
        size="sm"
        variant="ghost"
        colorScheme="green"
        _hover={{ bg: "green.50" }}
        onClick={(e) => {
          stopRowClick(e);
          tm.handleOpenEditTenant(t);
        }}
      />
      <TenantOverflowActionMenu items={items} stopRowClick={stopRowClick} menuAriaLabel="Tenant actions" />
    </HStack>
  );
}
