import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Radio,
  RadioGroup,
  Select,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Textarea,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import CreateButton from "../../common/CreateButton";
import FieldLabel from "../../common/FieldLabel";
import DataTable, {
  createActionsColumn,
  type DataTableColumn,
} from "../../common/table";
import { buildSample, runDetection, type DetectionHit } from "./detection";
import { useDeferredColumnSort } from "../../../utils/tableSort";
import {
  HANDLING_OPTIONS,
  policyEffective,
  subcategoryEffective,
  type PiiType,
  type Policy,
} from "./model";
import { usePiiPolicies, type ProcessingTarget } from "./PiiPoliciesProvider";
import DataTableActions from "../../common/DataTableActions";
import { handlingBadgeColor, StatusToggle } from "./ui";

function LockedNotice({ children }: { children: React.ReactNode }) {
  return (
    <Alert status="warning" borderRadius="md" mb={4}>
      <AlertIcon />
      {children}
    </Alert>
  );
}

function useParentActive() {
  const { categories, subcategories, view } = usePiiPolicies();
  const sub =
    view.kind === "sub" ? subcategories.find((s) => s.id === view.subcategoryId) : undefined;
  return {
    sub,
    parentActive: sub ? subcategoryEffective(sub, categories) === "Active" : true,
  };
}

export function PolicyList() {
  const store = usePiiPolicies();
  const {
    policies,
    domains,
    policySearch,
    setPolicySearch,
    policyDomainFilter,
    setPolicyDomainFilter,
    openDrawer,
    askConfirm,
    setPolicyStatus,
    deletePolicy,
  } = store;
  const { sub, parentActive } = useParentActive();

  const rows = useMemo(
    () =>
      policies.filter((p) => {
        const matchesName = p.name.toLowerCase().includes(policySearch.toLowerCase());
        const matchesDomain = !policyDomainFilter || p.domainIds.includes(policyDomainFilter);
        return matchesName && matchesDomain;
      }),
    [policies, policySearch, policyDomainFilter],
  );

  const policySortAccessors = useMemo(
    () => ({
      name: (row: Policy) => row.name,
      policyType: (row: Policy) => row.policyType,
      languages: (row: Policy) => row.languages.join(", "),
    }),
    [],
  );
  const policySort = useDeferredColumnSort("name", policySortAccessors);
  const sortedPolicies = useMemo(() => policySort.apply(rows), [policySort, rows]);

  const requestStatus = (policy: Policy, nextActive: boolean) => {
    askConfirm({
      title: `${nextActive ? "Activate" : "Deactivate"} "${policy.name}"?`,
      body: nextActive
        ? "Activating this policy makes it available to institutions and starts PII detection and sanitization. Continue?"
        : "Deactivating this policy will stop PII detection and sanitization for subscribed institutions. Continue?",
      confirmLabel: nextActive ? "Activate" : "Deactivate",
      confirmColorScheme: nextActive ? "blue" : "red",
      onConfirm: () => setPolicyStatus(policy.id, nextActive ? "Active" : "Inactive"),
    });
  };

  const columns = useMemo<DataTableColumn<Policy>[]>(
    () => [
      {
        id: "policyId",
        header: "Policy ID",
        cell: (row) => (
          <Badge fontFamily="mono" textTransform="none">
            {row.policyId}
          </Badge>
        ),
      },
      {
        id: "name",
        header: "Policy Name",
        sortable: true,
        sortAccessor: (row) => row.name,
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium">
            {row.name}
          </Text>
        ),
      },
      {
        id: "policyType",
        header: "Policy Type",
        sortable: true,
        sortAccessor: (row) => row.policyType,
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.policyType === "Global" ? "Global" : "Institution level"}
          </Text>
        ),
      },
      {
        id: "domain",
        header: "Domain",
        cell: (row) => (
          <Badge textTransform="none">
            {row.domainIds
              .map((id) => domains.find((d) => d.id === id)?.name)
              .filter(Boolean)
              .join(", ") || "—"}
          </Badge>
        ),
      },
      {
        id: "languages",
        header: "Languages",
        sortable: true,
        sortAccessor: (row) => row.languages.join(", "),
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.languages.join(", ")}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (row) => (
          <StatusToggle
            status={row.status}
            effective={policyEffective(row, parentActive)}
            locked={!parentActive}
            label={`${row.name} status`}
            onToggle={() => requestStatus(row, row.status !== "Active")}
          />
        ),
      },
      createActionsColumn<Policy>({
        getActions: (row) => [
          { id: "view", label: "View", onClick: () => openDrawer({ kind: "view-policy", id: row.id }) },
          { id: "edit", label: "Edit", onClick: () => openDrawer({ kind: "edit-policy", id: row.id }) },
          {
            id: "delete",
            label: "Delete",
            onClick: () =>
              askConfirm({
                title: "Delete policy?",
                body: "This will permanently remove its PII configuration. This action cannot be undone.",
                confirmLabel: "Delete",
                confirmColorScheme: "red",
                onConfirm: () => deletePolicy(row.id),
              }),
          },
        ],
      }),
    ],
    [domains, parentActive, openDrawer, askConfirm, deletePolicy],
  );

  return (
    <Box>
      {!parentActive ? (
        <LockedNotice>
          All policies here are inactive — "{sub?.name}" (or its category) is currently disabled.
        </LockedNotice>
      ) : null}
      <DataTable
        layout="admin"
        items={sortedPolicies}
        columns={columns}
        getRowKey={(row) => row.id}
        sort={policySort.sort}
        onSortChange={policySort.onSortChange}
        paginate="client"
        paginationPosition="bottom"
        unfilteredCount={policies.length}
        hasActiveFilters={Boolean(policySearch || policyDomainFilter)}
        onClearFilters={() => {
          setPolicySearch("");
          setPolicyDomainFilter("");
        }}
        emptyMessage="No policies yet."
        noResultsMessage="No policies match your search."
        onRowClick={(row) => openDrawer({ kind: "view-policy", id: row.id })}
        filterToolbarRightContent={
          <CreateButton onClick={() => openDrawer({ kind: "create-policy" })}>Create Policy</CreateButton>
        }
        search={{
          value: policySearch,
          onChange: setPolicySearch,
          placeholder: "Search policies...",
          fields: ["name"],
        }}
        filterDefs={[
          {
            id: "domain",
            label: "Domain",
            type: "select",
            value: policyDomainFilter,
            onChange: setPolicyDomainFilter,
            width: "170px",
            options: [
              { value: "", label: "All Domains" },
              ...domains.map((d) => ({ value: d.id, label: d.name })),
            ],
          },
        ]}
      />
    </Box>
  );
}

