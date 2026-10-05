import React from "react";
import { Badge, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import { framedEmpty, framedList, framedRow, getTaskTypeBadgeColor } from "./tierDisplay";

export interface MappedService {
  readonly serviceId: string;
  readonly name: string;
  readonly taskType: string;
  readonly isPublished: boolean;
}

interface ServicesMappedSectionProps {
  readonly services: MappedService[];
  readonly isLoading: boolean;
  readonly tierControl?: (service: MappedService) => React.ReactNode;
  readonly pendingRow?: (service: MappedService) => React.ReactNode | null;
}

export function ServicesMappedSection({
  services,
  isLoading,
  tierControl,
  pendingRow,
}: ServicesMappedSectionProps) {
  if (isLoading) {
    return (
      <HStack spacing={2} color="ink.400">
        <Spinner size="xs" />
        <Text fontSize="sm">Loading services…</Text>
      </HStack>
    );
  }
  if (!services.length) {
    return (
      <Text
        fontSize="sm"
        color="ink.400"
        {...(tierControl ? framedEmpty : null)}
      >
        No services mapped{tierControl ? "." : ""}
      </Text>
    );
  }
  return (
    <VStack align="stretch" {...(tierControl ? framedList : { spacing: 1 })}>
      {services.map((s) => {
        const pending = pendingRow?.(s);
        return (
          <HStack
            key={s.serviceId || s.name}
            justify="space-between"
            align="center"
            {...(tierControl ? framedRow : null)}
          >
            <Text fontSize="sm" color="ink.700" isTruncated minW={0}>
              {s.name}
            </Text>
            {pending ?? (
              <HStack spacing={1} flexShrink={0}>
                {s.taskType && (
                  <Badge
                    colorScheme={getTaskTypeBadgeColor(s.taskType)}
                    fontSize="xs"
                    px={2}
                    py={0.5}
                  >
                    {s.taskType}
                  </Badge>
                )}
                <Badge
                  colorScheme={s.isPublished ? "green" : "gray"}
                  fontSize="xs"
                  px={2}
                  py={0.5}
                >
                  {s.isPublished ? "PUBLISHED" : "DRAFT"}
                </Badge>
                {tierControl?.(s)}
              </HStack>
            )}
          </HStack>
        );
      })}
    </VStack>
  );
}
