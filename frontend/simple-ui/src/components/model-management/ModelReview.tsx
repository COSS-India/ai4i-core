import { Badge, Box, HStack, SimpleGrid, Text } from "@chakra-ui/react";
import React from "react";
import {
  formatModelVersionStatusLabel,
  getTaskColorScheme,
  isModelVersionStatusActive,
} from "../../config/constants";
import FieldLabel from "../common/FieldLabel";
import { resolveTaskType } from "../../utils/platformService";

/** Fields the registry already shows for a model. JSON stays the contract. */
export type ModelReviewSource = {
  modelId?: string;
  name?: string;
  version?: string;
  versionStatus?: string | null;
  description?: string | null;
  license?: unknown;
  source?: string | null;
  refUrl?: string | null;
  licenseUrl?: string | null;
  isLangDetectionEnabled?: boolean;
  isMultilingual?: boolean;
  domain?: unknown;
  task?: { type?: string };
  task_type?: string;
  taskType?: string;
};

function textValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "—";
}

function licenseLabel(license: unknown): string {
  if (typeof license === "string") return license || "—";
  if (license && typeof license === "object" && "name" in license) {
    const name = (license as { name?: unknown }).name;
    if (typeof name === "string" && name) return name;
  }
  return "—";
}

function domainList(domain: unknown): string[] {
  if (!Array.isArray(domain)) return [];
  return domain
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "name" in item) {
        const name = (item as { name?: unknown }).name;
        return typeof name === "string" ? name : "";
      }
      return "";
    })
    .filter(Boolean);
}

function ReviewField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Box>
      <FieldLabel variant="inline">{label}</FieldLabel>
      {children}
    </Box>
  );
}

export default function ModelReview({
  model,
  showStatus = false,
}: {
  model: ModelReviewSource;
  showStatus?: boolean;
}) {
  const taskType = resolveTaskType(model);
  const domains = domainList(model.domain);
  const source = model.source || model.refUrl;

  return (
    <Box>
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <ReviewField label="Model ID">
          <Text fontSize="md" wordBreak="break-all">{textValue(model.modelId)}</Text>
        </ReviewField>
        <ReviewField label="Model name">
          <Text fontSize="md">{textValue(model.name)}</Text>
        </ReviewField>
        <ReviewField label="Version">
          <Text fontSize="md">{model.version || "1.0"}</Text>
        </ReviewField>
        {showStatus ? (
          <ReviewField label="Status">
            <Badge
              colorScheme={isModelVersionStatusActive(model.versionStatus) ? "green" : "gray"}
              fontSize="sm"
              p={2}
            >
              {formatModelVersionStatusLabel(model.versionStatus)}
            </Badge>
          </ReviewField>
        ) : null}
        <ReviewField label="Task type">
          <Badge colorScheme={getTaskColorScheme(taskType)} fontSize="sm" p={2}>
            {taskType ? taskType.toUpperCase() : "N/A"}
          </Badge>
        </ReviewField>
      </SimpleGrid>

      <Box mt={4}>
        <ReviewField label="Description">
          <Text fontSize="md">{textValue(model.description)}</Text>
        </ReviewField>
      </Box>

      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4} mt={4}>
        <ReviewField label="License">
          <Text fontSize="md">{licenseLabel(model.license)}</Text>
        </ReviewField>
        <ReviewField label="Source">
          <Text fontSize="md">{textValue(source)}</Text>
        </ReviewField>
        {model.licenseUrl ? (
          <ReviewField label="License URL">
            <Text fontSize="md">{model.licenseUrl}</Text>
          </ReviewField>
        ) : null}
        <ReviewField label="Language auto-detection">
          <Text fontSize="md">{model.isLangDetectionEnabled ? "Enabled" : "Disabled"}</Text>
        </ReviewField>
        <ReviewField label="Multilingual">
          <Text fontSize="md">{model.isMultilingual ? "Yes" : "No"}</Text>
        </ReviewField>
      </SimpleGrid>

      <Box mt={4}>
        <FieldLabel variant="inline">Domain</FieldLabel>
        <HStack spacing={2} flexWrap="wrap" mt={1}>
          {domains.length > 0 ? (
            domains.map((domain) => (
              <Badge key={domain} fontSize="sm" colorScheme="gray" p={2}>
                {domain}
              </Badge>
            ))
          ) : (
            <Text color="ink.500" fontSize="sm">No domains specified</Text>
          )}
        </HStack>
      </Box>
    </Box>
  );
}