export function ConfigurationPanel() {
  const { configTab, setConfigTab } = usePiiPolicies();
  return (
    <Tabs
      variant="enclosed"
      colorScheme="blue"
      index={configTab === "domain" ? 1 : 0}
      onChange={(index) => setConfigTab(index === 1 ? "domain" : "types")}
    >
      <TabList>
        <Tab fontWeight="semibold">PII Types</Tab>
        <Tab fontWeight="semibold">Domain</Tab>
      </TabList>
      <TabPanels>
        <TabPanel px={0} pt={4}>
          <TypeLibrary />
        </TabPanel>
        <TabPanel px={0} pt={4}>
          <DomainTable />
        </TabPanel>
      </TabPanels>
    </Tabs>
  );
}

function TypeLibrary() {
  const {
    types,
    typeSearch,
    setTypeSearch,
    typeHandlingFilter,
    setTypeHandlingFilter,
    openDrawer,
    askConfirm,
    deleteType,
  } = usePiiPolicies();

  const rows = types.filter((t) => {
    const matchesName = t.name.toLowerCase().includes(typeSearch.toLowerCase());
    const matchesHandling = !typeHandlingFilter || t.handling === typeHandlingFilter;
    return matchesName && matchesHandling;
  });

  const typeSortAccessors = useMemo(
    () => ({
      name: (row: PiiType) => row.name,
      detection: (row: PiiType) => row.detectionMode,
    }),
    [],
  );
  const typeSort = useDeferredColumnSort("name", typeSortAccessors);
  const sortedTypes = useMemo(() => typeSort.apply(rows), [typeSort, rows]);

  const columns = useMemo<DataTableColumn<PiiType>[]>(
    () => [
      {
        id: "name",
        header: "PII Type",
        sortable: true,
        sortAccessor: (row) => row.name,
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium">
            {row.name}
          </Text>
        ),
      },
      {
        id: "handling",
        header: "Handling",
        cell: (row) => (
          <Badge colorScheme={handlingBadgeColor(row.handling)} textTransform="none">
            {row.handling}
          </Badge>
        ),
      },
      {
        id: "detection",
        header: "Detection",
        sortable: true,
        sortAccessor: (row) => row.detectionMode,
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.detectionMode}
          </Text>
        ),
      },
      createActionsColumn<PiiType>({
        getActions: (row) => [
          { id: "view", label: "View", onClick: () => openDrawer({ kind: "view-type", id: row.id }) },
          { id: "edit", label: "Edit", onClick: () => openDrawer({ kind: "edit-type", id: row.id }) },
          {
            id: "delete",
            label: "Delete",
            disabled: row.isDefault,
            tooltip: row.isDefault ? "This cannot be removed" : "Delete",
            onClick: () =>
              askConfirm({
                title: "Delete PII type?",
                body: "This will remove the PII type from the library. Policies using this type will need to be updated. This action cannot be undone.",
                confirmLabel: "Delete",
                confirmColorScheme: "red",
                onConfirm: () => deleteType(row.id),
              }),
          },
        ],
      }),
    ],
    [openDrawer, askConfirm, deleteType],
  );

  return (
    <DataTable
      layout="admin"
      items={sortedTypes}
      columns={columns}
      getRowKey={(row) => row.id}
      sort={typeSort.sort}
      onSortChange={typeSort.onSortChange}
      paginate="client"
      paginationPosition="bottom"
      unfilteredCount={types.length}
      hasActiveFilters={Boolean(typeSearch || typeHandlingFilter)}
      onClearFilters={() => {
        setTypeSearch("");
        setTypeHandlingFilter("");
      }}
      emptyMessage="No PII types yet."
      noResultsMessage="No PII types match your search."
      onRowClick={(row) => openDrawer({ kind: "view-type", id: row.id })}
      filterToolbarRightContent={
        <CreateButton onClick={() => openDrawer({ kind: "add-type" })}>Add PII Type</CreateButton>
      }
      search={{
        value: typeSearch,
        onChange: setTypeSearch,
        placeholder: "Search PII types...",
        fields: ["name"],
      }}
      filterDefs={[
        {
          id: "handling",
          label: "Handling",
          type: "select",
          value: typeHandlingFilter,
          onChange: setTypeHandlingFilter,
          width: "150px",
          options: [
            { value: "", label: "All Handling" },
            ...HANDLING_OPTIONS.map((h) => ({ value: h, label: h })),
          ],
        },
      ]}
    />
  );
}

