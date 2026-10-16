import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Flex,
  FormControl,
  Heading,
  Input,
  Select,
  Spinner,
  Stack,
  Text,
  Textarea,
  useDisclosure,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import StandardModal, { CreateModal } from "../common/StandardModal";
import DataTableActions from "../common/DataTableActions";
import ConfirmDialog from "../common/ConfirmDialog";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import FieldLabel from "../common/FieldLabel";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import {
  policyService,
  type MaskFormat,
  type PiiTypeOut,
} from "../../services/policyService";
import {
  EMPTY_PII_TYPES,
  PII_TYPES_QUERY_KEY,
  fetchAllPiiTypes,
  formatDt,
  getPolicyApiErrorMessage,
  parseDelimitedValues,
} from "./policyShared";

const MASK_OPTIONS: MaskFormat[] = ["full", "partial", "redact"];

function PiiTypeDetailModal({
  isOpen,
  onClose,
  piiType,
  onEdit,
}: {
  isOpen: boolean;
  onClose: () => void;
  piiType: PiiTypeOut | null;
  onEdit: (row: PiiTypeOut) => void;
}) {
  const detail = isOpen ? piiType : null;

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="PII type details"
      size="lg"
      footer={
        detail ? (
          <FormActions
            cancelLabel="Close"
            submitLabel="Edit"
            onCancel={onClose}
            onSubmit={() => onEdit(detail)}
            justify="space-between"
            pt={0}
          />
        ) : (
          <FormActions
            cancelLabel="Close"
            onCancel={onClose}
            hideSubmit
            justify="flex-end"
            pt={0}
          />
        )
      }
    >
      {detail ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {detail.pii_type_id}
          </Text>
          <Heading size="md">{detail.pii_type_label}</Heading>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Mask format
            </Text>
            <Badge>{detail.mask_format}</Badge>
          </Box>
          <FormControl>
            <FieldLabel formLabelProps={{ fontSize: "sm" }}>Regex pattern</FieldLabel>
            <Textarea value={detail.regex_pattern} readOnly fontFamily="mono" rows={4} />
          </FormControl>
          <Text fontSize="sm" color="gray.600">
            Created {formatDt(detail.created_at)}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}

export function PiiTypesPanel() {
  const queryClient = useQueryClient();
  const piiQuery = useQuery({
    queryKey: PII_TYPES_QUERY_KEY,
    queryFn: fetchAllPiiTypes,
    staleTime: 60 * 1000,
  });
  const allTypes = piiQuery.data ?? EMPTY_PII_TYPES;
  const loading = piiQuery.isPending;
  const error = piiQuery.isError
    ? getPolicyApiErrorMessage(piiQuery.error, "Failed to load PII types")
    : null;
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMask, setFilterMask] = useState("");
  const piiTypeSortAccessors = useMemo(
    () => ({
      label: (row: PiiTypeOut) => row.pii_type_label ?? "",
      regex: (row: PiiTypeOut) => row.regex_pattern ?? "",
      created: (row: PiiTypeOut) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
    }),
    [],
  );
  const piiTypeSort = useDeferredColumnSort("label", piiTypeSortAccessors);
  const [tableEpoch, setTableEpoch] = useState(0);
  const modal = useDisclosure();
  const viewModal = useDisclosure();
  const [viewPiiId, setViewPiiId] = useState<string | null>(null);
  const confirmDel = useDisclosure();
  const [editing, setEditing] = useState<PiiTypeOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PiiTypeOut | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [label, setLabel] = useState("");
  const [regex, setRegex] = useState("");
  const [examples, setExamples] = useState("");
  const [mask, setMask] = useState<MaskFormat>("redact");
  const [saving, setSaving] = useState(false);
  const [piiDetailLoading, setPiiDetailLoading] = useState(false);

  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const reloadPiiTypes = useCallback(() => {
    return queryClient.invalidateQueries({ queryKey: PII_TYPES_QUERY_KEY });
  }, [queryClient]);

  const getSortTimestamp = (value?: string | null): number => {
    if (value == null) return 0;
    const t = new Date(value).getTime();
    return Number.isNaN(t) ? 0 : t;
  };

  const filteredPiiTypes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = allTypes.filter((row) => {
      if (q) {
        const inLabel = (row.pii_type_label ?? "").toLowerCase().includes(q);
        const inRegex = (row.regex_pattern ?? "").toLowerCase().includes(q);
        if (!inLabel && !inRegex) return false;
      }
      if (filterMask && row.mask_format !== filterMask) return false;
      return true;
    });
    const byCreatedDesc = [...filtered].sort(
      (a, b) => getSortTimestamp(b.created_at) - getSortTimestamp(a.created_at),
    );
    return piiTypeSort.apply(byCreatedDesc);
  }, [allTypes, searchQuery, filterMask, piiTypeSort]);

  const hasActiveFilters = filterMask !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterMask("");
  };

  const openCreate = () => {
    setEditing(null);
    setLabel("");
    setRegex("");
    setExamples("");
    setMask("redact");
    modal.onOpen();
  };

  const openPiiView = (row: PiiTypeOut) => {
    setViewPiiId(row.pii_type_id);
    viewModal.onOpen();
  };

  const closePiiView = () => {
    viewModal.onClose();
    setViewPiiId(null);
  };

  const openEdit = (row: PiiTypeOut) => {
    setEditing(row);
    setExamples("");
    setLabel(row.pii_type_label);
    setRegex(row.regex_pattern);
    setMask(row.mask_format as MaskFormat);
    setPiiDetailLoading(false);
    modal.onOpen();
  };

  const save = async () => {
    if (!label.trim() || !regex.trim()) {
      showToast({ type: "warning", message: "Label and regex are required" });
      return;
    }
    const example_values = parseDelimitedValues(examples);
    if ((!editing || example_values.length > 0) && example_values.length < 3) {
      showToast({
        type: "warning",
        message: "Provide at least three example values when using the example field",
      });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await policyService.updatePiiType(editing.pii_type_id, {
          pii_type_label: label.trim(),
          regex_pattern: regex.trim(),
          example_values: example_values.length > 0 ? example_values : undefined,
          mask_format: mask,
        });
      } else {
        await policyService.createPiiType({
          pii_type_label: label.trim(),
          regex_pattern: regex.trim(),
          example_values,
          mask_format: mask,
        });
      }
      showToast({ type: "success", message: "Saved" });
      modal.onClose();
      void reloadPiiTypes();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Save failed"),
      });
    } finally {
      setSaving(false);
    }
  };

  const requestDelete = (row: PiiTypeOut) => {
    setDeleteTarget(row);
    confirmDel.onOpen();
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await policyService.deletePiiType(deleteTarget.pii_type_id);
      showToast({ type: "success", message: "Deleted" });
      confirmDel.onClose();
      setDeleteTarget(null);
      void reloadPiiTypes();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Delete failed (type may be in use)"),
      });
    } finally {
      setDeleting(false);
    }
  };

  const piiColumns = useMemo((): DataTableColumn<PiiTypeOut>[] => [
    {
      id: "label",
      header: "Label",
      sortable: true,
      sortAccessor: (row) => row.pii_type_label ?? "",
      cell: (row) => <Text fontWeight="medium" fontSize="sm">{row.pii_type_label}</Text>,
    },
    {
      id: "mask",
      header: "Mask",
      cell: (row) => <Badge>{row.mask_format}</Badge>,
    },
    {
      id: "regex",
      header: "Regex",
      tdProps: { maxW: "280px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
      sortable: true,
      sortAccessor: (row) => row.regex_pattern ?? "",
      cell: (row) => (
        <Box as="span" title={row.regex_pattern} display="block" isTruncated maxW="280px">
          {row.regex_pattern}
        </Box>
      ),
    },
    {
      id: "created",
      header: "Created",
      tdProps: { whiteSpace: "nowrap" },
      sortable: true,
      sortAccessor: (row) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <DataTableActions
          actions={[
            {
              id: "edit",
              label: "Edit PII type",
              onClick: () => openEdit(row),
            },
            {
              id: "delete",
              label: "Delete PII type",
              onClick: () => requestDelete(row),
            },
          ]}
        />
      ),
    },
  ], [openEdit, requestDelete]);

  const piiTypeForm = editing && piiDetailLoading ? (
          <Flex justify="center" py={8}>
            <Spinner />
          </Flex>
        ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FieldLabel>Label</FieldLabel>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </FormControl>
          <FormControl isRequired>
            <FieldLabel>Regex pattern</FieldLabel>
            <Textarea value={regex} onChange={(e) => setRegex(e.target.value)} fontFamily="mono" rows={3} />
          </FormControl>
          <FormControl isRequired={!editing}>
            <FieldLabel>
              {editing
                ? "Example values (comma or newline, optional validation)"
                : "Example values (comma or newline, min 3)"}
            </FieldLabel>
            <Textarea
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              placeholder="a@b.com, test@example.org, user@mail.co"
              rows={3}
            />
          </FormControl>
          <FormControl>
            <FieldLabel>Mask format</FieldLabel>
            <Select value={mask} onChange={(e) => setMask(e.target.value as MaskFormat)}>
              {MASK_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </FormControl>
        </Stack>
        );

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <DataTable<PiiTypeOut>
            layout="admin"
            key={tableEpoch}
            items={filteredPiiTypes}
            columns={piiColumns}
          sort={piiTypeSort.sort}
          onSortChange={(next) => { piiTypeSort.onSortChange(next); bumpTablePage(); }}
            getRowKey={(row) => row.pii_type_id}
            search={{
              label: "Search",
              value: searchQuery,
              onChange: setSearchQuery,
              placeholder: "Search by label or regex…",
              fields: ["label", "regex"],
            }}
            filterDefs={[
              {
                id: "mask",
                label: "Mask format",
                type: "select",
                param: "mask_format",
                value: filterMask,
                onChange: setFilterMask,
                options: [
                  { label: "All", value: "" },
                  ...MASK_OPTIONS.map((m) => ({ label: m, value: m })),
                ],
              },
            ]}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filterToolbarRightContent={
              <CreateButton onClick={openCreate}>Create PII Type</CreateButton>
            }
            isLoading={loading}
            loadingMessage="Loading PII types…"
            emptyMessage='No PII types in the library yet. Click "Create PII type" to add one.'
            noResultsMessage="No PII types match the current filters."
            unfilteredCount={allTypes.length}
            onRowClick={openPiiView}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            tableContainerProps={{ overflowX: "auto" }}
          />

      <PiiTypeDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePiiView}
        piiType={allTypes.find((row) => row.pii_type_id === viewPiiId) ?? null}
        onEdit={(row) => {
          closePiiView();
          openEdit(row);
        }}
      />

      <CreateModal
        isOpen={modal.isOpen && !editing}
        onClose={modal.onClose}
        title="Create PII Type"
        description="Add a PII type to the library for use in policies."
        size="md"
        footer={
          <FormActions
            submitLabel="Create PII Type"
            onCancel={modal.onClose}
            onSubmit={() => void save()}
            isLoading={saving}
            loadingText="Creating..."
            justify="space-between"
            pt={0}
          />
        }
      >
        {piiTypeForm}
      </CreateModal>

      <StandardModal
        isOpen={modal.isOpen && Boolean(editing)}
        onClose={modal.onClose}
        title="Edit PII Type"
        description="Update how this PII type is detected and labelled."
        size="lg"
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={modal.onClose}
            onSubmit={() => void save()}
            isLoading={saving}
            isDisabled={piiDetailLoading}
            loadingText="Saving..."
          />
        }
      >
        {piiTypeForm}
      </StandardModal>

      <ConfirmDialog
        isOpen={confirmDel.isOpen}
        onClose={confirmDel.onClose}
        title="Delete PII type"
        body={
          deleteTarget ? (
            <Text>
              Remove <strong>{deleteTarget.pii_type_label}</strong>? Policies referencing it may fail to
              update.
            </Text>
          ) : null
        }
        onConfirm={() => void confirmDelete()}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={deleting}
      />
    </Box>
  );
}
