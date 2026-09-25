import React, { useEffect, useMemo } from "react";
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
  HStack,
  IconButton,
  Input,
  Select,
  Skeleton,
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
  Grid,
} from "@chakra-ui/react";
import {
  AddIcon,
  DeleteIcon,
  EditIcon,
  SmallCloseIcon,
} from "@chakra-ui/icons";
import { FiArrowUp, FiCalendar, FiPause, FiPlay } from "react-icons/fi";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  createActionsColumn,
  type DataTableColumn,
} from "../common/table";
import ConfirmDialog from "../common/ConfirmDialog";
import CreateHeader from "../common/CreateHeader";
import FormActions from "../common/FormActions";
import FormSection from "../common/FormSection";
import FormFieldsRow, { FORM_LABEL_TO_INPUT_PT } from "../common/FormFieldsRow";
import StandardModal, { CreateModal } from "../common/StandardModal";
import {
  effectiveTierStatus,
  getTierStatusAction,
  useTierManagement,
  type TierStatusActionKey,
} from "../../hooks/useTierManagement";
import type { Tier, TierStatus } from "../../services/tierManagementService";
import type { TierFormData, TierFormQuota } from "../../types/tierManagement";
import { INSTITUTIONS, formatModelTaskTypeLabel } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { generateUUID } from "../../utils/uuid";
import { QUOTA_LIMIT_MAX, validateQuotaLimit } from "./tierFormValidation";
import { useDeferredColumnSort } from "../../utils/tableSort";

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

const TIER_NAME_COLUMN: DataTableColumn<Tier> = {
  id: "name",
  header: "Tier Name",
  thProps: { w: "500px", maxW: "500px" },
  tdProps: { maxW: "500px" },
  sortable: true,
  sortAccessor: (tier) => tier.name ?? "",
  cell: (tier) => (
    <Tooltip label={tier.name} placement="top" hasArrow openDelay={300}>
      <Text fontSize="sm" fontWeight="medium" isTruncated maxW="510px">
        {tier.name}
      </Text>
    </Tooltip>
  ),
};

const TIER_STATUS_BADGE: Record<
  TierStatus,
  { label: string; colorScheme: string }
> = {
  INACTIVE: { label: "Inactive", colorScheme: "gray" },
  ACTIVE: { label: "Active", colorScheme: "green" },
  DEACTIVATED: { label: "Deactivated", colorScheme: "orange" },
  DELETED: { label: "Deleted", colorScheme: "red" },
};

/**
 * DELETED is absent because `list_tiers` excludes deleted tiers from every
 * response, so the option would always return nothing. It stays in
 * TIER_STATUS_BADGE only because that map is keyed by the full union.
 */
const TIER_FILTER_STATUSES: TierStatus[] = [
  "ACTIVE",
  "INACTIVE",
  "DEACTIVATED",
];

const TIER_STATUS_COLUMN: DataTableColumn<Tier> = {
  id: "status",
  header: "Status",
  thProps: { w: "240px" },
  cell: (tier) => {
    const badge = TIER_STATUS_BADGE[effectiveTierStatus(tier)];
    return (
      <Badge
        colorScheme={badge.colorScheme}
        fontSize="xs"
        px={2}
        py={0.5}
        borderRadius="md"
      >
        {badge.label}
      </Badge>
    );
  },
};

/**
 * Icon for the single lifecycle action a tier offers in its current status.
 * Keyed by status, not by label: INACTIVE and DEACTIVATED both offer an
 * "Activate" action (each transitions to ACTIVE), so labels are not unique.
 */
const TIER_STATUS_ACTION_ICON: Record<TierStatusActionKey, React.ReactElement> =
  {
    INACTIVE: <FiArrowUp />,
    ACTIVE: <FiPause />,
    DEACTIVATED: <FiPlay />,
  };

const TIER_TASK_TYPES_VISIBLE_COUNT = 4;

const TIER_TASK_TYPES_COLUMN: DataTableColumn<Tier> = {
  id: "taskTypes",
  header: "Model Task Types",
  cell: (tier) => (
    <HStack spacing={1} flexWrap="wrap">
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
        <Text fontSize="sm" color="ink.400">
          —
        </Text>
      )}
    </HStack>
  ),
};

