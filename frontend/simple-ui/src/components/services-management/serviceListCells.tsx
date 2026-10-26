import { Badge, HStack, Text } from "@chakra-ui/react";
import React from "react";
import { getTaskColorScheme } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";
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
    <Badge colorScheme={getTaskColorScheme(taskType)} fontSize="sm" p={1}>
      {label}
    </Badge>
  );
}

export function renderServiceTierCell(service: Service): React.ReactNode {
  const names = service.tierNames;
  if (!names || names.length === 0) {
    return (
      <Text fontSize="sm" color="ink.400">
        —
      </Text>
    );
  }
  return (
    <HStack spacing={1} flexWrap="wrap">
      {names.map((name) => (
        <Badge key={name} colorScheme="gray" fontSize="xs" px={2} py={0.5}>
          {name}
        </Badge>
      ))}
    </HStack>
  );
}

export function renderServiceStatusCell(service: Service): React.ReactNode {
  if (service.isPublished === true) {
    return (
      <Badge colorScheme="green" fontSize="sm" p={1}>
        Published
      </Badge>
    );
  }
  return (
    <Badge colorScheme="gray" fontSize="sm" p={1}>
      Unpublished
    </Badge>
  );
}

export function renderServiceCreatedAtCell(service: Service): React.ReactNode {
  const label = formatServiceListDate(serviceCreatedAtMillis(service));
  return (
    <Text fontSize="sm" color={mutedOrDefault(label === "—")} noOfLines={1}>
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
    <Text fontSize="sm" color={mutedOrDefault(label === "—")} noOfLines={1}>
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
