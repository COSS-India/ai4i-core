import React from "react";
import { HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import { INSTITUTIONS } from "../../config/constants";
import { framedEmpty, framedList, framedRow } from "./tierDisplay";

export interface AssignedTenant {
  readonly tenantId: string;
  readonly organisation: string;
}

interface AssignedTenantsSectionProps {
  readonly tenants: AssignedTenant[];
  readonly isLoading: boolean;
  readonly tierControl?: (tenant: AssignedTenant) => React.ReactNode;
  readonly pendingRow?: (tenant: AssignedTenant) => React.ReactNode | null;
}

export function AssignedTenantsSection({
  tenants,
  isLoading,
  tierControl,
  pendingRow,
}: AssignedTenantsSectionProps) {
  if (isLoading) {
    return (
      <HStack spacing={2} color="ink.400">
        <Spinner size="xs" />
        <Text fontSize="sm">Loading {INSTITUTIONS.toLowerCase()}…</Text>
      </HStack>
    );
  }
  if (!tenants.length) {
    return (
      <Text
        fontSize="sm"
        color="ink.400"
        {...(tierControl ? framedEmpty : null)}
      >
        No {INSTITUTIONS.toLowerCase()} assigned{tierControl ? "." : ""}
      </Text>
    );
  }
  return (
    <VStack align="stretch" {...(tierControl ? framedList : { spacing: 1 })}>
      {tenants.map((t) => {
        const pending = pendingRow?.(t);
        return (
          <HStack
            key={t.tenantId}
            justify="space-between"
            align="center"
            {...(tierControl ? framedRow : null)}
            bg={pending ? "blue.50" : undefined}
          >
            <Text fontSize="sm" color="ink.700" isTruncated minW={0}>
              {t.organisation}
            </Text>
            {pending ?? (
              <HStack spacing={3} flexShrink={0}>
                <Text fontSize="xs" color="ink.500">
                  ID: {t.tenantId}
                </Text>
                {tierControl?.(t)}
              </HStack>
            )}
          </HStack>
        );
      })}
    </VStack>
  );
}
