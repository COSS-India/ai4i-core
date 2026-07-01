import React, { useMemo } from "react";
import {
  Badge,
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Input,
  Select,
  Text,
  Tooltip,
  VStack,
  NumberInput,
  NumberInputField,
  Divider,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import ConfirmDialog from "../common/ConfirmDialog";
import StandardModal from "../common/StandardModal";
import { useTierManagement } from "../../hooks/useTierManagement";
import type { Tier } from "../../services/tierManagementService";
import type { TierFormData, TierFormQuota } from "../../types/tierManagement";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";

function getTaskTypeBadgeColor(taskType: string): string {
  switch (taskType.toUpperCase()) {
    case "LLM":
      return "purple";
    case "ASR":
      return "orange";
    case "NMT":
      return "green";
    case "TTS":
      return "blue";
    case "OCR":
      return "teal";
    case "PIPELINE":
      return "pink";
    case "NER":
      return "red";
    default:
      return "gray";
  }
}

// ─── Column cell renderers (defined outside TierManagement to avoid S6478) ───

const TIER_NAME_COLUMN: AdminTableColumn<Tier> = {
  id: "name",
  header: "Tier Name",
  cell: (tier) => (
    <Text fontSize="sm" fontWeight="medium">
      {tier.name}
    </Text>
  ),
};

const TIER_TASK_TYPES_COLUMN: AdminTableColumn<Tier> = {
  id: "taskTypes",
  header: "Model Task Types",
  cell: (tier) => (
    <HStack spacing={1} flexWrap="wrap">
      {tier.quotas?.map((q) => (
        <Badge
          key={q.modelTaskType}
          colorScheme={getTaskTypeBadgeColor(q.modelTaskType)}
          fontSize="xs"
          px={2}
          py={0.5}
        >
          {q.modelTaskType}
        </Badge>
      )) ?? (
        <Text fontSize="sm" color="gray.400">
          —
        </Text>
      )}
    </HStack>
  ),
};

interface TierActionsCellProps {
  readonly tier: Tier;
  readonly deletingId: string | null;
  readonly onView: (tier: Tier) => void;
  readonly onEdit: (tier: Tier) => void;
  readonly onDelete: (tier: Tier) => void;
}

function TierActionsCell({
  tier,
  deletingId,
  onView,
  onEdit,
  onDelete,
}: TierActionsCellProps) {
  return (
    <HStack spacing={1}>
      <Tooltip label="View" placement="top" hasArrow>
        <IconButton
          aria-label="View tier"
          icon={<ViewIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          _hover={{ bg: "blue.50" }}
          onClick={() => onView(tier)}
        />
      </Tooltip>
      <Tooltip label="Edit" placement="top" hasArrow>
        <IconButton
          aria-label="Edit tier"
          icon={<EditIcon />}
          size="sm"
          variant="ghost"
          colorScheme="green"
          _hover={{ bg: "green.50" }}
          onClick={() => onEdit(tier)}
        />
      </Tooltip>
      <Tooltip label="Delete" placement="top" hasArrow>
        <IconButton
          aria-label="Delete tier"
          icon={<DeleteIcon />}
          size="sm"
          variant="ghost"
          colorScheme="red"
          _hover={{ bg: "red.50" }}
          onClick={() => onDelete(tier)}
          isLoading={deletingId === tier.id}
          isDisabled={deletingId !== null}
        />
      </Tooltip>
    </HStack>
  );
}

function makeTierActionsColumn(
  deletingId: string | null,
  onView: (tier: Tier) => void,
  onEdit: (tier: Tier) => void,
  onDelete: (tier: Tier) => void,
): AdminTableColumn<Tier> {
  return {
    id: "actions",
    header: "Actions",
    tdProps: { onClick: (e: React.MouseEvent) => e.stopPropagation() },
    cell: (tier) => (
      <TierActionsCell
        tier={tier}
        deletingId={deletingId}
        onView={onView}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    ),
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface QuotaEditorProps {
  readonly quotas: TierFormQuota[];
  readonly onChange: (quotas: TierFormQuota[]) => void;
  readonly taskTypeNames: string[];
  readonly unitByTaskType: Record<string, string>;
}

function QuotaEditor({
  quotas,
  onChange,
  taskTypeNames,
  unitByTaskType,
}: QuotaEditorProps) {
  const handleQuotaChange = (
    idx: number,
    field: keyof TierFormQuota,
    value: string,
  ) => {
    const updated = quotas.map((q, i) => {
      if (i !== idx) return q;
      if (field === "modelTaskType") {
        return {
          ...q,
          modelTaskType: value,
          unit: unitByTaskType[value] ?? "",
        };
      }
      return { ...q, [field]: value };
    });
    onChange(updated);
  };

  const addQuota = () => {
    onChange([
      ...quotas,
      {
        _key: crypto.randomUUID(),
        modelTaskType: "",
        unit: "",
        limit: "",
      },
    ]);
  };

  const removeQuota = (idx: number) =>
    onChange(quotas.filter((_, i) => i !== idx));

  return (
    <VStack align="stretch" spacing={3}>
      <HStack justify="space-between">
        <Text fontSize="sm" fontWeight="semibold" color="gray.700">
          Quotas
        </Text>
        <Button
          size="xs"
          leftIcon={<AddIcon />}
          variant="outline"
          colorScheme="blue"
          onClick={addQuota}
        >
          Add Quota
        </Button>
      </HStack>

      <Box maxH="340px" overflowY="auto" pr={1}>
        <VStack align="stretch" spacing={3}>
          {quotas.map((quota, idx) => (
            <Box
              key={quota._key ?? `${quota.modelTaskType}-${idx}`}
              p={3}
              borderWidth="1px"
              borderRadius="md"
              borderColor="gray.200"
              bg="gray.50"
            >
              <HStack align="flex-end" spacing={3} flexWrap="wrap">
                <FormControl w={{ base: "full", sm: "160px" }} isRequired>
                  <FormLabel fontSize="xs" mb={1}>
                    Model Task Type
                  </FormLabel>
                  <Select
                    size="sm"
                    value={quota.modelTaskType}
                    onChange={(e) =>
                      handleQuotaChange(idx, "modelTaskType", e.target.value)
                    }
                  >
                    <option value="" disabled>
                      Select model task type
                    </option>
                    {taskTypeNames
                      .filter((t) => {
                        const selectedElsewhere = quotas
                          .filter((_, i) => i !== idx)
                          .map((q) => q.modelTaskType);
                        return (
                          !selectedElsewhere.includes(t) ||
                          t === quota.modelTaskType
                        );
                      })
                      .map((t) => (
                        <option key={t} value={t}>
                          {formatModelTaskTypeLabel(t)}
                        </option>
                      ))}
                  </Select>
                </FormControl>

                <FormControl w={{ base: "full", sm: "130px" }}>
                  <FormLabel fontSize="xs" mb={1}>
                    Unit
                  </FormLabel>
                  <Input
                    size="sm"
                    value={quota.unit}
                    isReadOnly
                    placeholder="-"
                    bg="gray.50"
                    cursor="default"
                  />
                </FormControl>

                <FormControl w={{ base: "full", sm: "120px" }} isRequired>
                  <FormLabel fontSize="xs" mb={1}>
                    Limit
                  </FormLabel>
                  <NumberInput
                    size="sm"
                    min={0}
                    value={quota.limit}
                    onChange={(v) => handleQuotaChange(idx, "limit", v)}
                  >
                    <NumberInputField placeholder="e.g. 10000" />
                  </NumberInput>
                </FormControl>

                {quotas.length > 1 && (
                  <IconButton
                    aria-label="Remove quota"
                    icon={<DeleteIcon />}
                    size="sm"
                    variant="ghost"
                    colorScheme="red"
                    onClick={() => removeQuota(idx)}
                    alignSelf="flex-end"
                  />
                )}
              </HStack>
            </Box>
          ))}
        </VStack>
      </Box>
    </VStack>
  );
}

interface TierFormProps {
  readonly formData: TierFormData;
  readonly onChange: (data: TierFormData) => void;
  readonly taskTypeNames: string[];
  readonly unitByTaskType: Record<string, string>;
}

function TierForm({
  formData,
  onChange,
  taskTypeNames,
  unitByTaskType,
}: TierFormProps) {
  return (
    <VStack align="stretch" spacing={4}>
      <FormControl isRequired>
        <FormLabel fontWeight="semibold">Tier Name</FormLabel>
        <Input
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
          placeholder="e.g. Enterprise"
        />
      </FormControl>

      <FormControl>
        <FormLabel fontWeight="semibold">Description</FormLabel>
        <Input
          value={formData.description}
          onChange={(e) =>
            onChange({ ...formData, description: e.target.value })
          }
          placeholder="e.g. Enterprise tier for high usage"
        />
      </FormControl>

      <Divider />

      <QuotaEditor
        quotas={formData.quotas}
        onChange={(quotas) => onChange({ ...formData, quotas })}
        taskTypeNames={taskTypeNames}
        unitByTaskType={unitByTaskType}
      />
    </VStack>
  );
}

// ─── Page component ───────────────────────────────────────────────────────────

const TierManagement: React.FC = () => {
  const { taskTypeNames, unitByTaskType } = useInferenceTypes();

  const {
    searchQuery,
    setSearchQuery,
    filterTaskType,
    setFilterTaskType,
    hasActiveFilters,
    clearFilters,
    filteredTiers,
    tiers,
    isLoading,
    tierToDelete,
    deletingId,
    isDeleteOpen,
    onDeleteClose,
    handleDeleteClick,
    handleDeleteConfirm,
    isCreateOpen,
    onCreateClose,
    handleOpenCreate,
    handleCreateSubmit,
    editingTier,
    isEditOpen,
    onEditClose,
    handleOpenEdit,
    handleEditSubmit,
    viewTier,
    isViewOpen,
    onViewClose,
    handleViewClick,
    formData,
    setFormData,
    isSubmitting,
    cancelRef,
  } = useTierManagement();

  const columns = useMemo(
    () => [
      TIER_NAME_COLUMN,
      TIER_TASK_TYPES_COLUMN,
      makeTierActionsColumn(
        deletingId,
        handleViewClick,
        handleOpenEdit,
        handleDeleteClick,
      ),
    ],
    [deletingId, handleDeleteClick, handleOpenEdit, handleViewClick],
  );

  const tierFormFooter = (
    <HStack justify="flex-end" spacing={3}>
      <Button
        variant="outline"
        onClick={isCreateOpen ? onCreateClose : onEditClose}
      >
        Cancel
      </Button>
      <Button
        colorScheme="blue"
        isLoading={isSubmitting}
        loadingText={isCreateOpen ? "Creating..." : "Saving..."}
        onClick={isCreateOpen ? handleCreateSubmit : handleEditSubmit}
      >
        {isCreateOpen ? "Create Tier" : "Save Changes"}
      </Button>
    </HStack>
  );

  return (
    <Box>
      <AdminDataTable
        items={filteredTiers}
        columns={columns}
        getRowKey={(tier) => tier.id}
        isLoading={isLoading}
        loadingMessage="Loading tiers..."
        emptyMessage="No tiers found. Create your first tier to get started."
        noResultsMessage="No tiers match the current filters."
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        unfilteredCount={tiers.length}
        paginate="client"
        filterToolbarAlign="flex-start"
        filterToolbarRightContent={
          <Box ml="auto">
            <Button
              leftIcon={<AddIcon />}
              colorScheme="blue"
              size="sm"
              onClick={handleOpenCreate}
            >
              Create Tier
            </Button>
          </Box>
        }
        filters={
          <HStack spacing={3} flexWrap="wrap" align="flex-end">
            <TableSearchField
              label=""
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="Search tiers..."
              formControlProps={{ w: { base: "full", md: "220px" }, mb: 0 }}
              inputGroupProps={{ size: "sm" }}
            />
            <TableSelectField
              label=""
              value={filterTaskType}
              onChange={setFilterTaskType}
              formControlProps={{ w: { base: "full", sm: "210px" }, mb: 0 }}
              selectProps={{ size: "sm" }}
            >
              <option value="">Filter by Model Task Type - All</option>
              {taskTypeNames.map((t) => (
                <option key={t} value={t}>
                  {formatModelTaskTypeLabel(t)}
                </option>
              ))}
            </TableSelectField>
          </HStack>
        }
      />

      {/* Delete confirmation */}
      <ConfirmDialog
        isOpen={isDeleteOpen}
        onClose={onDeleteClose}
        onConfirm={handleDeleteConfirm}
        title="Delete Tier"
        body={
          <>
            Are you sure you want to delete the tier{" "}
            <strong>{tierToDelete?.name}</strong>? This action cannot be undone
            and may affect tenants currently assigned to this tier.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={deletingId === tierToDelete?.id}
        confirmLoadingText="Deleting..."
        leastDestructiveRef={cancelRef}
      />

      {/* Create Tier modal */}
      <StandardModal
        isOpen={isCreateOpen}
        onClose={onCreateClose}
        title="Create Tier"
        size="xl"
        closeOnOverlayClick={!isSubmitting}
        footer={tierFormFooter}
        contentProps={{
          maxH: "85vh",
          display: "flex",
          flexDirection: "column",
        }}
        bodyProps={{ overflowY: "auto", flex: 1 }}
      >
        <TierForm
          formData={formData}
          onChange={setFormData}
          taskTypeNames={taskTypeNames}
          unitByTaskType={unitByTaskType}
        />
      </StandardModal>

      {/* Edit Tier modal */}
      <StandardModal
        isOpen={isEditOpen}
        onClose={onEditClose}
        title={`Edit Tier: ${editingTier?.name ?? ""}`}
        size="xl"
        closeOnOverlayClick={!isSubmitting}
        footer={tierFormFooter}
        contentProps={{
          maxH: "85vh",
          display: "flex",
          flexDirection: "column",
        }}
        bodyProps={{ overflowY: "auto", flex: 1 }}
      >
        <TierForm
          formData={formData}
          onChange={setFormData}
          taskTypeNames={taskTypeNames}
          unitByTaskType={unitByTaskType}
        />
      </StandardModal>

      {/* View Tier modal */}
      <StandardModal
        isOpen={isViewOpen}
        onClose={onViewClose}
        title={`Tier Details — ${viewTier?.name ?? ""}`}
        size="md"
        footer={
          <Button variant="outline" onClick={onViewClose}>
            Close
          </Button>
        }
      >
        {viewTier && (
          <VStack align="stretch" spacing={5}>
            {/* Name + description */}
            <Box>
              <Text fontSize="lg" fontWeight="bold" color="gray.800">
                {viewTier.name}
              </Text>
              {viewTier.description && (
                <Text fontSize="sm" color="gray.500" mt={0.5}>
                  {viewTier.description}
                </Text>
              )}
            </Box>

            {/* Quotas as label/value rows */}
            <VStack align="stretch" spacing={2}>
              {viewTier.quotas?.length ? (
                viewTier.quotas.map((q) => (
                  <HStack key={q.modelTaskType} spacing={2}>
                    <Badge
                      colorScheme={getTaskTypeBadgeColor(q.modelTaskType)}
                      fontSize="xs"
                    >
                      {q.modelTaskType}
                    </Badge>
                    <Text fontSize="sm" color="gray.600">
                      Quota:
                    </Text>
                    <Text fontSize="sm" fontWeight="semibold" color="gray.800">
                      {q.limit.toLocaleString()}
                    </Text>
                  </HStack>
                ))
              ) : (
                <Text fontSize="sm" color="gray.400">
                  —
                </Text>
              )}
            </VStack>

            <Divider />

            {/* Services Mapped — not yet provided by the tier API */}
            <Box>
              <Text
                fontSize="xs"
                fontWeight="semibold"
                color="gray.500"
                textTransform="uppercase"
                mb={1}
              >
                Services Mapped
              </Text>
              <Text fontSize="sm" color="gray.400">
                —
              </Text>
            </Box>

            {/* Tenants Assigned — not yet provided by the tier API */}
            <Box>
              <Text
                fontSize="xs"
                fontWeight="semibold"
                color="gray.500"
                textTransform="uppercase"
                mb={1}
              >
                Tenants Assigned
              </Text>
              <Text fontSize="sm" color="gray.400">
                —
              </Text>
            </Box>

            <Divider />

            {/* Created */}
            {viewTier.createdAt && (
              <Box>
                <Text
                  fontSize="xs"
                  fontWeight="semibold"
                  color="gray.500"
                  textTransform="uppercase"
                  mb={1}
                >
                  Created
                </Text>
                <Text fontSize="sm" color="gray.700">
                  {new Date(viewTier.createdAt).toLocaleDateString(undefined, {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </Text>
              </Box>
            )}
          </VStack>
        )}
      </StandardModal>
    </Box>
  );
};

export default TierManagement;
