import { HStack, Text } from "@chakra-ui/react";
import React from "react";
import { getTaskColorScheme } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";
import { TruncatingBadge } from "../common/dataTableUtils";
import { resolveTaskType } from "../../utils/platformService";
import {
  formatServiceListDate,
  formatServiceListPrice,
  serviceCreatedAtMillis,
  serviceListServiceId,
  serviceModelName,
  servicePublishedOnMillis,
} from "./serviceListColumns";

function mutedOrDefault(isEmpty: boolean): string | undefined {
  if (isEmpty) return "ink.400";
  return undefined;
}

export function renderServiceNameCell(service: Service): React.ReactNode {
  return (
    <Text fontSize="sm" fontWeight="medium" noOfLines={1} title={service.name}>
      {service.name || "N/A"}
    </Text>
  );
}

export function renderServiceTaskTypeCell(service: Service): React.ReactNode {
  const taskType = resolveTaskType(service);
  const label = taskType ? taskType.toUpperCase() : "N/A";
  return (
    <TruncatingBadge
      colorScheme={getTaskColorScheme(taskType)}
      fontSize="sm"
      px={1.5}
      py={0.5}
      title={label}
    >
      {label}
    </TruncatingBadge>
  );
}

const SERVICE_TIERS_VISIBLE_COUNT = 3;

export function renderServiceTierCell(service: Service): React.ReactNode {
  const names = service.tierNames;
  if (!names?.length) {
    return (
      <Text fontSize="sm" color="ink.400">
        —
      </Text>
    );
  }
  const fullLabel = names.join(", ");
  const visible = names.slice(0, SERVICE_TIERS_VISIBLE_COUNT);
  const hiddenCount = names.length - visible.length;
  return (
    <HStack
      spacing={1}
      flexWrap="nowrap"
      overflow="hidden"
      minW={0}
      maxW="100%"
      title={fullLabel}
    >
      {visible.map((name, index) => (
        <TruncatingBadge
          key={name}
          colorScheme="gray"
          fontSize="xs"
          px={2}
          py={0.5}
          maxW={index === 0 ? "100%" : undefined}
          flexShrink={index === 0 ? 1 : 0}
          title={name}
        >
          {name}
        </TruncatingBadge>
      ))}
      {hiddenCount > 0 ? (
        <TruncatingBadge colorScheme="gray" fontSize="xs" px={2} py={0.5} flexShrink={0}>
          +{hiddenCount}
        </TruncatingBadge>
      ) : null}
    </HStack>
  );
}

export function renderServiceStatusCell(service: Service): React.ReactNode {
  if (service.isPublished === true) {
    return (
      <TruncatingBadge colorScheme="green" fontSize="sm" p={1}>
        Published
      </TruncatingBadge>
    );
  }
  return (
    <TruncatingBadge colorScheme="gray" fontSize="sm" p={1}>
      Unpublished
    </TruncatingBadge>
  );
}

export function renderServiceCreatedAtCell(service: Service): React.ReactNode {
  const label = formatServiceListDate(serviceCreatedAtMillis(service));
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(label === "—")}
      noOfLines={1}
      title={label === "—" ? undefined : label}
    >
      {label}
    </Text>
  );
}

export function renderServiceModelNameCell(service: Service): React.ReactNode {
  const label = serviceModelName(service) || "—";
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(label === "—")}
      noOfLines={1}
      title={label}
    >
      {label}
    </Text>
  );
}

export function renderServiceIdCell(service: Service): React.ReactNode {
  const label = serviceListServiceId(service) || "—";
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(label === "—")}
      noOfLines={1}
      title={label}
    >
      {label}
    </Text>
  );
}

export function renderServiceInputPriceCell(service: Service): React.ReactNode {
  return (
    <Text fontSize="sm" color={mutedOrDefault(service.costPerUnit == null)}>
      {formatServiceListPrice(service.costPerUnit)}
    </Text>
  );
}

export function renderServiceOutputPriceCell(service: Service): React.ReactNode {
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(service.outputCostPerUnit == null)}
    >
      {formatServiceListPrice(service.outputCostPerUnit)}
    </Text>
  );
}

export function renderServiceCachedInputPriceCell(
  service: Service,
): React.ReactNode {
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(service.cachedInputCostPerUnit == null)}
    >
      {formatServiceListPrice(service.cachedInputCostPerUnit)}
    </Text>
  );
}

export function renderServicePublishedOnCell(service: Service): React.ReactNode {
  const label = formatServiceListDate(servicePublishedOnMillis(service));
  return (
    <Text
      fontSize="sm"
      color={mutedOrDefault(label === "—")}
      noOfLines={1}
      title={label === "—" ? undefined : label}
    >
      {label}
    </Text>
  );
}

export function renderEmptyServiceCell(): React.ReactNode {
  return (
    <Text fontSize="sm" color="ink.400">
      —
    </Text>
  );
}
