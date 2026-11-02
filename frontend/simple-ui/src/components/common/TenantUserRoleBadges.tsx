import React from "react";
import { Badge, Text, Wrap, WrapItem } from "@chakra-ui/react";
import {
  formatTenantUserRoleLabel,
  resolveTenantUserRoles,
} from "../../utils/tenantUserRoles";

export interface TenantUserRoleBadgesProps {
  /** Auth RBAC roles. The API schema already folds legacy singular `role` into this. */
  roles?: string[];
  emptyLabel?: string;
  badgeFontSize?: string;
}

/** Displays one or more tenant user RBAC roles as badges. */
export default function TenantUserRoleBadges({
  roles,
  emptyLabel = "—",
  badgeFontSize = "xs",
}: Readonly<TenantUserRoleBadgesProps>) {
  const list = resolveTenantUserRoles({ roles });
  if (list.length === 0) {
    return <Text color="gray.500">{emptyLabel}</Text>;
  }
  return (
    <Wrap spacing={1}>
      {list.map((role) => (
        <WrapItem key={role}>
          <Badge colorScheme="purple" fontSize={badgeFontSize}>
            {formatTenantUserRoleLabel(role)}
          </Badge>
        </WrapItem>
      ))}
    </Wrap>
  );
}
