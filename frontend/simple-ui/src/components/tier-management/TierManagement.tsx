import React, { useMemo } from "react";
import {
  Badge,
  Box,
  Button,
  Drawer,
  DrawerOverlay,
  DrawerContent,
  DrawerCloseButton,
  DrawerHeader,
  DrawerBody,
  DrawerFooter,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  IconButton,
  Input,
  Select,
  Spinner,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Tooltip,
  VStack,
  NumberInput,
  NumberInputField,
  Divider,
  Grid,
} from "@chakra-ui/react";
import {
  AddIcon,
  DeleteIcon,
  EditIcon,
  SmallCloseIcon,
  ViewIcon,
} from "@chakra-ui/icons";
import { FiCalendar } from "react-icons/fi";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import ConfirmDialog from "../common/ConfirmDialog";
import { FORM_LABEL_TO_INPUT_PT } from "../common/FormFieldsRow";
import StandardModal from "../common/StandardModal";
import { useTierManagement } from "../../hooks/useTierManagement";
import type { Tier } from "../../services/tierManagementService";
import type { TierFormData, TierFormQuota } from "../../types/tierManagement";
import { INSTITUTIONS, formatModelTaskTypeLabel } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { generateUUID } from "../../utils/uuid";

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

function formatQuotaAmount(
  limit: number,
  unit?: string,
): { boldText: string; suffixText: string } {
  const trimmedUnit = (unit ?? "").trim();
  const spaceIdx = trimmedUnit.indexOf(" ");
  if (spaceIdx === -1) {
    return {
      boldText: limit.toLocaleString(),
      suffixText: trimmedUnit ? `${trimmedUnit.toLowerCase()}/month` : "/month",
    };
  }
  const prefix = trimmedUnit.slice(0, spaceIdx);
  const rest = trimmedUnit.slice(spaceIdx + 1);
  return {
    boldText: `${limit.toLocaleString()}${prefix}`,
    suffixText: `${rest.toLowerCase()}/month`,
  };
}

// ─── Column cell renderers (defined outside TierManagement to avoid S6478) ───

const TIER_NAME_COLUMN: AdminTableColumn<Tier> = {
  id: "name",
  header: "Tier Name",
  thProps: { w: "420px", maxW: "420px" },
  tdProps: { maxW: "420px" },
  cell: (tier) => (
    <Tooltip label={tier.name} placement="top" hasArrow openDelay={300}>
      <Text fontSize="sm" fontWeight="medium" isTruncated maxW="430px">
        {tier.name}
      </Text>
    </Tooltip>
  ),
};

const TIER_TASK_TYPES_VISIBLE_COUNT = 4;

