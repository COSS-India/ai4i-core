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
  Text,
  VStack,
} from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import DataTable, { type DataTableColumn } from "../common/table";
import InfoTip from "../common/InfoTip";
import PercentageStepper, {
  type PercentageBound,
} from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { totalApplicationsExceeds100 } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { BulkBudgetDraft } from "./hooks/useApplicationManagement";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "—";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

function parsePctInput(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : -1;
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
  onPctBoundHit,
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
  onPctBoundHit: (applicationId: string, bound: PercentageBound) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const totalOver = liveTotalPct > 100 + 1e-6;

  const columns = useMemo<DataTableColumn<BulkBudgetDraft>[]>(
    () => [
      {
        id: "name",
        header: "Application",
        sortable: true,
        sortAccessor: (row) => row.name ?? "",
        cell: (row) => {
          const editable = row.status === "ACTIVE";
          return (
            <Box opacity={editable ? 1 : 0.75}>
              <Text fontWeight="600" fontSize="sm">
                {row.name}
              </Text>
              {!editable ? (
                <Badge mt={1} colorScheme="gray" fontSize="10px">
                  Inactive
                </Badge>
              ) : null}
            </Box>
          );
        },
      },
      {
        id: "used",
        header: "Used",
        sortable: true,
        sortAccessor: (row) => row.consumed_percentage ?? -1,
        cell: (row) => {
          if (row.consumed_percentage != null) {
            return (
              <>
                <Text fontSize="sm">{formatPct(row.consumed_percentage)}</Text>
                <Text fontSize="xs" color="gray.500">
                  {formatSpendMoney(row.consumed_budget ?? 0, currency)}
                </Text>
              </>
            );
          }
          if (row.rowError?.startsWith("Could not load")) {
            return (
              <Text fontSize="sm" color="red.500">
                Load failed — refocus to retry
              </Text>
            );
          }
          return (
            <Text fontSize="sm" color="gray.400">
              {row.keysLoading ? "Loading…" : "Focus row to load keys"}
            </Text>
          );
        },
      },
      {
        id: "budgetPct",
        header: "Budget %",
        sortable: true,
        sortAccessor: (row) => parsePctInput(row.pctInput),
        cell: (row) => {
          const editable = row.status === "ACTIVE";
          return (
            <FormControl isInvalid={Boolean(row.rowError)}>
              <PercentageStepper
                variant="inline"
                value={row.pctInput}
                onChange={(next) => onPctChange(row.application_id, next)}
                onBoundHit={(bound) => onPctBoundHit(row.application_id, bound)}
                onFocus={() => onRowFocus(row.application_id)}
                isDisabled={!editable}
              />
              {row.rowError ? (
                <FormErrorMessage mt={1}>{row.rowError}</FormErrorMessage>
              ) : null}
            </FormControl>
          );
        },
      },
      {
        id: "keyPreview",
        header: "Key preview",
        sortable: true,
        sortAccessor: (row) => row.keyPreviews.length,
        cell: (row) => {
          if (row.keysLoading) {
            return (
              <Text fontSize="xs" color="gray.500">
                Loading keys…
              </Text>
            );
          }
          if (row.keyPreviews.length === 0) {
            return (
              <Text fontSize="xs" color="gray.400">
                —
              </Text>
            );
          }
          return (
            <VStack align="stretch" spacing={1} maxW="220px">
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
          );
        },
      },
    ],
    [currency, onPctChange, onPctBoundHit, onRowFocus],
  );

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Budget"
      size="6xl"
      footer={
        <HStack spacing={3}>
          <Button variant="ghost" onClick={onClose}>
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
          {FIELD_HINTS.application.bulkBudgetEdit.intro}
        </Text>

        <Box bg="blue.50" borderRadius="md" p={4}>
          <HStack justify="space-between" mb={2}>
            <HStack spacing={1.5}>
              <Text
                fontSize="xs"
                fontWeight="bold"
                color="gray.500"
                textTransform="uppercase"
              >
                {FIELD_HINTS.application.bulkBudgetEdit.institutionBudgetAllocatedLabel}
              </Text>
              <InfoTip
                message={FIELD_HINTS.application.tooltips.institutionBudgetAllocated}
              />
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

        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.application_id}
          defaultSortKey="name"
          defaultSortDirection="asc"
          isLoading={isLoading}
          isEmpty={!isLoading && rows.length === 0}
          emptyMessage="No Applications to edit."
          asyncStateHeight="160px"
          borderRadius="md"
          theadBg="gray.50"
          cellPy={2}
          containerMt={0}
        />
      </VStack>
    </StandardModal>
  );
}
