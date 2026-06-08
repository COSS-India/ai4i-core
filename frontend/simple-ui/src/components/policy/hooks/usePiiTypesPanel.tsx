import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Box,
  HStack,
  IconButton,
  Text,
  Tooltip,
  useDisclosure,
  useToast,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { type AdminTableColumn } from "../../common/AdminDataTable";
import { useAdminTableSurface } from "../../common/TableControls";
import { policyService, type MaskFormat, type PiiTypeOut } from "../../../services/policyService";
import { formatDt, getPolicyApiErrorMessage, parseDelimitedValues } from "../utils";

export function usePiiTypesPanel(toast: ReturnType<typeof useToast>) {
  const [allTypes, setAllTypes] = useState<PiiTypeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMask, setFilterMask] = useState("");
  const [sortBy, setSortBy] = useState<"time" | "label">("time");
  const [labelSortDirection, setLabelSortDirection] = useState<"asc" | "desc">("asc");
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

  const { cardBg, borderColor } = useAdminTableSurface();
  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const reloadPiiTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const acc: PiiTypeOut[] = [];
      let page = 1;
      const limit = 100;
      for (;;) {
        const res = await policyService.listPiiTypes({ page, limit });
        acc.push(...res.data.data);
        if (acc.length >= res.data.meta.total || res.data.data.length === 0) break;
        page += 1;
      }
      setAllTypes(acc);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load PII types"));
      setAllTypes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadPiiTypes();
  }, [reloadPiiTypes]);

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
    return [...filtered].sort((a, b) => {
      const createdA = getSortTimestamp(a.created_at);
      const createdB = getSortTimestamp(b.created_at);
      const labelCmp = (a.pii_type_label ?? "").localeCompare(b.pii_type_label ?? "", undefined, {
        sensitivity: "base",
      });
      if (sortBy === "time") {
        if (createdB !== createdA) return createdB - createdA;
        return 0;
      }
      if (labelCmp !== 0) return labelSortDirection === "asc" ? labelCmp : -labelCmp;
      if (createdB !== createdA) return createdB - createdA;
      return 0;
    });
  }, [allTypes, searchQuery, filterMask, sortBy, labelSortDirection]);

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
    modal.onOpen();
    setPiiDetailLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPiiType(row.pii_type_id);
        const p = res.data;
        setLabel(p.pii_type_label);
        setRegex(p.regex_pattern);
        setMask(p.mask_format as MaskFormat);
      } catch (e: unknown) {
        toast({
          title: getPolicyApiErrorMessage(e, "Could not load PII type (GET by id)"),
          status: "error",
          duration: 4000,
        });
        setLabel(row.pii_type_label);
        setRegex(row.regex_pattern);
        setMask(row.mask_format as MaskFormat);
      } finally {
        setPiiDetailLoading(false);
      }
    };
    void run();
  };

  const save = async () => {
    if (!label.trim() || !regex.trim()) {
      toast({ title: "Label and regex are required", status: "warning" });
      return;
    }
    const example_values = parseDelimitedValues(examples);
    if ((!editing || example_values.length > 0) && example_values.length < 3) {
      toast({
        title: "Provide at least three example values when using the example field",
        status: "warning",
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
      toast({ title: "Saved", status: "success", duration: 2000 });
      modal.onClose();
      void reloadPiiTypes();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Save failed"),
        status: "error",
        duration: 5000,
        isClosable: true,
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
      toast({ title: "Deleted", status: "success", duration: 2000 });
      confirmDel.onClose();
      setDeleteTarget(null);
      void reloadPiiTypes();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Delete failed (type may be in use)"),
        status: "error",
        duration: 5000,
      });
    } finally {
      setDeleting(false);
    }
  };

  const piiColumns = useMemo((): AdminTableColumn<PiiTypeOut>[] => [
    {
      id: "label",
      header: "Label",
      sortable: {
        label: "Label",
        direction: labelSortDirection,
        onAsc: () => {
          setSortBy("label");
          setLabelSortDirection("asc");
          bumpTablePage();
        },
        onDesc: () => {
          setSortBy("label");
          setLabelSortDirection("desc");
          bumpTablePage();
        },
        ascAriaLabel: "Sort PII types by label ascending",
        descAriaLabel: "Sort PII types by label descending",
      },
      cell: (row) => <Text fontWeight="medium">{row.pii_type_label}</Text>,
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
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "actions",
      header: "Actions",
      thProps: { textAlign: "right" },
      tdProps: { textAlign: "right", onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <HStack justify="flex-end" spacing={1}>
          <Tooltip label="Edit PII type" hasArrow placement="top">
            <IconButton
              aria-label="Edit PII type"
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              colorScheme="blue"
              _hover={{ bg: "blue.50" }}
              onClick={() => openEdit(row)}
            />
          </Tooltip>
          <Tooltip label="Delete PII type" hasArrow placement="top">
            <IconButton
              aria-label="Delete PII type"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={() => requestDelete(row)}
            />
          </Tooltip>
        </HStack>
      ),
    },
  ], [labelSortDirection, bumpTablePage, openEdit, requestDelete]);


  return {
    toast,
    error, cardBg, borderColor, tableEpoch, filteredPiiTypes, piiColumns,
    searchQuery, setSearchQuery, filterMask, setFilterMask,
    hasActiveFilters, clearAllFilters, bumpTablePage, openCreate, loading, allTypes,
    viewModal, viewPiiId, closePiiView, openEdit, openPiiView,
    modal, editing, label, setLabel, regex, setRegex, examples, setExamples, mask, setMask,
    saving, piiDetailLoading, save,
    confirmDel, deleteTarget, deleting, confirmDelete,
  };
}

export type UsePiiTypesPanelReturn = ReturnType<typeof usePiiTypesPanel>;
