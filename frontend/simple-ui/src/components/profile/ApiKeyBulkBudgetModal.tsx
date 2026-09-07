import React, { useMemo } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Input,
  Select,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import InfoTip from "../common/InfoTip";
import PercentageStepper, {
  type PercentageBound,
} from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { editKeyBudgetTitle, totalApiKeysExceeds100 } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { Application } from "../../types/application";
import type { KeyBudgetDraft } from "./hooks/useApiKeyBudgetEdit";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "—";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

export default function ApiKeyBulkBudgetModal({
  isOpen,
  onClose,
  isLoading,
  isSaving,
  banner,
  applications,
  selectedApplicationId,
  onApplicationChange,
  applicationName,
  applicationBudget,
  applicationAllocatedPct,
  applicationBudgetUnset,
  liveTotalPct,
  rows,
  onPctChange,
  onPctBoundHit,
  onAmountChange,
  onSave,
  canSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  isLoading: boolean;
  isSaving: boolean;
  banner: string | null;
  applications: Application[];
  selectedApplicationId: string;
  onApplicationChange: (applicationId: string) => void;
  applicationName: string;
  applicationBudget: number;
  applicationAllocatedPct: number | null;
  applicationBudgetUnset: boolean;
  liveTotalPct: number;
  rows: KeyBudgetDraft[];
  onPctChange: (apiKeyId: number, value: string) => void;
  onPctBoundHit: (apiKeyId: number, bound: PercentageBound) => void;
  onAmountChange: (apiKeyId: number, value: string) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const totalOver = liveTotalPct > 100 + 1e-6;
  const currency = "INR";

  const body = useMemo(() => {
    if (!selectedApplicationId) {
      return (
        <Text color="gray.500" py={8} textAlign="center">
          {FIELD_HINTS.apiKey.bulkBudgetEdit.selectApplicationPrompt}
        </Text>
      );
    }
    if (isLoading) {
      return (
        <Text color="gray.500" py={8} textAlign="center">
          {FIELD_HINTS.apiKey.bulkBudgetEdit.loading}
        </Text>
      );
    }
    if (rows.length === 0) {
      return (
        <Text color="gray.500" py={8} textAlign="center">
          {FIELD_HINTS.apiKey.bulkBudgetEdit.empty}
        </Text>
      );
    }
    return (
      <Box borderWidth="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
        <Table size="sm">
          <Thead bg="gray.50">
            <Tr>
              <Th>Key</Th>
              <Th>Used</Th>
              <Th>Budget %</Th>
              <Th>Budget ({currency})</Th>
            </Tr>
          </Thead>
          <Tbody>
            {rows.map((row) => (
              <Tr key={row.api_key_id} verticalAlign="top">
                <Td>
                  <Text fontWeight="600" fontSize="sm">
                    {row.key_name}
                  </Text>
                </Td>
                <Td>
                  <Text fontSize="sm">{formatPct(row.consumed_percentage)}</Text>
                  <Text fontSize="xs" color="gray.500">
                    {formatSpendMoney(row.consumed_budget ?? 0, currency)}
                  </Text>
                </Td>
                <Td>
                  <FormControl isInvalid={Boolean(row.rowError)}>
                    <PercentageStepper
                      variant="inline"
                      value={row.pctInput}
                      onChange={(next) => onPctChange(row.api_key_id, next)}
                      onBoundHit={(bound) => onPctBoundHit(row.api_key_id, bound)}
                    />
                    {row.rowError ? (
                      <FormErrorMessage mt={1}>{row.rowError}</FormErrorMessage>
                    ) : null}
                  </FormControl>
                </Td>
                <Td>
                  <Input
                    type="number"
                    size="sm"
                    w="120px"
                    bg="white"
                    value={row.amountInput}
                    onChange={(e) => onAmountChange(row.api_key_id, e.target.value)}
                    min={row.consumed_budget ?? undefined}
                    step={0.01}
                    isDisabled={applicationBudgetUnset}
                    placeholder={applicationBudgetUnset ? "—" : undefined}
                  />
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>
    );
  }, [
    selectedApplicationId,
    isLoading,
    rows,
    onPctChange,
    onPctBoundHit,
    onAmountChange,
    applicationBudgetUnset,
  ]);

  const title = editKeyBudgetTitle(applicationName || undefined);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="4xl"
      footer={
        <HStack spacing={3}>
          <Button variant="ghost" onClick={onClose} isDisabled={isSaving}>
            Cancel
          </Button>
          <Button
            colorScheme="blue"
            isLoading={isSaving}
            isDisabled={!canSave}
            onClick={() => void onSave()}
          >
            Save changes
          </Button>
        </HStack>
      }
    >
      <VStack align="stretch" spacing={4}>
        <Text fontSize="sm" color="gray.600">
          {FIELD_HINTS.apiKey.bulkBudgetEdit.intro}
        </Text>

        <FormControl isRequired>
          <FormLabel fontSize="sm" fontWeight="semibold">
            Application
          </FormLabel>
          <Select
            placeholder={FIELD_HINTS.apiKey.bulkBudgetEdit.selectApplicationPlaceholder}
            value={selectedApplicationId}
            onChange={(e) => onApplicationChange(e.target.value)}
            bg="white"
          >
            {applications.map((app) => (
              <option key={app.application_id} value={app.application_id}>
                {app.name}
              </option>
            ))}
          </Select>
        </FormControl>

        {selectedApplicationId && (
          <Box bg="blue.50" borderRadius="md" p={4}>
            <HStack justify="space-between" mb={2}>
              <HStack spacing={1.5}>
                <Text
                  fontSize="xs"
                  fontWeight="bold"
                  color="gray.500"
                  textTransform="uppercase"
                >
                  {FIELD_HINTS.apiKey.bulkBudgetEdit.allocatedToKeysLabel}
                </Text>
                <InfoTip message={FIELD_HINTS.apiKey.tooltips.budgetAllocation} />
              </HStack>
              <Text fontWeight="bold" color={totalOver ? "red.500" : undefined}>
                {formatPct(liveTotalPct)}
              </Text>
            </HStack>
            <Box h="8px" bg="gray.200" borderRadius="full" overflow="hidden">
              <Box
                h="100%"
                bg={totalOver ? "red.500" : "blue.500"}
                width={`${Math.min(liveTotalPct, 100)}%`}
              />
            </Box>
            <Text fontSize="xs" color="gray.500" mt={2}>
              {FIELD_HINTS.apiKey.bulkBudgetEdit.applicationAllocationPrefix}{" "}
              {applicationAllocatedPct != null
                ? formatPct(applicationAllocatedPct)
                : "—"}{" "}
              · {formatSpendMoney(applicationBudget, currency)}
            </Text>
          </Box>
        )}

        {applicationBudgetUnset && selectedApplicationId && (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            {FIELD_HINTS.apiKey.bulkBudgetEdit.applicationBudgetUnset}
          </Alert>
        )}

        {totalOver && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {totalApiKeysExceeds100(liveTotalPct)}
          </Alert>
        )}

        {banner && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {banner}
          </Alert>
        )}

        {body}
      </VStack>
    </StandardModal>
  );
}
