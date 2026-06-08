import { HStack, IconButton } from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { FiMail, FiPauseCircle, FiPower } from "react-icons/fi";
import { TENANT, resolveTenantUserDisplayStatus } from "../../../config/constants";
import type { TenantUserView } from "../../../types/tenant";
import type { TenantManagementState } from "./types";
import TenantOverflowActionMenu, { type RowActionMenuItem } from "./TenantOverflowActionMenu";

interface UserRowActionsProps {
  user: TenantUserView;
  tm: TenantManagementState;
  userListTenantStatus: string | null;
}

export default function UserRowActions({ user: u, tm, userListTenantStatus }: UserRowActionsProps) {
  const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
  const displayStatus = resolveTenantUserDisplayStatus(u, userListTenantStatus);

  const items: RowActionMenuItem[] = (() => {
    if (
      displayStatus === TENANT.USER_STATUS.PENDING ||
      displayStatus === TENANT.USER_STATUS.PENDING_ACTIVATION
    ) {
      return [
        {
          key: "resend-verification",
          label: "Resend verification email",
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
          onSelect: () => tm.handleOpenUserStatus(u, TENANT.USER_STATUS.SUSPENDED),
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
        colorScheme="blue"
        _hover={{ bg: "blue.50" }}
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
        colorScheme="green"
        _hover={{ bg: "green.50" }}
        onClick={(e) => {
          stopRowClick(e);
          tm.handleOpenEditUser(u);
        }}
      />
      <TenantOverflowActionMenu items={items} stopRowClick={stopRowClick} menuAriaLabel="User actions" />
    </HStack>
  );
}