/**
 * A per-tier count column. Counts are aggregated in the hook from one fetch,
 * and render blank rather than `0` until it settles — "0" and "not loaded yet"
 * read very differently.
 */
function makeTierCountColumn(
  id: string,
  header: string,
  countByTierId: Map<string, number>,
  isLoading: boolean,
  hasError: boolean,
  errorLabel: string,
): DataTableColumn<Tier> {
  return {
    id,
    header,
    thProps: { w: "140px" },
    sortable: true,
    align: "center",
    cell: (tier) => {
      if (isLoading) {
        // `mx="auto"`: a fixed-width block is not moved by textAlign.
        return (
          <Skeleton height="20px" width="28px" borderRadius="md" mx="auto" />
        );
      }
      if (hasError) {
        return (
          <Tooltip label={errorLabel} placement="top" hasArrow>
            <Text fontSize="sm" color="gray.400">
              —
            </Text>
          </Tooltip>
        );
      }
      // Non-zero gets a neutral chip so tiers in use stand out; zero stays a
      // bare number, or an empty tier would carry the same weight as a used
      // one. `minW` keeps 1- and 2-digit chips even in the centred column.
      const count = countByTierId.get(tier.id) ?? 0;
      if (count === 0) {
        return (
          <Text fontSize="sm" color="gray.500">
            0
          </Text>
        );
      }
      return (
        <Badge
          colorScheme="gray"
          fontSize="xs"
          fontWeight="bold"
          px={2}
          py={0.5}
          borderRadius="md"
          minW="28px"
          textAlign="center"
        >
          {count}
        </Badge>
      );
    },
  };
}

function makeTierActionsColumn(
  deletingId: string | null,
  updatingStatusId: string | null,
  onEdit: (tier: Tier) => void,
  onDelete: (tier: Tier) => void,
  onStatusChange: (tier: Tier) => void,
): DataTableColumn<Tier> {
  return createActionsColumn<Tier>({
    getActions: (tier) => {
      const statusAction = getTierStatusAction(tier.status);
      const canDelete = tier.status === "DEACTIVATED";
      const busy = deletingId !== null || updatingStatusId !== null;
      return [
        {
          id: "edit",
          label: "Edit",
          icon: <EditIcon />,
          onClick: () => onEdit(tier),
          "aria-label": "Edit tier",
        },
        {
          id: "status",
          label: statusAction?.label ?? "Update status",
          icon: TIER_STATUS_ACTION_ICON[
            tier.status as TierStatusActionKey
          ] ?? <FiArrowUp />,
          onClick: () => onStatusChange(tier),
          visible: statusAction !== null,
          disabled: busy,
          isLoading: updatingStatusId === tier.id,
          color: `${statusAction?.colorScheme ?? "blue"}.500`,
          hoverColor: `${statusAction?.colorScheme ?? "blue"}.600`,
          hoverBg: `${statusAction?.colorScheme ?? "blue"}.50`,
          "aria-label": `${statusAction?.label ?? "Update status"} tier`,
        },
        {
          id: "delete",
          label: "Delete",
          tooltip: canDelete
            ? "Delete"
            : "Deactivate this tier before deleting it",
          icon: <DeleteIcon />,
          onClick: () => onDelete(tier),
          disabled: !canDelete || busy,
          isLoading: deletingId === tier.id,
          "aria-label": "Delete tier",
        },
      ];
    },
  });
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
  readonly mode?: "create" | "edit" | "view";
  readonly showErrors?: boolean;
}

function isUnitInvalid(quota: TierFormQuota): boolean {
  return !quota.unit.trim();
}

/**
 * Inline verdict for a quota row's limit. Delegates to the shared rule so the
 * form and `validateQuotas` (which gates submit) cannot drift apart.
 */
function limitError(quota: TierFormQuota): string | null {
  return validateQuotaLimit(quota.limit);
}

