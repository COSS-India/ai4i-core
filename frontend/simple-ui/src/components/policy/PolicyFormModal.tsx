import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  Select,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
  Tooltip,
  useDisclosure,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import { useAdminTableSurface } from "../common/TableControls";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";
import { isTenantStatus, TENANT } from "../../config/constants";
import { listTenants } from "../../services/tenantService";
import type { TenantView } from "../../types/tenant";
import { AUDIT_PAGE_SIZE_OPTIONS, LANGUAGE_OPTIONS, MASK_OPTIONS } from "./constants";
import { formatDt, getPolicyApiErrorMessage, parseDelimitedValues, useDebouncedValue } from "./utils";

export default function PolicyFormModal({
  isOpen,
  onClose,
  policyId,
  piiOptions,
  refreshPiiOptions,
  onSaved,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  piiOptions: PiiTypeOut[];
  refreshPiiOptions: () => Promise<void> | void;
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isGlobal, setIsGlobal] = useState(true);
  const [tenantIds, setTenantIds] = useState<string[]>([]);
  const [tenantInput, setTenantInput] = useState("");
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [selectedPii, setSelectedPii] = useState<string[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);
  const [tenantsError, setTenantsError] = useState<string | null>(null);

  const didFetchPiiOptionsForThisOpen = useRef(false);
  useEffect(() => {
    if (!isOpen) {
      didFetchPiiOptionsForThisOpen.current = false;
      return;
    }

    // Only fetch PII options once when the modal is opened, to avoid background load.
    if (didFetchPiiOptionsForThisOpen.current) return;
    didFetchPiiOptionsForThisOpen.current = true;
    void refreshPiiOptions();
  }, [isOpen, refreshPiiOptions]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setTenantsLoading(true);
    setTenantsError(null);
    void listTenants()
      .then((res) => {
        if (cancelled) return;
        const list = (res.tenants ?? []).filter((tenant) =>
          isTenantStatus(tenant.status, TENANT.STATUS.ACTIVE)
        );
        setTenants(
          [...list].sort((a, b) =>
            (a.organisation ?? "").localeCompare(b.organisation ?? "", undefined, {
              sensitivity: "base",
            })
          )
        );
      })
      .catch(() => {
        if (!cancelled) setTenantsError("Could not load tenants. You can enter a tenant ID below.");
      })
      .finally(() => {
        if (!cancelled) setTenantsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    if (!policyId) {
      setName("");
      setDescription("");
      setIsGlobal(true);
      setTenantIds([]);
      setTenantInput("");
      setLangs(["en"]);
      setSelectedPii([]);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    const run = async () => {
      try {
        const res = await policyService.getPolicy(policyId);
        if (cancelled) return;
        const p = res.data;
        setName(p.name);
        setDescription(p.description || "");
        setIsGlobal(p.is_global);
        const tids = p.tenant_ids ?? [];
        setTenantIds(tids);
        setTenantInput(tids.join(", "));
        setLangs(p.supported_languages?.length ? p.supported_languages : ["en"]);
        setSelectedPii((p.pii_types || []).map((x: { pii_type_id: string }) => x.pii_type_id));
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load policy"));
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, policyId, onError]);

  const handleSubmit = async () => {
    const normalizedTenantIds =
      tenantsError || tenants.length === 0 ? parseDelimitedValues(tenantInput) : tenantIds;

    if (!name.trim()) {
      onError("Name is required");
      return;
    }
    if (!langs.length) {
      onError("Select at least one language");
      return;
    }
    if (!isGlobal && !normalizedTenantIds.length) {
      onError("Select at least one tenant for non-global policies");
      return;
    }
    if (!selectedPii.length) {
      onError("Select at least one PII type");
      return;
    }
    const pii_types = selectedPii.map((pii_type_id) => ({ pii_type_id }));
    setSaving(true);
    try {
      if (policyId) {
        const body: Parameters<typeof policyService.updatePolicy>[1] = {
          name: name.trim(),
          description: description.trim() || null,
          supported_languages: langs,
          is_global: isGlobal,
          tenant_ids: isGlobal ? [] : normalizedTenantIds,
          pii_types,
        };
        await policyService.updatePolicy(policyId, body);
      } else {
        await policyService.createPolicy({
          name: name.trim(),
          description: description.trim() || undefined,
          is_global: isGlobal,
          supported_languages: langs,
          tenant_ids: isGlobal ? undefined : normalizedTenantIds,
          pii_types,
        });
      }
      onSaved();
    } catch (e: unknown) {
      onError(getPolicyApiErrorMessage(e, "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const piiById = useMemo(
    () => new Map(piiOptions.map((p) => [p.pii_type_id, p])),
    [piiOptions]
  );
  const tenantById = useMemo(
    () => new Map(tenants.map((tenant) => [tenant.tenant_id, tenant])),
    [tenants]
  );

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={policyId ? "Edit policy definition" : "New policy definition"}
      size="xl"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button colorScheme="blue" onClick={() => void handleSubmit()} isLoading={saving}>
            Save
          </Button>
        </HStack>
      }
    >
      {loadingDetail ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FormLabel>Name</FormLabel>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </FormControl>
          <FormControl>
            <FormLabel>Description</FormLabel>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </FormControl>
          <FormControl display="flex" alignItems="center">
            <FormLabel mb={0}>Global policy</FormLabel>
            <Switch isChecked={isGlobal} onChange={(e) => setIsGlobal(e.target.checked)} />
          </FormControl>
          {!isGlobal && (
            <FormControl isRequired>
              <FormLabel>Tenants</FormLabel>
              {tenantsLoading ? (
                <HStack spacing={2} py={2}>
                  <Spinner size="sm" />
                  <Text fontSize="sm" color="gray.600">
                    Loading tenants…
                  </Text>
                </HStack>
              ) : tenantsError || tenants.length === 0 ? (
                <>
                  {tenantsError ? (
                    <Text fontSize="sm" color="red.500" mb={2}>
                      {tenantsError}
                    </Text>
                  ) : (
                    <Text fontSize="sm" color="gray.600" mb={2}>
                      No tenants found. Enter tenant IDs manually.
                    </Text>
                  )}
                  <Textarea
                    placeholder={
                      policyId
                        ? "Tenant IDs separated by comma or newline"
                        : "Tenant IDs separated by comma or newline"
                    }
                    value={tenantInput}
                    onChange={(e) => setTenantInput(e.target.value)}
                    fontFamily="mono"
                    fontSize="sm"
                    rows={3}
                  />
                  <FormHelperText>Enter one or more tenant IDs.</FormHelperText>
                </>
              ) : (
                <>
                  <Box maxH="220px" overflowY="auto" borderWidth="1px" borderRadius="md" p={3}>
                    <CheckboxGroup value={tenantIds} onChange={(v) => setTenantIds(v as string[])}>
                      <Stack spacing={2}>
                        {tenantIds
                          .filter((id) => !tenantById.has(id))
                          .map((id) => (
                            <Checkbox key={id} value={id}>
                              Current assignment - {id}
                            </Checkbox>
                          ))}
                        {tenants.map((t) => (
                          <Checkbox key={t.tenant_id} value={t.tenant_id}>
                            {t.organisation || "(Unnamed)"}{" "}
                            <Text as="span" color="gray.500" fontSize="sm">
                              ({t.tenant_id})
                            </Text>
                          </Checkbox>
                        ))}
                      </Stack>
                    </CheckboxGroup>
                  </Box>
                  <FormHelperText>
                    Select one or more active tenant assignments for this policy.
                  </FormHelperText>
                </>
              )}
            </FormControl>
          )}
          <FormControl>
            <FormLabel>Supported languages</FormLabel>
            <CheckboxGroup value={langs} onChange={(v) => setLangs(v as string[])}>
              <HStack spacing={4}>
                {LANGUAGE_OPTIONS.map((code) => (
                  <Checkbox key={code} value={code}>
                    {code}
                  </Checkbox>
                ))}
              </HStack>
            </CheckboxGroup>
          </FormControl>
          <FormControl isRequired>
            <FormLabel>PII types (policy configuration)</FormLabel>
            <Box maxH="220px" overflowY="auto" borderWidth="1px" borderRadius="md" p={3}>
              <CheckboxGroup
                value={selectedPii}
                onChange={(v) => setSelectedPii(v as string[])}
              >
                <Stack spacing={2}>
                  {piiOptions.map((p) => (
                    <Checkbox key={p.pii_type_id} value={p.pii_type_id}>
                      {p.pii_type_label}{" "}
                      <Text as="span" color="gray.500" fontSize="sm">
                        ({p.mask_format})
                      </Text>
                    </Checkbox>
                  ))}
                </Stack>
              </CheckboxGroup>
              {!piiOptions.length && (
                <Text fontSize="sm" color="gray.500">
                  No PII types yet. Add some under &quot;PII type library&quot;.
                </Text>
              )}
            </Box>
            <Text fontSize="xs" color="gray.500" mt={1}>
              {selectedPii.length} selected
              {selectedPii.some((id) => !piiById.has(id)) ? " (includes types not in current list)" : ""}
            </Text>
          </FormControl>
        </Stack>
      )}
    </StandardModal>
  );
}