function DomainTable() {
  const { domains, domainSearch, setDomainSearch, openDrawer, askConfirm, deleteDomain } =
    usePiiPolicies();
  const rows = domains.filter((d) => d.name.toLowerCase().includes(domainSearch.toLowerCase()));
  const domainSortAccessors = useMemo(
    () => ({
      name: (row: (typeof domains)[number]) => row.name,
    }),
    [],
  );
  const domainSort = useDeferredColumnSort("name", domainSortAccessors);
  const sortedDomains = useMemo(() => domainSort.apply(rows), [domainSort, rows]);

  const columns = useMemo<DataTableColumn<(typeof domains)[number]>[]>(
    () => [
      {
        id: "name",
        header: "Domain Name",
        sortable: true,
        sortAccessor: (row) => row.name,
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium">
            {row.name}
          </Text>
        ),
      },
      {
        id: "description",
        header: "Description",
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.description || "—"}
          </Text>
        ),
      },
      createActionsColumn({
        getActions: (row) => [
          { id: "edit", label: "Edit", onClick: () => openDrawer({ kind: "edit-domain", id: row.id }) },
          {
            id: "delete",
            label: "Delete",
            disabled: row.isDefault,
            tooltip: row.isDefault ? "This cannot be removed" : "Delete",
            onClick: () =>
              askConfirm({
                title: "Delete domain?",
                body: "PII types and policies tagged with this domain will keep their data, but the domain filter will no longer be available.",
                confirmLabel: "Delete",
                confirmColorScheme: "red",
                onConfirm: () => deleteDomain(row.id),
              }),
          },
        ],
      }),
    ],
    [openDrawer, askConfirm, deleteDomain],
  );

  return (
    <DataTable
      layout="admin"
      items={sortedDomains}
      columns={columns}
      getRowKey={(row) => row.id}
      sort={domainSort.sort}
      onSortChange={domainSort.onSortChange}
      paginate="client"
      paginationPosition="bottom"
      unfilteredCount={domains.length}
      hasActiveFilters={Boolean(domainSearch)}
      onClearFilters={() => setDomainSearch("")}
      emptyMessage="No domains yet."
      noResultsMessage="No domains match your search."
      filterToolbarRightContent={
        <CreateButton onClick={() => openDrawer({ kind: "add-domain" })}>Create Domain</CreateButton>
      }
      search={{
        value: domainSearch,
        onChange: setDomainSearch,
        placeholder: "Search domains...",
        fields: ["name"],
      }}
    />
  );
}