function showLimitError(quota: TierFormQuota, showErrors?: boolean): boolean {
  return (showErrors || !!quota.limit.trim()) && !!limitError(quota);
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
        <Text fontSize="sm" fontWeight="semibold" color="ink.700">
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
              borderColor="ink.200"
              bg="ink.50"
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
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Model Task Type
                    </FieldLabel>
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
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Unit
                    </FieldLabel>
                    <Input
                      size="sm"
                      value={quota.unit}
                      isReadOnly
                      placeholder="-"
                      bg="ink.50"
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
                    isInvalid={showLimitError(quota, showErrors)}
                    isDisabled={isEditMode}
                    minW={0}
                  >
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Limit
                    </FieldLabel>
                    <NumberInput
                      size="sm"
                      min={0}
                      max={QUOTA_LIMIT_MAX}
                      step={1}
                      // An out-of-range value must survive blur so the inline
                      // error can name it; clamping would silently rewrite it.
                      clampValueOnBlur={false}
                      value={quota.limit}
                      onChange={(v) => handleQuotaChange(idx, "limit", v)}
                    >
                      <NumberInputField
                        placeholder={FIELD_HINTS.tier.quotaLimit.placeholder}
                      />
                    </NumberInput>
                    <FormErrorMessage fontSize="xs">
                      {limitError(quota)}
                    </FormErrorMessage>
                    <FieldHint show={!showLimitError(quota, showErrors)}>
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
  readonly mode?: "create" | "edit" | "view";
  readonly showErrors?: boolean;
}

