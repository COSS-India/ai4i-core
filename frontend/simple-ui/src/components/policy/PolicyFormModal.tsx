import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Box,
  Button,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  HStack,
  Input,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
} from "@chakra-ui/react";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import FieldLabel from "../common/FieldLabel";
import FieldHint from "../common/FieldHint";
import { policyService, type PiiTypeOut, type PolicyOut } from "../../services/policyService";
import {
  INSTITUTION,
  INSTITUTION_ARTICLE,
  INSTITUTIONS,
  isTenantStatus,
  TENANT,
} from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import { useTenantsList } from "../../hooks/useTenantsList";
import {
  formatDt,
  getPolicyApiErrorMessage,
  parseDelimitedValues,
} from "./policyShared";

function policyFormFromList(policy: PolicyOut): boolean {
  return Array.isArray(policy.supported_languages) && Array.isArray(policy.pii_types);
}

const LANGUAGE_OPTIONS = ["en", "hi"] as const;

export function PolicyFormModal({
  isOpen,
  onClose,
  policyId,
  piiOptions,
  refreshPiiOptions,
  cachedPolicy = null,
  onSaved,
  onError,
  mode,
  onViewEdit,
  onViewDelete,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  piiOptions: PiiTypeOut[];
  refreshPiiOptions: () => Promise<void> | void;
  /** Row already loaded by the policy list. Skips GET /policies/{id} when complete. */
  cachedPolicy?: PolicyOut | null;
  onSaved: () => void;
  onError: (msg: string) => void;
  mode?: "create" | "edit" | "view";
  onViewEdit?: (id: string) => void;
  onViewDelete?: (policy: PolicyOut) => void;
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
  const [loadedPolicy, setLoadedPolicy] = useState<PolicyOut | null>(null);
  const resolvedMode = mode ?? (policyId ? "edit" : "create");
  const readOnly = resolvedMode === "view";
  const tenantsQuery = useTenantsList({ enabled: isOpen });
  const tenantsError = tenantsQuery.isError
    ? `Could not load ${INSTITUTIONS.toLowerCase()}. You can enter ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()} ID below.`
    : null;
  const tenantsLoading = tenantsQuery.isLoading;
  const tenants = useMemo(() => {
    const list = (tenantsQuery.data?.tenants ?? []).filter((tenant) =>
      isTenantStatus(tenant.status, TENANT.STATUS.ACTIVE)
    );
    return [...list].sort((a, b) =>
      (a.organisation ?? "").localeCompare(b.organisation ?? "", undefined, {
        sensitivity: "base",
      })
    );
  }, [tenantsQuery.data]);

  useEffect(() => {
    if (!isOpen) return;
    // Reuse the page catalog when it is already loaded; fetch only if mount
    // load failed or has not produced a result yet.
    void refreshPiiOptions();
  }, [isOpen, refreshPiiOptions]);

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
      setLoadedPolicy(null);
      return;
    }
    const applyPolicy = (p: PolicyOut) => {
      setName(p.name);
      setDescription(p.description || "");
      setIsGlobal(p.is_global);
      const tids = p.tenant_ids ?? [];
      setTenantIds(tids);
      setTenantInput(tids.join(", "));
      setLangs(p.supported_languages?.length ? p.supported_languages : ["en"]);
      setSelectedPii((p.pii_types || []).map((x: { pii_type_id: string }) => x.pii_type_id));
      setLoadedPolicy(p);
    };
    if (
      cachedPolicy &&
      cachedPolicy.policy_id === policyId &&
      policyFormFromList(cachedPolicy)
    ) {
      applyPolicy(cachedPolicy);
      setLoadingDetail(false);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    const run = async () => {
      try {
        const res = await policyService.getPolicy(policyId);
        if (cancelled) return;
        applyPolicy(res.data);
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
  }, [isOpen, policyId, onError, cachedPolicy]);

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
      onError(`Select at least one ${INSTITUTION.toLowerCase()} for non-global policies`);
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
  const optionListScroll = { maxH: "220px" as const, overflowY: "auto" as const };

  const formBody = loadingDetail ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : (
        <Stack spacing={4}>
          {readOnly ? (
            <ReadOnlyField label="Name">{name || "—"}</ReadOnlyField>
          ) : (
            <FormControl isRequired>
              <FieldLabel>Name</FieldLabel>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </FormControl>
          )}
          {readOnly ? (
            <ReadOnlyField label="Description">{description || "No description"}</ReadOnlyField>
          ) : (
            <FormControl>
              <FieldLabel>Description</FieldLabel>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </FormControl>
          )}
          {readOnly ? (
            <ReadOnlyField label="Global policy">{isGlobal ? "Yes" : "No"}</ReadOnlyField>
          ) : (
            <FormControl display="flex" alignItems="center">
              <FieldLabel formLabelProps={{ mb: 0 }}>Global policy</FieldLabel>
              <Switch isChecked={isGlobal} onChange={(e) => setIsGlobal(e.target.checked)} />
            </FormControl>
          )}
          {!isGlobal && readOnly ? (
            <ReadOnlyField label={INSTITUTIONS}>
              {(tenantsError || tenants.length === 0
                ? parseDelimitedValues(tenantInput)
                : tenantIds
              )
                .map((id) => tenantById.get(id)?.organisation || id)
                .join(", ") || "—"}
            </ReadOnlyField>
          ) : null}
          {!isGlobal && !readOnly && (
            <FormControl isRequired>
              <FieldLabel>{INSTITUTIONS}</FieldLabel>
              {tenantsLoading ? (
                <HStack spacing={2} py={2}>
                  <Spinner size="sm" />
                  <Text fontSize="sm" color="gray.600">
                    Loading {INSTITUTIONS.toLowerCase()}…
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
                      No {INSTITUTIONS.toLowerCase()} found. Enter {INSTITUTION.toLowerCase()} IDs manually.
                    </Text>
                  )}
                  <Textarea
                    placeholder={`${INSTITUTION} IDs separated by comma or newline`}
                    value={tenantInput}
                    onChange={(e) => setTenantInput(e.target.value)}
                    isReadOnly={readOnly}
                    fontFamily="mono"
                    fontSize="sm"
                    rows={3}
                  />
                  <FieldHint>{FIELD_HINTS.policy.tenantIdsManual}</FieldHint>
                </>
              ) : (
                <>
                  <Box
                    borderWidth="1px"
                    borderRadius="md"
                    p={3}
                    {...optionListScroll}
                  >
                    <CheckboxGroup value={tenantIds} onChange={(v) => setTenantIds(v as string[])}>
                      <Stack spacing={2}>
                        {tenantIds
                          .filter((id) => !tenantById.has(id))
                          .map((id) => (
                            <Checkbox key={id} value={id} isRequired={false} isDisabled={readOnly}>
                              Current assignment - {id}
                            </Checkbox>
                          ))}
                        {tenants.map((t) => (
                          <Checkbox key={t.tenant_id} value={t.tenant_id} isRequired={false} isDisabled={readOnly}>
                            {t.organisation || "(Unnamed)"}{" "}
                            <Text as="span" color="gray.500" fontSize="sm">
                              ({t.tenant_id})
                            </Text>
                          </Checkbox>
                        ))}
                      </Stack>
                    </CheckboxGroup>
                  </Box>
                  <FieldHint>{FIELD_HINTS.policy.tenantIdsSelect}</FieldHint>
                </>
              )}
            </FormControl>
          )}
          {readOnly ? (
            <ReadOnlyField label="Supported languages">{langs.join(", ") || "—"}</ReadOnlyField>
          ) : (
          <FormControl>
            <FieldLabel>Supported languages</FieldLabel>
            <CheckboxGroup value={langs} onChange={(v) => setLangs(v as string[])}>
              <HStack spacing={4}>
                {LANGUAGE_OPTIONS.map((code) => (
                  <Checkbox key={code} value={code} isRequired={false} isDisabled={readOnly}>
                    {code}
                  </Checkbox>
                ))}
              </HStack>
            </CheckboxGroup>
          </FormControl>
          )}
          {readOnly ? (
            <ReadOnlyField label="PII types (policy configuration)">
              {selectedPii.length
                ? selectedPii.map((id) => piiById.get(id)?.pii_type_label || id).join(", ")
                : "—"}
            </ReadOnlyField>
          ) : (
          <FormControl isRequired>
            <FieldLabel>PII types (policy configuration)</FieldLabel>
            <Box
              borderWidth="1px"
              borderRadius="md"
              p={3}
              {...optionListScroll}
            >
              <CheckboxGroup
                value={selectedPii}
                onChange={(v) => setSelectedPii(v as string[])}
              >
                <Stack spacing={2}>
                  {piiOptions.map((p) => (
                    <Checkbox key={p.pii_type_id} value={p.pii_type_id} isRequired={false} isDisabled={readOnly}>
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
          )}
        </Stack>
      );

  if (!isOpen) return null;

  const pageTitle = resolvedMode === "create" ? "Create Policy" : name || "Policy";
  const pageDescription =
    resolvedMode === "create"
      ? "Define a policy and choose which PII types it covers."
      : resolvedMode === "view"
        ? "View this policy's scope and PII coverage."
        : "Update who this policy applies to and which PII types it covers.";

  return (
    <FormDrawer
      isOpen={isOpen}
      onClose={onClose}
      lockDismiss={saving}
      title={pageTitle}
      description={pageDescription}
      footer={
        readOnly ? (
          <FormActions hideSubmit cancelLabel="Close" onCancel={onClose} pt={0} />
        ) : (
          <FormActions
            cancelLabel="Cancel"
            submitLabel={policyId ? "Save Changes" : "Create Policy"}
            onCancel={onClose}
            onSubmit={() => void handleSubmit()}
            isLoading={saving}
            loadingText={policyId ? "Saving..." : "Creating..."}
            justify="space-between"
            pt={0}
          />
        )
      }
    >
      {readOnly && policyId ? (
        <HStack spacing={2} mb={4}>
          {loadedPolicy ? (
            <Badge colorScheme={loadedPolicy.is_active ? "green" : "gray"}>
              {loadedPolicy.is_active ? "Active" : "Inactive"}
            </Badge>
          ) : null}
          {loadedPolicy && onViewDelete ? (
            <Button
              size="sm"
              colorScheme="red"
              variant="outline"
              onClick={() => onViewDelete(loadedPolicy)}
            >
              Delete
            </Button>
          ) : null}
          {onViewEdit ? (
            <Button size="sm" onClick={() => onViewEdit(policyId)}>
              Edit
            </Button>
          ) : null}
        </HStack>
      ) : null}
      {loadingDetail ? formBody : <FormSection title="Policy">{formBody}</FormSection>}
      {readOnly && loadedPolicy && !loadingDetail ? (
        <FormSection title="Record">
          <ReadOnlyField label="Policy ID">
            <Text fontFamily="mono" fontSize="sm">{loadedPolicy.policy_id}</Text>
          </ReadOnlyField>
          <ReadOnlyField label="Created">{formatDt(loadedPolicy.created_at)}</ReadOnlyField>
        </FormSection>
      ) : null}
    </FormDrawer>
  );
}
