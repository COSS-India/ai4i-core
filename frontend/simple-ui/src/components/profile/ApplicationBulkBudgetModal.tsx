import React, { useMemo } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  HStack,
  Input,
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
import { FIELD_HINTS } from "../../config/fieldHints";
import { totalApplicationsExceeds100 } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { BulkBudgetDraft } from "./hooks/useApplicationManagement";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "—";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

function PercentageStepper({
  value,
  onChange,
  onFocus,
  min = 0,
  max = 100,
  isDisabled = false,
}: {
  value: string;
  onChange: (next: string) => void;
  onFocus?: () => void;
  min?: number;
  max?: number;
  isDisabled?: boolean;
}) {
  const numeric = value.trim() === "" ? null : Number(value);
  return (
    <HStack spacing={1} align="center">
      <Input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        min={min}
        max={max}
        step={0.01}
        size="sm"
        w="88px"
        bg="white"
        isDisabled={isDisabled}
      />
      <Text color="gray.500" fontSize="sm" fontWeight="semibold">%</Text>
    </HStack>
  );
}

export default function ApplicationBulkBudgetModal({
  isOpen,
  onClose,
  isLoading,
  isSaving,
  banner,
  tenantBudget,
  institutionBudgetUnset,
  currency,
  liveTotalPct,
  rows,
  onRowFocus,
  onPctChange,
  onSave,
  canSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  isLoading: boolean;
  isSaving: boolean;
  banner: string | null;
  tenantBudget: number;
  institutionBudgetUnset: boolean;
  currency: string;
  liveTotalPct: number;
  rows: BulkBudgetDraft[];
  onRowFocus: (applicationId: string) => void;
  onPctChange: (applicationId: string, value: string) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const totalOver = liveTotalPct > 100 + 1e-6;

  const body = useMemo(() => {
    if (isLoading) {
      return (
        <Text color="gray.500" py={8} textAlign="center">
          Loading Applications…
        </Text>
      );
    }
    if (rows.length === 0) {
      return (
        <Text color="gray.500" py={8} textAlign="center">
          No Applications to edit.
        </Text>
      );
    }
    return (
      <Box borderWidth="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
        <Table size="sm">
          <Thead bg="gray.50">
            <Tr>
              <Th>Application</Th>
              <Th>Used</Th>
              <Th>Budget %</Th>
              <Th>Key preview</Th>
            </Tr>
          </Thead>
          <Tbody>
            {rows.map((row) => {
              const editable = row.status === "ACTIVE";
              return (
              <Tr key={row.application_id} verticalAlign="top" opacity={editable ? 1 : 0.75}>
                <Td>
                  <Text fontWeight="600" fontSize="sm">{row.name}</Text>
                  {!editable ? (
                    <Badge mt={1} colorScheme="gray" fontSize="10px">
                      Inactive
                    </Badge>
                  ) : null}
                  {row.rowError ? (
                    <Text fontSize="xs" color="red.500" mt={1}>{row.rowError}</Text>
                  ) : null}
                </Td>
                <Td>
                  {row.consumed_percentage != null ? (
                    <>
                      <Text fontSize="sm">{formatPct(row.consumed_percentage)}</Text>
                      <Text fontSize="xs" color="gray.500">
                        {formatSpendMoney(row.consumed_budget ?? 0, currency)}
                      </Text>
                    </>
                  ) : row.rowError ? (
                    <Text fontSize="sm" color="red.500">
                      Load failed — refocus to retry
                    </Text>
                  ) : (
                    <Text fontSize="sm" color="gray.400">
                      {row.keysLoading ? "Loading…" : "Focus row to load keys"}
                    </Text>
                  )}
                </Td>
                <Td>
                  <FormControl isInvalid={Boolean(row.rowError)}>
                    <PercentageStepper
                      value={row.pctInput}
                      onChange={(next) => onPctChange(row.application_id, next)}
                      onFocus={() => onRowFocus(row.application_id)}
                      min={
                        row.consumed_percentage != null ? row.consumed_percentage : 0
                      }
                      max={100}
                      isDisabled={!editable}
                    />
                  </FormControl>
                </Td>
                <Td maxW="220px">
                  {row.keysLoading ? (
                    <Text fontSize="xs" color="gray.500">Loading keys…</Text>
                  ) : row.keyPreviews.length === 0 ? (
                    <Text fontSize="xs" color="gray.400">—</Text>
                  ) : (
                    <VStack align="stretch" spacing={1}>
                      {row.keyPreviews.map((key) => (
                        <Text
                          key={key.id}
                          fontSize="xs"
                          color={key.floorViolation ? "red.500" : "gray.600"}
                        >
                          {key.key_name}: {formatPct(key.allocated_percentage)} ·{" "}
                          {formatSpendMoney(key.allocated_budget, currency)}
                        </Text>
                      ))}
                    </VStack>
                  )}
                </Td>
              </Tr>
            );
            })}
          </Tbody>
        </Table>
      </Box>
    );
  }, [
    isLoading,
    rows,
    currency,
    onPctChange,
    onRowFocus,
    institutionBudgetUnset,
  ]);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Budget"
      size="6xl"
      footer={
        <HStack spacing={3}>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
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
          {FIELD_HINTS.application.bulkBudgetEdit.intro}
        </Text>

        <Box bg="blue.50" borderRadius="md" p={4}>
          <HStack justify="space-between" mb={2}>
            <HStack spacing={1.5}>
              <Text fontSize="xs" fontWeight="bold" color="gray.500" textTransform="uppercase">
                {FIELD_HINTS.application.bulkBudgetEdit.institutionBudgetAllocatedLabel}
              </Text>
              <InfoTip message={FIELD_HINTS.application.tooltips.institutionBudgetAllocated} />
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
            {FIELD_HINTS.application.bulkBudgetEdit.institutionTotalPrefix}{" "}
            {formatSpendMoney(tenantBudget, currency)}
          </Text>
        </Box>

        {institutionBudgetUnset && (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            {FIELD_HINTS.application.institutionBudgetNotSet}
          </Alert>
        )}

        {totalOver && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {totalApplicationsExceeds100(liveTotalPct)}
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