export function PlaygroundPanel() {
  const {
    policies,
    types,
    playgroundPolicyId,
    playgroundTarget,
    playgroundInput,
    playgroundResult,
    setPlaygroundPolicy,
    setPlaygroundTarget,
    setPlaygroundInput,
    setPlaygroundResult,
    loadPlaygroundSample,
  } = usePiiPolicies();
  const { parentActive } = useParentActive();
  const activePolicies = policies.filter((p) => policyEffective(p, parentActive) === "Active");
  const selected = policies.find((p) => p.policyId === playgroundPolicyId) ?? null;
  const canRun = Boolean(selected && playgroundTarget && playgroundInput.trim());
  const resultRows = playgroundResult?.results ?? [];
  const resultSortAccessors = useMemo(
    () => ({
      type: (row: DetectionHit) => row.typeName,
      instances: (row: DetectionHit) => row.instances.length,
      action: (row: DetectionHit) => row.handling,
    }),
    [],
  );
  const resultSort = useDeferredColumnSort("type", resultSortAccessors);
  const sortedResults = useMemo(() => resultSort.apply(resultRows), [resultSort, resultRows]);

  return (
    <Box maxW="4xl">
      <Box borderWidth="1px" borderColor="ink.200" borderRadius="md" p={4} mb={5}>
        <Flex wrap="wrap" align="flex-end" gap={4}>
          <Box flex="1" minW="240px">
            <FieldLabel required>Select Policy</FieldLabel>
            <Select
              aria-label="Select policy"
              placeholder="Choose a policy to test"
              value={playgroundPolicyId}
              onChange={(e) => {
                const policy = policies.find((p) => p.policyId === e.target.value);
                setPlaygroundPolicy(e.target.value, policy ? buildSample(policy, types) : "");
              }}
            >
              {activePolicies.map((p) => (
                <option key={p.policyId} value={p.policyId}>
                  {p.policyId} · {p.name}
                </option>
              ))}
            </Select>
          </Box>
          <Box>
            <FieldLabel required>Processing Target</FieldLabel>
            <RadioGroup
              value={playgroundTarget}
              onChange={(value) => setPlaygroundTarget(value as ProcessingTarget)}
            >
              <HStack h="10" px={3} borderWidth="1px" borderColor="ink.200" borderRadius="md" spacing={4}>
                <Radio value="response" size="sm">
                  Response
                </Radio>
                <Radio value="storage" size="sm">
                  Storage
                </Radio>
              </HStack>
            </RadioGroup>
          </Box>
        </Flex>
        <Text fontSize="xs" color="ink.500" mt={3}>
          Both targets detect PII and apply each type’s configured Mask, Redact, or Hash action — the
          response is sanitized the same as anything written to storage.
        </Text>
        {selected ? <SimplePolicySummary policy={selected} /> : null}
      </Box>

      <Box borderWidth="1px" borderColor="ink.200" borderRadius="md" p={4} mb={5}>
        <Flex justify="space-between" align="center" mb={2}>
          <FieldLabel>Input Request</FieldLabel>
          {selected ? (
            <Button
              variant="link"
              size="xs"
              onClick={() => loadPlaygroundSample(buildSample(selected, types))}
            >
              Load sample
            </Button>
          ) : null}
        </Flex>
        <Textarea
          rows={6}
          fontFamily="mono"
          fontSize="sm"
          isDisabled={!selected}
          placeholder={selected ? "Paste a request payload to test…" : "Select a policy first"}
          value={playgroundInput}
          onChange={(e) => setPlaygroundInput(e.target.value)}
        />
        <Button mt={3} size="sm" isDisabled={!canRun} onClick={() => {
          if (!selected) return;
          const linked = selected.typeIds
            .map((id) => types.find((t) => t.id === id))
            .filter((t): t is PiiType => Boolean(t));
          setPlaygroundResult(runDetection(playgroundInput, linked));
        }}>
          Run Simulation
        </Button>
      </Box>

      {playgroundResult && selected ? (
        <Box>
          <Text fontSize="sm" fontWeight="semibold" mb={3}>
            Detected PII in this request
          </Text>
          {playgroundResult.results.length === 0 ? (
            <Text fontSize="sm" color="ink.500" mb={4}>
              No PII detected for the types enabled in {selected.policyId}.
            </Text>
          ) : (
            <Box mb={4}>
              <DataTable
                layout="admin"
                items={sortedResults}
                getRowKey={(row) => row.typeId}
                sort={resultSort.sort}
                onSortChange={resultSort.onSortChange}
                paginate="client"
                paginationPosition="bottom"
                columns={[
                  {
                    id: "type",
                    header: "PII Type",
                    sortable: true,
                    sortAccessor: (row) => row.typeName,
                    cell: (row) => row.typeName,
                  },
                  {
                    id: "instances",
                    header: "Instances",
                    sortable: true,
                    sortAccessor: (row) => row.instances.length,
                    cell: (row) => row.instances.length,
                  },
                  {
                    id: "action",
                    header: "Action",
                    sortable: true,
                    sortAccessor: (row) => row.handling,
                    cell: (row) => (
                      <Badge colorScheme={handlingBadgeColor(row.handling)} textTransform="none">
                        {row.handling}
                      </Badge>
                    ),
                  },
                  {
                    id: "output",
                    header: "Output",
                    cell: (row) => (
                      <Text fontFamily="mono" fontSize="xs" color="ink.500">
                        {row.replacements.join(", ")}
                      </Text>
                    ),
                  },
                ]}
              />
            </Box>
          )}
          <Flex direction={{ base: "column", lg: "row" }} gap={4}>
            <PayloadCard title="Original Payload" text={playgroundInput} />
            <PayloadCard
              title={playgroundTarget === "storage" ? "Storage Payload" : "Response Payload"}
              text={playgroundResult.sanitized}
            />
          </Flex>
        </Box>
      ) : null}
    </Box>
  );
}