export function TierForm({
  formData,
  onChange,
  taskTypeNames,
  unitByTaskType,
  onSchedule,
  onRemove,
  removingTaskType,
  isEditMode,
  mode,
  showErrors,
}: TierFormProps) {
  const formMode = mode ?? (isEditMode ? "edit" : "create");
  if (formMode === "view") {
    return (
      <VStack align="stretch" spacing={4}>
        <Box>
          <FieldLabel variant="inline">Tier Name</FieldLabel>
          <Text fontSize="md" color="ink.800">{formData.name || "—"}</Text>
        </Box>
        <Box>
          <FieldLabel variant="inline">Description</FieldLabel>
          <Text fontSize="md" color="ink.700">{formData.description || "—"}</Text>
        </Box>
        <Box>
          <Text fontSize="xs" fontWeight="semibold" color="ink.500" textTransform="uppercase" mb={2}>
            Quota by Model Task Type
          </Text>
          <VStack align="stretch" spacing={2}>
            {formData.quotas.length ? (
              formData.quotas.map((q) => {
                const limit = Number(q.limit);
                const { boldText, suffixText } = formatQuotaAmount(
                  Number.isFinite(limit) ? limit : 0,
                  q.unit,
                );
                return (
                  <HStack key={q.modelTaskType} justify="space-between">
                    <Text fontSize="sm" color="ink.700">
                      {formatModelTaskTypeLabel(q.modelTaskType)}
                    </Text>
                    <Text fontSize="sm">
                      <Text as="span" fontWeight="semibold" color="ink.800">{boldText}</Text>{" "}
                      <Text as="span" color="ink.600">{suffixText}</Text>
                    </Text>
                  </HStack>
                );
              })
            ) : (
              <Text fontSize="sm" color="ink.400">—</Text>
            )}
          </VStack>
        </Box>
      </VStack>
    );
  }

  return (
    <VStack align="stretch" spacing={0}>
      <FormSection title="Basic information">
      <FormControl isRequired>
        <FieldLabel>Tier Name</FieldLabel>
        <Input
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
          placeholder={FIELD_HINTS.tier.name.placeholder}
          maxLength={100}
        />
        <FieldHint>{FIELD_HINTS.tier.name.helper}</FieldHint>
      </FormControl>

      <FormControl>
        <FieldLabel>Description</FieldLabel>
        <Input
          value={formData.description}
          onChange={(e) =>
            onChange({ ...formData, description: e.target.value })
          }
          placeholder={FIELD_HINTS.tier.description.placeholder}
        />
        <FieldHint>{FIELD_HINTS.tier.description.helper}</FieldHint>
      </FormControl>
      </FormSection>

      <FormSection title="Usage limits">
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
      </FormSection>
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
        color="ink.500"
        textTransform="uppercase"
        mb={1}
      >
        {INSTITUTIONS} Assigned · {isLoading ? "…" : tenants.length}
      </Text>
      {(() => {
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
            <Text fontSize="sm" color="ink.400">
              No {INSTITUTIONS.toLowerCase()} assigned
            </Text>
          );
        }
        return (
          <VStack align="stretch" spacing={1}>
            {tenants.map((t) => (
              <HStack key={t.tenantId} justify="space-between">
                <Text fontSize="sm" color="ink.700" isTruncated>
                  {t.organisation}
                </Text>
                <Text fontSize="xs" color="ink.500" flexShrink={0}>
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
        color="ink.500"
        textTransform="uppercase"
        mb={1}
      >
        Services Mapped · {isLoading ? "…" : services.length}
      </Text>
      {(() => {
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
            <Text fontSize="sm" color="ink.400">
              No services mapped
            </Text>
          );
        }
        return (
          <VStack align="stretch" spacing={1}>
            {services.map((s) => (
              <HStack key={s.serviceId || s.name} justify="space-between">
                <Text fontSize="sm" color="ink.700" isTruncated>
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

const TierManagement: React.FC<{
  onRegisterCreate?: (open: () => void) => void;
}> = ({ onRegisterCreate }) => {
  const { taskTypeNames, unitByTaskType } = useInferenceTypes();

  const {
    searchQuery,
    setSearchQuery,
    filterTaskType,
    setFilterTaskType,
    filterStatus,
    setFilterStatus,
    hasActiveFilters,
    clearFilters,
    serviceCountByTierId,
    isServiceCountLoading,
    hasServiceCountError,
    institutionCountByTierId,
    isInstitutionCountLoading,
    hasInstitutionCountError,
    filteredTiers,
    tiers,
    isLoading,
    tierToDelete,
    deletingId,
    isDeleteOpen,
    onDeleteClose,
    handleDeleteClick,
    handleDeleteConfirm,
    statusTier,
    statusAction,
    updatingStatusId,
    isStatusOpen,
    handleStatusClick,
    handleStatusClose,
    handleStatusConfirm,
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
    scheduleLimitError,
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

  useEffect(() => {
    onRegisterCreate?.(handleOpenCreate);
  }, [onRegisterCreate, handleOpenCreate]);

  /**
   * An untouched New Quota Limit is empty rather than wrong, so the hint stays
   * until the admin has actually typed something the backend would reject.
   */
  const showScheduleLimitError = !!scheduleLimit.trim() && !!scheduleLimitError;

  const tierSortAccessors = useMemo(
    () => ({
      name: (tier: Tier) => tier.name ?? "",
      // This table owns its sort, so a column's own `sortAccessor` is ignored.
      services: (tier: Tier) => serviceCountByTierId.get(tier.id) ?? 0,
      institutions: (tier: Tier) => institutionCountByTierId.get(tier.id) ?? 0,
    }),
    [serviceCountByTierId, institutionCountByTierId],
  );
  const tierSort = useDeferredColumnSort("name", tierSortAccessors);
  const sortedTiers = useMemo(
    () => tierSort.apply(filteredTiers),
    [filteredTiers, tierSort],
  );

  const columns = useMemo(
    () => [
      TIER_NAME_COLUMN,
      TIER_STATUS_COLUMN,
      TIER_TASK_TYPES_COLUMN,
      makeTierCountColumn(
        "services",
        "Services",
        serviceCountByTierId,
        isServiceCountLoading,
        hasServiceCountError,
        "Could not load services",
      ),
      makeTierCountColumn(
        "institutions",
        INSTITUTIONS,
        institutionCountByTierId,
        isInstitutionCountLoading,
        hasInstitutionCountError,
        `Could not load ${INSTITUTIONS.toLowerCase()}`,
      ),
      makeTierActionsColumn(
        deletingId,
        updatingStatusId,
        handleOpenEdit,
        handleDeleteClick,
        handleStatusClick,
      ),
    ],
    [
      deletingId,
      updatingStatusId,
      handleDeleteClick,
      handleOpenEdit,
      handleStatusClick,
      serviceCountByTierId,
      isServiceCountLoading,
      hasServiceCountError,
      institutionCountByTierId,
      isInstitutionCountLoading,
      hasInstitutionCountError,
    ],
  );

  const tierFormFooter = (
    <FormActions
      submitLabel="Save Changes"
      onCancel={onEditClose}
      isLoading={isSubmitting}
      loadingText="Saving..."
      onSubmit={handleEditSubmit}
    />
  );

  return (
    <Box>
      <DataTable
        layout="admin"
        items={sortedTiers}
        columns={columns}
        getRowKey={(tier) => tier.id}
        sort={tierSort.sort}
        onSortChange={tierSort.onSortChange}
        onRowClick={handleViewClick}
        isLoading={isLoading}
        loadingMessage="Loading tiers..."
        emptyMessage="No tiers found. Create your first tier to get started."
        noResultsMessage="No tiers match the current filters."
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        unfilteredCount={tiers.length}
        paginate="client"
        paginationPosition="bottom"
        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        filterToolbarAlign="flex-start"
        search={{
          value: searchQuery,
          onChange: setSearchQuery,
          placeholder: "Search tiers...",
          fields: ["name"],
        }}
        filterDefs={[
          {
            id: "taskType",
            label: "Model Task Type",
            type: "select",
            param: "model_task_type",
            value: filterTaskType,
            onChange: setFilterTaskType,
            width: { base: "full", sm: "200px" },
            options: [
              ...(taskTypeNames.length > 1 ? [{ label: "All", value: "" }] : []),
              ...taskTypeNames.map((t) => ({
                label: formatModelTaskTypeLabel(t),
                value: t,
              })),
            ],
          },
          {
            id: "status",
            label: "Status",
            // No `param`: client-side, since fetching by status would make
            // `unfilteredCount` the filtered count.
            type: "select",
            value: filterStatus,
            onChange: setFilterStatus,
            width: { base: "full", sm: "180px" },
            options: [
              { label: "All", value: "" },
              // Labels from the badge map, so dropdown and column agree.
              ...TIER_FILTER_STATUSES.map((s) => ({
                label: TIER_STATUS_BADGE[s].label,
                value: s,
              })),
            ],
          },
        ]}
      />

      {/* Lifecycle status confirmation (activate / deactivate) */}
      <ConfirmDialog
        isOpen={isStatusOpen}
        onClose={handleStatusClose}
        onConfirm={handleStatusConfirm}
        title={statusAction?.title ?? "Update Tier Status"}
        body={statusAction?.body ?? ""}
        confirmLabel={statusAction?.confirmLabel ?? "Confirm"}
        cancelLabel="Cancel"
        confirmColorScheme={statusAction?.colorScheme ?? "blue"}
        isConfirmLoading={updatingStatusId === statusTier?.id}
        confirmLoadingText={statusAction?.loadingText}
        leastDestructiveRef={cancelRef}
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
            <strong>{tierToDelete?.name}</strong>? This action cannot be undone.
            Deletion is refused while the tier is still assigned to a tenant or
            mapped to a service.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={deletingId === tierToDelete?.id}
        confirmLoadingText="Deleting..."
        leastDestructiveRef={cancelRef}
      />

      {/* Create Tier */}
      <CreateModal
        isOpen={isCreateOpen}
        onClose={onCreateClose}
        size="lg"
        title="Create Tier"
        description={`Configure access and usage limits for ${INSTITUTIONS.toLowerCase()}.`}
        footer={
          <FormActions
            submitLabel="Create Tier"
            onCancel={onCreateClose}
            isLoading={isSubmitting}
            loadingText="Creating..."
            justify="space-between"
            pt={0}
            onSubmit={() => {
              void handleCreateSubmit();
            }}
          />
        }
      >
        <TierForm
          formData={formData}
          onChange={setFormData}
          taskTypeNames={taskTypeNames}
          unitByTaskType={unitByTaskType}
          showErrors={showQuotaErrors}
        />
      </CreateModal>

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
          <DrawerHeader borderBottomWidth="1px" borderColor="ink.200">
            <CreateHeader
              title={editingTier?.name ? `Edit ${editingTier.name}` : "Edit Tier"}
              description="Update this tier's access and usage limits."
            />
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
          <DrawerFooter borderTopWidth="1px" borderColor="ink.200">
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
          <FormActions
            submitLabel="Confirm Schedule"
            onCancel={handleScheduleClose}
            onSubmit={() => void handleScheduleConfirm()}
            isLoading={isScheduling}
            loadingText="Scheduling..."
            isDisabled={!!scheduleLimitError}
            justify="flex-end"
            pt={0}
          />
        }
      >
        {scheduleTarget && (
          <VStack align="stretch" spacing={4}>
            <HStack justify="space-between">
              <Text fontSize="sm" fontWeight="semibold" color="ink.700">
                {formatModelTaskTypeLabel(scheduleTarget.modelTaskType)}
              </Text>
              <Text fontSize="sm" color="ink.600">
                Current:{" "}
                <Text as="span" fontWeight="semibold" color="ink.800">
                  {scheduleTarget.limit} {scheduleTarget.unit}
                </Text>
              </Text>
            </HStack>

            <FormControl isRequired isInvalid={showScheduleLimitError}>
              <FieldLabel formLabelProps={{ fontSize: "sm" }}>
                New Quota Limit ({scheduleTarget.unit})
              </FieldLabel>
              <NumberInput
                size="sm"
                min={0}
                max={QUOTA_LIMIT_MAX}
                step={1}
                clampValueOnBlur={false}
                value={scheduleLimit}
                onChange={setScheduleLimit}
              >
                <NumberInputField placeholder="e.g. 10" />
              </NumberInput>
              {showScheduleLimitError ? (
                <FormErrorMessage fontSize="xs">
                  {scheduleLimitError}
                </FormErrorMessage>
              ) : (
                <FieldHint>{FIELD_HINTS.tier.quotaLimit.helper}</FieldHint>
              )}
            </FormControl>

            <Text fontSize="xs" color="ink.500">
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
          <DrawerHeader borderBottomWidth="1px" borderColor="ink.200">
            {`Tier Details — ${viewTier?.name ?? ""}`}
          </DrawerHeader>
          <DrawerBody py={6}>
            {viewTier && (
              <VStack align="stretch" spacing={5}>
                <Tabs colorScheme="blue" size="sm">
                  <TabList>
                    <Tab>Current</Tab>
                    <Tab>Upcoming</Tab>
                  </TabList>
                  <TabPanels>
                    <TabPanel px={0}>
                      <VStack align="stretch" spacing={4}>
                        <TierForm
                          mode="view"
                          formData={{
                            name: viewTier.name,
                            description: viewTier.description ?? "",
                            quotas: (viewTier.quotas ?? []).map((q) => ({
                              modelTaskType: q.modelTaskType,
                              unit: q.unit ?? "",
                              limit: String(q.limit ?? ""),
                            })),
                          }}
                          onChange={() => undefined}
                          taskTypeNames={taskTypeNames}
                          unitByTaskType={unitByTaskType}
                        />

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
                              <Text fontSize="sm" color="ink.400">
                                No upcoming changes.
                              </Text>
                            );
                          }
                          return pendingQuotas.map((q) => (
                            <HStack
                              key={q.modelTaskType}
                              justify="space-between"
                            >
                              <Text fontSize="sm" color="ink.700">
                                {formatModelTaskTypeLabel(q.modelTaskType)}{" "}
                                Quota
                              </Text>
                              <HStack spacing={3}>
                                <Text fontSize="sm" color="ink.600">
                                  <Text
                                    as="span"
                                    fontWeight="semibold"
                                    color="ink.800"
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
          <DrawerFooter borderTopWidth="1px" borderColor="ink.200">
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
