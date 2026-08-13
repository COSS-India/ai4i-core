import React from "react";
import { Badge, Text, Wrap, WrapItem } from "@chakra-ui/react";
import {
  formatTenantUserRoleLabel,
  resolveTenantUserRoles,
  type TenantUserRoleSource,
} from "../../utils/tenantUserRoles";
import { formatInstitutionCopy } from "../../utils/institutionCopy";

export interface TenantUserRoleBadgesProps extends TenantUserRoleSource {
  emptyLabel?: string;
  badgeFontSize?: string;
}

/** Displays one or more tenant user RBAC roles as badges. */
export default function TenantUserRoleBadges({
  role,
  roles,
  emptyLabel = "—",
  badgeFontSize = "xs",
}: TenantUserRoleBadgesProps) {
  const list = resolveTenantUserRoles({ role, roles });
  if (list.length === 0) {
    return <Text color="gray.500">{emptyLabel}</Text>;
  }
  return (
    <Wrap spacing={1}>
      {list.map((role) => (
        <WrapItem key={role}>
          <Badge colorScheme="purple" fontSize={badgeFontSize}>
            {formatInstitutionCopy(formatTenantUserRoleLabel(role))}
          </Badge>
        </WrapItem>
      ))}
    </Wrap>
  );
}