function SimplePolicySummary({ policy }: { policy: Policy }) {
  const { types } = usePiiPolicies();
  return (
    <Flex wrap="wrap" gap={4} borderTopWidth="1px" borderColor="ink.200" pt={3} mt={3}>
      <Box>
        <FieldLabel variant="metric">Policy Type</FieldLabel>
        <Badge mt={1.5} colorScheme={policy.policyType === "Global" ? "blue" : "gray"} textTransform="none">
          {policy.policyType}
        </Badge>
      </Box>
      <Box>
        <FieldLabel variant="metric">Scope</FieldLabel>
        <Text fontSize="sm" mt={1.5}>
          {policy.scope}
        </Text>
      </Box>
      <Box flex="1" minW="200px">
        <FieldLabel variant="metric">PII Types</FieldLabel>
        <Flex wrap="wrap" gap={1} mt={1.5}>
          {policy.typeIds.map((id) => {
            const t = types.find((x) => x.id === id);
            return t ? (
              <Badge key={id} colorScheme="blue" textTransform="none">
                {t.name}
              </Badge>
            ) : null;
          })}
        </Flex>
      </Box>
    </Flex>
  );
}

function PayloadCard({ title, text }: { title: string; text: string }) {
  return (
    <Box flex="1" borderWidth="1px" borderColor="ink.200" borderRadius="md" p={4}>
      <Text fontSize="sm" fontWeight="semibold" mb={2}>
        {title}
      </Text>
      <Box bg="ink.50" borderRadius="md" p={3} fontFamily="mono" fontSize="sm" whiteSpace="pre-wrap">
        {text}
      </Box>
    </Box>
  );
}