const TIER_TASK_TYPES_COLUMN: AdminTableColumn<Tier> = {
  id: "taskTypes",
  header: "Model Task Types",
  thProps: { textAlign: "center" },
  tdProps: { textAlign: "center" },
  cell: (tier) => (
    <HStack spacing={1} flexWrap="wrap" justify="center">
      {(tier.quotas ?? []).slice(0, TIER_TASK_TYPES_VISIBLE_COUNT).map((q) => (
        <Badge
          key={q.modelTaskType}
          colorScheme={getTaskTypeBadgeColor(q.modelTaskType)}
          fontSize="xs"
          px={2}
          py={0.5}
        >
          {q.modelTaskType}
        </Badge>
      ))}
      {(tier.quotas?.length ?? 0) > TIER_TASK_TYPES_VISIBLE_COUNT && (
        <Badge colorScheme="gray" fontSize="xs" px={2} py={0.5}>
          +{tier.quotas!.length - TIER_TASK_TYPES_VISIBLE_COUNT}
        </Badge>
      )}
      {!tier.quotas?.length && (
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
    <HStack spacing={1} justify="center">
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
    thProps: { textAlign: "center" },
    tdProps: {
      textAlign: "center",
      onClick: (e: React.MouseEvent) => e.stopPropagation(),
    },
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
  readonly onSchedule?: (quota: TierFormQuota) => void;
  readonly onRemove?: (quota: TierFormQuota) => void;
  readonly removingTaskType?: string | null;
  readonly isEditMode?: boolean;
  readonly showErrors?: boolean;
}

function isUnitInvalid(quota: TierFormQuota): boolean {
  return !quota.unit.trim();
}

function isLimitInvalid(quota: TierFormQuota): boolean {
  const limitNum = Number(quota.limit);
  return (
    quota.limit.trim() === "" || !Number.isFinite(limitNum) || limitNum <= 0
  );
}

function QuotaEditor({
  quotas,
  onChange,
  taskTypeNames,
  unitByTaskType,
  onSchedule,
  onRemove,
  removingTaskType,
  isEditMode,
  showErrors,
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
        _key: generateUUID(),
        modelTaskType: "",
        unit: "",
        limit: "",
      },
    ]);
  };

  const removeQuota = (idx: number) =>
    onChange(quotas.filter((_, i) => i !== idx));

  // "Add Quota" only makes sense when there's more than one model task type
  // to choose from, and only while there's an unused type left to add.
  const canAddQuota =
    taskTypeNames.length > 1 && quotas.length < taskTypeNames.length;

  return (
    <VStack align="stretch" spacing={3}>
      <HStack justify="space-between">
        <Text fontSize="sm" fontWeight="semibold" color="gray.700">
          Quotas
        </Text>
        {!isEditMode && canAddQuota && (
          <Button
            size="xs"
            leftIcon={<AddIcon />}
            variant="outline"
            colorScheme="blue"
            onClick={addQuota}
          >
            Add Quota
          </Button>
        )}
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
              <HStack align="flex-start" spacing={3}>
                <Grid
                  templateColumns={{
                    base: "1fr",
                    sm: "minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr)",
                  }}
                  gap={3}
                  flex={1}
                  minW={0}
                  alignItems="start"
                >
                  <FormControl isRequired isDisabled={isEditMode} minW={0}>
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
                        ?.filter((t) => {
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

                  <FormControl
                    isRequired
                    isInvalid={showErrors && isUnitInvalid(quota)}
                    isDisabled={isEditMode}
                    minW={0}
                  >
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
                    <FormErrorMessage fontSize="xs">
                      Unit is required.
                    </FormErrorMessage>
                    <FieldHint show={!(showErrors && isUnitInvalid(quota))}>
                      {FIELD_HINTS.tier.quotaUnit.helper}
                    </FieldHint>
                  </FormControl>

                  <FormControl
                    isRequired
                    isInvalid={showErrors && isLimitInvalid(quota)}
                    isDisabled={isEditMode}
                    minW={0}
                  >
                    <FormLabel fontSize="xs" mb={1}>
                      Limit
                    </FormLabel>
                    <NumberInput
                      size="sm"
                      min={0}
                      value={quota.limit}
                      onChange={(v) => handleQuotaChange(idx, "limit", v)}
                    >
                      <NumberInputField
                        placeholder={FIELD_HINTS.tier.quotaLimit.placeholder}
                      />
                    </NumberInput>
                    <FormErrorMessage fontSize="xs">
                      Limit must be greater than 0.
                    </FormErrorMessage>
                    <FieldHint show={!(showErrors && isLimitInvalid(quota))}>
                      {FIELD_HINTS.tier.quotaLimit.helper}
                    </FieldHint>
                  </FormControl>
                </Grid>

                {quota.isExisting && onSchedule && (
                  <Tooltip label="Schedule a change" placement="top" hasArrow>
                    <IconButton
                      aria-label="Schedule a change"
                      icon={<FiCalendar />}
                      size="sm"
                      variant="ghost"
                      colorScheme="blue"
                      onClick={() => onSchedule(quota)}
                      mt={FORM_LABEL_TO_INPUT_PT}
                    />
                  </Tooltip>
                )}

                {!isEditMode && quota.isExisting && onRemove && (
                  <Tooltip label="Remove quota" placement="top" hasArrow>
                    <IconButton
                      aria-label="Remove quota"
                      icon={<SmallCloseIcon />}
                      size="sm"
                      variant="ghost"
                      colorScheme="gray"
                      isLoading={removingTaskType === quota.modelTaskType}
                      isDisabled={
                        !!removingTaskType &&
                        removingTaskType !== quota.modelTaskType
                      }
                      onClick={() => onRemove(quota)}
                      mt={FORM_LABEL_TO_INPUT_PT}
                    />
                  </Tooltip>
                )}

                {!isEditMode && !quota.isExisting && quotas.length > 1 && (
                  <IconButton
                    aria-label="Remove quota"
                    icon={<DeleteIcon />}
                    size="sm"
                    variant="ghost"
                    colorScheme="red"
                    onClick={() => removeQuota(idx)}
                    mt={FORM_LABEL_TO_INPUT_PT}
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
  readonly onSchedule?: (quota: TierFormQuota) => void;
  readonly onRemove?: (quota: TierFormQuota) => void;
  readonly removingTaskType?: string | null;
  readonly isEditMode?: boolean;
  readonly showErrors?: boolean;
}

function TierForm({
  formData,
  onChange,
  taskTypeNames,
  unitByTaskType,
  onSchedule,
  onRemove,
  removingTaskType,
  isEditMode,
  showErrors,
}: TierFormProps) {
  return (
    <VStack align="stretch" spacing={4}>
      <FormControl isRequired>
        <FormLabel fontWeight="semibold">Tier Name</FormLabel>
        <Input
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
          placeholder={FIELD_HINTS.tier.name.placeholder}
        />
        <FieldHint>{FIELD_HINTS.tier.name.helper}</FieldHint>
      </FormControl>

      <FormControl>
        <FormLabel fontWeight="semibold">Description</FormLabel>
        <Input
          value={formData.description}
          onChange={(e) =>
            onChange({ ...formData, description: e.target.value })
          }
          placeholder={FIELD_HINTS.tier.description.placeholder}
        />
        <FieldHint>{FIELD_HINTS.tier.description.helper}</FieldHint>
      </FormControl>

      <Divider />

      <QuotaEditor
        quotas={formData.quotas}
        onChange={(quotas) => onChange({ ...formData, quotas })}
        taskTypeNames={taskTypeNames}
        unitByTaskType={unitByTaskType}
        onSchedule={onSchedule}
        onRemove={onRemove}
        removingTaskType={removingTaskType}
        isEditMode={isEditMode}
        showErrors={showErrors}
      />
    </VStack>
  );
}

interface AssignedTenant {
  readonly tenantId: string;
  readonly organisation: string;
}

interface AssignedTenantsSectionProps {
  readonly tenants: AssignedTenant[];
  readonly isLoading: boolean;
  readonly pt?: number;
}

function AssignedTenantsSection({
  tenants,
  isLoading,
  pt,
}: AssignedTenantsSectionProps) {
  return (
    <Box pt={pt}>
      <Text
        fontSize="xs"
        fontWeight="semibold"
        color="gray.500"
        textTransform="uppercase"
        mb={1}
      >
        {INSTITUTIONS} Assigned · {isLoading ? "…" : tenants.length}
      </Text>
      {(() => {
        if (isLoading) {
          return (
            <HStack spacing={2} color="gray.400">
              <Spinner size="xs" />
              <Text fontSize="sm">Loading {INSTITUTIONS.toLowerCase()}…</Text>
            </HStack>
          );
        }
        if (!tenants.length) {
          return (
            <Text fontSize="sm" color="gray.400">
              No {INSTITUTIONS.toLowerCase()} assigned
            </Text>
          );
        }
        return (
          <VStack align="stretch" spacing={1}>
            {tenants.map((t) => (
              <HStack key={t.tenantId} justify="space-between">
                <Text fontSize="sm" color="gray.700" isTruncated>
                  {t.organisation}
                </Text>
                <Text fontSize="xs" color="gray.500" flexShrink={0}>
                  ID: {t.tenantId}
                </Text>
              </HStack>
            ))}
          </VStack>
        );
      })()}
    </Box>
  );
}

interface MappedService {
  readonly serviceId: string;
  readonly name: string;
  readonly taskType: string;
  readonly isPublished: boolean;
}

interface ServicesMappedSectionProps {
  readonly services: MappedService[];
  readonly isLoading: boolean;
}

function ServicesMappedSection({
  services,
  isLoading,
}: ServicesMappedSectionProps) {
  return (
    <Box>
      <Text
        fontSize="xs"
        fontWeight="semibold"
        color="gray.500"
        textTransform="uppercase"
        mb={1}
      >
        Services Mapped · {isLoading ? "…" : services.length}
      </Text>
      {(() => {
        if (isLoading) {
          return (
            <HStack spacing={2} color="gray.400">
              <Spinner size="xs" />
              <Text fontSize="sm">Loading services…</Text>
            </HStack>
          );
        }
        if (!services.length) {
          return (
            <Text fontSize="sm" color="gray.400">
              No services mapped
            </Text>
          );
        }
        return (
          <VStack align="stretch" spacing={1}>
            {services.map((s) => (
              <HStack key={s.serviceId || s.name} justify="space-between">
                <Text fontSize="sm" color="gray.700" isTruncated>
                  {s.name}
                </Text>
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
                </HStack>
              </HStack>
            ))}
          </VStack>
        );
      })()}
    </Box>
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
    removingTaskType,
    handleRemoveQuota,
    scheduleTarget,
    scheduleLimit,
    setScheduleLimit,
    isScheduleOpen,
    isScheduling,
    handleScheduleClose,
    handleScheduleConfirm,
    handleOpenSchedule,
    viewTier,
    isViewOpen,
    onViewClose,
    handleViewClick,
    cancelingTaskType,
    handleCancelPendingQuota,
    assignedTenantsForViewTier,
    isAssignedTenantsLoading,
    servicesForViewTier,
    isServicesForViewTierLoading,
    formData,
    setFormData,
    isSubmitting,
    showQuotaErrors,
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

      {/* Create Tier drawer */}
      <Drawer
        isOpen={isCreateOpen}
        onClose={onCreateClose}
        placement="right"
        size="lg"
        closeOnOverlayClick={!isSubmitting}
      >
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            Create Tier
          </DrawerHeader>
          <DrawerBody py={6}>
            <TierForm
              formData={formData}
              onChange={setFormData}
              taskTypeNames={taskTypeNames}
              unitByTaskType={unitByTaskType}
              showErrors={showQuotaErrors}
            />
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            {tierFormFooter}
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* Edit Tier drawer */}
      <Drawer
        isOpen={isEditOpen}
        onClose={onEditClose}
        placement="right"
        size="lg"
        closeOnOverlayClick={!isSubmitting}
      >
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            {`Edit Tier: ${editingTier?.name ?? ""}`}
          </DrawerHeader>
          <DrawerBody py={6}>
            <TierForm
              formData={formData}
              onChange={setFormData}
              taskTypeNames={taskTypeNames}
              unitByTaskType={unitByTaskType}
              onSchedule={handleOpenSchedule}
              onRemove={(quota) => handleRemoveQuota(quota.modelTaskType)}
              removingTaskType={removingTaskType}
              isEditMode
              showErrors={showQuotaErrors}
            />
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            {tierFormFooter}
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* Schedule quota change modal */}
      <StandardModal
        isOpen={isScheduleOpen}
        onClose={handleScheduleClose}
        title="Schedule quota change"
        size="sm"
        closeOnOverlayClick={!isScheduling}
        footer={
          <HStack justify="flex-end" spacing={3}>
            <Button variant="outline" onClick={handleScheduleClose}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              isLoading={isScheduling}
              loadingText="Scheduling..."
              onClick={handleScheduleConfirm}
            >
              Confirm Schedule
            </Button>
          </HStack>
        }
      >
        {scheduleTarget && (
          <VStack align="stretch" spacing={4}>
            <HStack justify="space-between">
              <Text fontSize="sm" fontWeight="semibold" color="gray.700">
                {formatModelTaskTypeLabel(scheduleTarget.modelTaskType)}
              </Text>
              <Text fontSize="sm" color="gray.600">
                Current:{" "}
                <Text as="span" fontWeight="semibold" color="gray.800">
                  {scheduleTarget.limit} {scheduleTarget.unit}
                </Text>
              </Text>
            </HStack>

            <FormControl isRequired>
              <FormLabel fontSize="sm">
                New Quota Limit ({scheduleTarget.unit})
              </FormLabel>
              <NumberInput
                size="sm"
                min={0}
                value={scheduleLimit}
                onChange={setScheduleLimit}
              >
                <NumberInputField placeholder="e.g. 10" />
              </NumberInput>
            </FormControl>

            <Text fontSize="xs" color="gray.500">
              Takes effect from the next billing cycle.
            </Text>
          </VStack>
        )}
      </StandardModal>

      {/* View Tier drawer */}
      <Drawer
        isOpen={isViewOpen}
        onClose={onViewClose}
        placement="right"
        size="md"
      >
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            {`Tier Details — ${viewTier?.name ?? ""}`}
          </DrawerHeader>
          <DrawerBody py={6}>
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

                <Tabs colorScheme="blue" size="sm">
                  <TabList>
                    <Tab>Current</Tab>
                    <Tab>Upcoming</Tab>
                  </TabList>
                  <TabPanels>
                    <TabPanel px={0}>
                      <VStack align="stretch" spacing={4}>
                        <HStack justify="space-between" align="flex-start">
                          <Text fontSize="sm" color="gray.600">
                            Tier Name
                          </Text>
                          <Text
                            fontSize="sm"
                            fontWeight="semibold"
                            color="gray.800"
                          >
                            {viewTier.name}
                          </Text>
                        </HStack>

                        <HStack justify="space-between" align="flex-start">
                          <Text fontSize="sm" color="gray.600">
                            Description
                          </Text>
                          <Text
                            fontSize="sm"
                            color="gray.700"
                            textAlign="right"
                          >
                            {viewTier.description || "—"}
                          </Text>
                        </HStack>

                        <Divider />

                        <Box>
                          <Text
                            fontSize="xs"
                            fontWeight="semibold"
                            color="gray.500"
                            textTransform="uppercase"
                            mb={2}
                          >
                            Quota by Model Task Type
                          </Text>
                          <VStack align="stretch" spacing={2}>
                            {viewTier.quotas?.length ? (
                              viewTier.quotas.map((q) => {
                                const { boldText, suffixText } =
                                  formatQuotaAmount(q.limit, q.unit);
                                return (
                                  <HStack
                                    key={q.modelTaskType}
                                    justify="space-between"
                                  >
                                    <Text fontSize="sm" color="gray.700">
                                      {formatModelTaskTypeLabel(
                                        q.modelTaskType,
                                      )}
                                    </Text>
                                    <Text fontSize="sm">
                                      <Text
                                        as="span"
                                        fontWeight="semibold"
                                        color="gray.800"
                                      >
                                        {boldText}
                                      </Text>{" "}
                                      <Text as="span" color="gray.600">
                                        {suffixText}
                                      </Text>
                                    </Text>
                                  </HStack>
                                );
                              })
                            ) : (
                              <Text fontSize="sm" color="gray.400">
                                —
                              </Text>
                            )}
                          </VStack>
                        </Box>

                        <ServicesMappedSection
                          services={servicesForViewTier}
                          isLoading={isServicesForViewTierLoading}
                        />

                        <AssignedTenantsSection
                          tenants={assignedTenantsForViewTier}
                          isLoading={isAssignedTenantsLoading}
                        />
                      </VStack>
                    </TabPanel>

                    <TabPanel px={0}>
                      <VStack align="stretch" spacing={3}>
                        {(() => {
                          const pendingQuotas =
                            viewTier.quotas?.filter(
                              (q) => q.pendingLimit != null,
                            ) ?? [];
                          if (!pendingQuotas.length) {
                            return (
                              <Text fontSize="sm" color="gray.400">
                                No upcoming changes.
                              </Text>
                            );
                          }
                          return pendingQuotas.map((q) => (
                            <HStack
                              key={q.modelTaskType}
                              justify="space-between"
                            >
                              <Text fontSize="sm" color="gray.700">
                                {formatModelTaskTypeLabel(q.modelTaskType)}{" "}
                                Quota
                              </Text>
                              <HStack spacing={3}>
                                <Text fontSize="sm" color="gray.600">
                                  <Text
                                    as="span"
                                    fontWeight="semibold"
                                    color="gray.800"
                                  >
                                    {q.pendingLimit?.toLocaleString()} {q.unit}
                                  </Text>{" "}
                                  · effective next billing cycle
                                </Text>
                                <Button
                                  variant="link"
                                  size="xs"
                                  colorScheme="red"
                                  isLoading={
                                    cancelingTaskType === q.modelTaskType
                                  }
                                  isDisabled={
                                    cancelingTaskType !== null &&
                                    cancelingTaskType !== q.modelTaskType
                                  }
                                  onClick={() =>
                                    handleCancelPendingQuota(q.modelTaskType)
                                  }
                                >
                                  Cancel
                                </Button>
                              </HStack>
                            </HStack>
                          ));
                        })()}

                        <AssignedTenantsSection
                          tenants={assignedTenantsForViewTier}
                          isLoading={isAssignedTenantsLoading}
                          pt={2}
                        />
                      </VStack>
                    </TabPanel>
                  </TabPanels>
                </Tabs>
              </VStack>
            )}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" onClick={onViewClose}>
              Close
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    </Box>
  );
};

export default TierManagement;