export function InstitutionCatalog() {
  const {
    policies,
    institutionId,
    subscriptions,
    catalogScope,
    setCatalogScope,
    openDrawer,
    toggleSubscription,
  } = usePiiPolicies();
  const { sub, parentActive } = useParentActive();
  const active = policies.filter((p) => policyEffective(p, parentActive) === "Active");
  const visible =
    catalogScope === "subscribed"
      ? active.filter(
          (p) =>
            p.policyType === "Institution level" &&
            (subscriptions[p.policyId] ?? []).includes(institutionId),
        )
      : active;

  const catalogSortAccessors = useMemo(
    () => ({
      name: (row: Policy) => row.name,
      types: (row: Policy) => row.typeIds.length,
      languages: (row: Policy) => row.languages.join(", "),
    }),
    [],
  );
  const catalogSort = useDeferredColumnSort("name", catalogSortAccessors);
  const sortedVisible = useMemo(() => catalogSort.apply(visible), [catalogSort, visible]);

  const columns = useMemo<DataTableColumn<Policy>[]>(
    () => [
      {
        id: "policyId",
        header: "Policy ID",
        cell: (row) => (
          <Badge fontFamily="mono" textTransform="none">
            {row.policyId}
          </Badge>
        ),
      },
      {
        id: "name",
        header: "Policy Name",
        sortable: true,
        sortAccessor: (row) => row.name,
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium">
            {row.name}
          </Text>
        ),
      },
      {
        id: "types",
        header: "PII Types",
        sortable: true,
        sortAccessor: (row) => row.typeIds.length,
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.typeIds.length}
          </Text>
        ),
      },
      {
        id: "languages",
        header: "Languages",
        sortable: true,
        sortAccessor: (row) => row.languages.join(", "),
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {row.languages.join(", ")}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (row) => {
          const subscribed = (subscriptions[row.policyId] ?? []).includes(institutionId);
          const applied = subscribed || row.policyType === "Global";
          return (
            <Badge colorScheme={applied ? "green" : "gray"} textTransform="none">
              {row.policyType === "Global" ? "Always applied" : subscribed ? "Subscribed" : "Not subscribed"}
            </Badge>
          );
        },
      },
      {
        id: "actions",
        header: "Actions",
        truncate: false,
        cell: (row) => {
          const subscribed = (subscriptions[row.policyId] ?? []).includes(institutionId);
          return (
            <HStack>
              <DataTableActions
                actions={[
                  {
                    id: "view",
                    label: "View",
                    onClick: () => openDrawer({ kind: "view-policy", id: row.id }),
                  },
                ]}
              />
              {row.policyType === "Global" ? null : (
                <Button
                  size="xs"
                  variant={subscribed ? "outline" : "solid"}
                  onClick={() => toggleSubscription(row.policyId, institutionId)}
                >
                  {subscribed ? "Unsubscribe" : "Subscribe"}
                </Button>
              )}
            </HStack>
          );
        },
      },
    ],
    [subscriptions, institutionId, openDrawer, toggleSubscription],
  );

  return (
    <Box>
      {!parentActive ? (
        <LockedNotice>
          "{sub?.name}" (or its category) is currently disabled — no policies are being enforced.
        </LockedNotice>
      ) : null}
      <DataTable
        layout="admin"
        items={sortedVisible}
        columns={columns}
        getRowKey={(row) => row.id}
        sort={catalogSort.sort}
        onSortChange={catalogSort.onSortChange}
        paginate="client"
        paginationPosition="bottom"
        unfilteredCount={active.length}
        hasActiveFilters={catalogScope === "subscribed"}
        onClearFilters={() => setCatalogScope("all")}
        emptyMessage="No policies to show."
        noResultsMessage="No subscriptions to show."
        filterDefs={[
          {
            id: "scope",
            label: "Show",
            type: "select",
            value: catalogScope,
            onChange: (value) => setCatalogScope(value === "subscribed" ? "subscribed" : "all"),
            width: "180px",
            options: [
              { value: "all", label: "All policies" },
              { value: "subscribed", label: "My subscriptions" },
            ],
          },
        ]}
      />
    </Box>
  );
}
