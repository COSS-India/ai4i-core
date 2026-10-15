import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Center,
  Flex,
  HStack,
  Select,
  Stack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Textarea,
} from "@chakra-ui/react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import CreateButton from "../../common/CreateButton";
import FormActions from "../../common/FormActions";
import FormDrawer from "../../common/FormDrawer";
import ReadOnlyField from "../../common/ReadOnlyField";
import LoadingSpinner from "../../common/LoadingSpinner";
import FieldLabel from "../../common/FieldLabel";
import DataTable, {
  createActionsColumn,
  type DataTableColumn,
} from "../../common/table";
import { entityNamesForPolicy } from "./apiMap";
import {
  buildSample,
  PLAYGROUND_SIMULATION_HELP,
  simulationRows,
  type SimulationRow,
} from "./detection";
import { useDeferredColumnSort } from "../../../utils/tableSort";
import { showToast } from "../../../utils/toast";
import {
  DEFAULT_POLICY_LANGUAGES,
  domainLabel,
  filterPolicies,
  isFieldShown,
  languageLabel,
  policyEffective,
  policyParentActive,
  subcategoriesForCategory,
  subcategoryAfterCategoryChange,
  type PiiType,
  type Policy,
  type PolicyField,
} from "./model";
import { loadModelEntities } from "./modelEntities";
import { usePiiPolicies } from "./PiiPoliciesProvider";
import { sharedTypes } from "./policyCustomFields";
import { StatusToggle } from "./ui";

/** Whether a policy's sub-category and category are both active. */
function useParentActive() {
  const { categories, subcategories } = usePiiPolicies();
  return useCallback(
    (policy: Policy) => policyParentActive(policy, subcategories, categories),
    [categories, subcategories],
  );
}

/** Category and sub-category names for a policy row. */
function useHierarchyNames() {
  const { categories, subcategories } = usePiiPolicies();
  return useMemo(() => {
    const subById = new Map(subcategories.map((s) => [s.id, s]));
    const categoryById = new Map(categories.map((c) => [c.id, c]));
    return {
      subcategory: (policy: Policy) => subById.get(policy.subcategoryId)?.name ?? "",
      category: (policy: Policy) => {
        const sub = subById.get(policy.subcategoryId);
        return (sub && categoryById.get(sub.categoryId)?.name) || "";
      },
    };
  }, [categories, subcategories]);
}

export function PolicyList() {
  const store = usePiiPolicies();
  const {
    policies,
    domains,
    categories,
    subcategories,
    policySearch,
    setPolicySearch,
    policyDomainFilter,
    setPolicyDomainFilter,
    policyCategoryFilter,
    setPolicyCategoryFilter,
    policySubcategoryFilter,
    setPolicySubcategoryFilter,
    openDrawer,
    openPlayground,
    askConfirm,
    setPolicyStatus,
    deletePolicy,
    policiesStatus,
    policiesError,
    reloadPolicies,
    role,
  } = store;
  const canManage = role === "adopter";
  const parentActive = useParentActive();
  const names = useHierarchyNames();

  const rows = useMemo(
    () =>
      filterPolicies(
        policies,
        {
          search: policySearch,
          domainId: policyDomainFilter,
          categoryId: policyCategoryFilter,
          subcategoryId: policySubcategoryFilter,
        },
        subcategories,
      ),
    [policies, policySearch, policyDomainFilter, policyCategoryFilter, policySubcategoryFilter, subcategories],
  );

  const subcategoryOptions = useMemo(
    () => subcategoriesForCategory(subcategories, policyCategoryFilter),
    [subcategories, policyCategoryFilter],
  );

  const changeCategoryFilter = (categoryId: string) => {
    setPolicyCategoryFilter(categoryId);
    setPolicySubcategoryFilter(
      subcategoryAfterCategoryChange(subcategories, policySubcategoryFilter, categoryId),
    );
  };

  const policySortAccessors = useMemo(
    () => ({
      name: (row: Policy) => row.name,
      category: names.category,
      subcategory: names.subcategory,
      languages: (row: Policy) => row.languages.map(languageLabel).join(", "),
    }),
    [names],
  );
  const policySort = useDeferredColumnSort("name", policySortAccessors);
  const sortedPolicies = useMemo(() => policySort.apply(rows), [policySort, rows]);

  const requestStatus = useCallback(
    (policy: Policy, nextActive: boolean) => {
      askConfirm({
        title: `${nextActive ? "Activate" : "Deactivate"} "${policy.name}"?`,
        body: nextActive
          ? "Activating this policy makes it available to institutions and starts PII detection and sanitization. Continue?"
          : "Deactivating this policy will stop PII detection and sanitization for subscribed institutions. Continue?",
        confirmLabel: nextActive ? "Activate" : "Deactivate",
        confirmColorScheme: nextActive ? "blue" : "red",
        onConfirm: () => setPolicyStatus(policy.id, nextActive ? "Active" : "Inactive"),
      });
    },
    [askConfirm, setPolicyStatus],
  );

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
      ...(canManage
        ? [
            {
              id: "category",
              header: "Category",
              sortable: true,
              sortAccessor: names.category,
              cell: (row: Policy) => (
                <Text fontSize="sm" color="ink.500">
                  {names.category(row) || "—"}
                </Text>
              ),
            },
            {
              id: "subcategory",
              header: "Sub-category",
              sortable: true,
              sortAccessor: names.subcategory,
              cell: (row: Policy) => (
                <Text fontSize="sm" color="ink.500">
                  {names.subcategory(row) || "—"}
                </Text>
              ),
            },
          ]
        : []),
      {
        id: "domain",
        header: "Domain",
        cell: (row) => (
          <Badge textTransform="none">
            {row.domainIds.map((id) => domainLabel(id, domains)).filter(Boolean).join(", ") || "—"}
          </Badge>
        ),
      },
      {
        id: "languages",
        header: "Languages",
        sortable: true,
        sortAccessor: (row) => row.languages.map(languageLabel).join(", "),
        cell: (row) => (
          <Text fontSize="sm" color="ink.500">
            {DEFAULT_POLICY_LANGUAGES.map(languageLabel).join(", ")}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (row) => {
          if (!canManage) {
            return (
              <Badge colorScheme={row.status === "Active" ? "green" : "gray"} textTransform="none">
                {row.status}
              </Badge>
            );
          }
          const active = parentActive(row);
          return (
            <StatusToggle
              status={row.status}
              effective={policyEffective(row, active)}
              locked={!active}
              label={
                active
                  ? `${row.name} status`
                  : `${row.name} status, locked because its sub-category or category is inactive`
              }
              onToggle={() => requestStatus(row, row.status !== "Active")}
            />
          );
        },
      },
      createActionsColumn<Policy>({
        getActions: (row) => {
          const view = {
            id: "view",
            label: "View",
            onClick: () => openDrawer({ kind: "view-policy", id: row.id }),
          };
          if (!canManage) return [view];
          return [
            view,
            { id: "edit", label: "Edit", onClick: () => openDrawer({ kind: "edit-policy", id: row.id }) },
            { id: "test", label: "Test in Playground", onClick: () => openPlayground(row.policyId) },
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
          ];
        },
      }),
    ],
    [canManage, domains, names, parentActive, requestStatus, openDrawer, openPlayground, askConfirm, deletePolicy],
  );

  return (
    <Box>
      {canManage ? (
        <Flex justify="flex-end" mb={4}>
          <CreateButton onClick={() => openDrawer({ kind: "create-policy" })}>Create Policy</CreateButton>
        </Flex>
      ) : null}
      {policiesStatus === "error" ? (
        <Alert status="error" borderRadius="md" mb={4}>
          <AlertIcon />
          <Text flex="1" fontSize="sm">
            {policiesError}
          </Text>
          <Button size="sm" variant="outline" onClick={reloadPolicies}>
            Try again
          </Button>
        </Alert>
      ) : null}
      {policiesStatus === "loading" && policies.length === 0 ? (
        <Center py={10}>
          <LoadingSpinner label="Loading policies…" />
        </Center>
      ) : (
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
        hasActiveFilters={Boolean(
          policySearch || policyDomainFilter || policyCategoryFilter || policySubcategoryFilter,
        )}
        onClearFilters={() => {
          setPolicySearch("");
          setPolicyDomainFilter("");
          setPolicyCategoryFilter("");
          setPolicySubcategoryFilter("");
        }}
        emptyMessage="No policies yet."
        noResultsMessage="No policies match your search."
        onRowClick={(row) => openDrawer({ kind: "view-policy", id: row.id })}
        search={{
          value: policySearch,
          onChange: setPolicySearch,
          placeholder: "Search policies...",
          fields: ["name"],
        }}
        filterDefs={[
          ...(canManage
            ? [
                {
                  id: "category",
                  label: "Category",
                  type: "select" as const,
                  value: policyCategoryFilter,
                  onChange: changeCategoryFilter,
                  width: "180px",
                  options: [
                    { value: "", label: "All Categories" },
                    ...categories.map((c) => ({ value: c.id, label: c.name })),
                  ],
                },
                {
                  id: "subcategory",
                  label: "Sub-category",
                  type: "select" as const,
                  value: policySubcategoryFilter,
                  onChange: setPolicySubcategoryFilter,
                  width: "180px",
                  options: [
                    { value: "", label: "All Sub-categories" },
                    ...subcategoryOptions.map((s) => ({ value: s.id, label: s.name })),
                  ],
                },
              ]
            : []),
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
      )}
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

interface EntityRow {
  key: string;
  /** Unset for entities from GET /pii/entities, which belong to no policy type. */
  type?: PiiType;
  entityName: string;
  mode: PolicyField["mode"];
}

function entityRows(types: PiiType[]): EntityRow[] {
  return types.flatMap((type) => {
    const seen = new Set<string>();
    return type.fields.flatMap((field) => {
      const key = `${type.id}:${field.mode}:${field.entityName}`;
      if (!field.entityName || !isFieldShown(field) || seen.has(key)) return [];
      seen.add(key);
      return [{ key, type, entityName: field.entityName, mode: field.mode }];
    });
  });
}

function viewEntityDrawer(type: PiiType, row: EntityRow) {
  return {
    kind: "view-type" as const,
    id: type.id,
    entity: { name: row.entityName, mode: row.mode },
  };
}

function TypeLibrary() {
  const {
    types,
    typeSearch,
    setTypeSearch,
    openDrawer,
    askConfirm,
    deleteType,
    updateType,
    typesStatus,
    typesError,
    reloadTypes,
  } = usePiiPolicies();

  const [modelEntities, setModelEntities] = useState<string[]>([]);
  const [detail, setDetail] = useState<EntityRow | null>(null);
  useEffect(() => {
    let current = true;
    loadModelEntities("en").then(
      (entities) => {
        if (current) setModelEntities(entities);
      },
      () => {
        if (current) {
          showToast({ type: "error", message: "Couldn't load model supported PII types.", messageOnly: true });
        }
      },
    );
    return () => {
      current = false;
    };
  }, []);

  const allRows = useMemo(
    () => [
      ...modelEntities.map((entityName): EntityRow => ({ key: `en:${entityName}`, entityName, mode: "model" })),
      ...entityRows(sharedTypes(types)),
    ],
    [modelEntities, types],
  );
  const rows = useMemo(() => {
    const query = typeSearch.toLowerCase();
    if (!query) return allRows;
    return allRows.filter(
      (row) =>
        row.entityName.toLowerCase().includes(query) || Boolean(row.type?.name.toLowerCase().includes(query)),
    );
  }, [allRows, typeSearch]);

  const typeSortAccessors = useMemo(
    () => ({
      entity: (row: EntityRow) => row.entityName,
      group: (row: EntityRow) => row.type?.name ?? "",
      mode: (row: EntityRow) => row.mode,
    }),
    [],
  );
  const typeSort = useDeferredColumnSort("entity", typeSortAccessors);
  const sortedRows = useMemo(() => typeSort.apply(rows), [typeSort, rows]);
  // Only rows from a policy type have a group; GET /pii/entities rows have none.
  const hasGroups = allRows.some((row) => row.type);

  const columns = useMemo<DataTableColumn<EntityRow>[]>(() => {
    const removeEntity = async (type: PiiType, row: EntityRow) => {
      const remaining = type.fields.filter(
        (field) => !(field.entityName === row.entityName && field.mode === row.mode),
      );
      if (remaining.length === 0) {
        await deleteType(type.id);
        return;
      }
      const error = await updateType(type.id, { name: type.name, fields: remaining });
      if (error) showToast({ type: "error", message: error, messageOnly: true });
    };

    return [
      {
        id: "entity",
        header: "PII Type",
        sortable: true,
        sortAccessor: (row) => row.entityName,
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium">
            {row.entityName}
          </Text>
        ),
      },
      ...(hasGroups
        ? [
            {
              id: "group",
              header: "Group",
              sortable: true,
              sortAccessor: (row: EntityRow) => row.type?.name ?? "",
              cell: (row: EntityRow) => (
                <Text fontSize="sm" color="ink.500">
                  {row.type?.name ?? "—"}
                </Text>
              ),
            },
          ]
        : []),
      {
        id: "mode",
        header: "Mode",
        sortable: true,
        sortAccessor: (row) => row.mode,
        cell: (row) => (
          <Badge colorScheme={row.mode === "model" ? "purple" : "blue"} variant="subtle">
            {row.mode === "model" ? "Model" : "Custom"}
          </Badge>
        ),
      },
      createActionsColumn<EntityRow>({
        getActions: (row) => {
          const type = row.type;
          if (!type) return [{ id: "view", label: "View", onClick: () => setDetail(row) }];
          return [
            { id: "view", label: "View", onClick: () => openDrawer(viewEntityDrawer(type, row)) },
            { id: "edit", label: "Edit", onClick: () => openDrawer({ kind: "edit-type", id: type.id }) },
            {
              id: "delete",
              label: "Delete",
              onClick: () =>
                askConfirm({
                  title: `Delete ${row.entityName}?`,
                  body: type.fields.every(
                    (field) => field.entityName === row.entityName && field.mode === row.mode,
                  )
                      ? `${row.entityName} is the only PII type in ${type.name}, so the whole group will be deleted. This action cannot be undone.`
                      : `This removes ${row.entityName} from ${type.name}. Policies that picked it will no longer detect it. This action cannot be undone.`,
                  confirmLabel: "Delete",
                  confirmColorScheme: "red",
                  onConfirm: () => {
                    void removeEntity(type, row);
                  },
                }),
            },
          ];
        },
      }),
    ];
  }, [hasGroups, openDrawer, askConfirm, deleteType, updateType]);

  return (
    <Box>
      {typesStatus === "error" ? (
        <Alert status="error" borderRadius="md" mb={4}>
          <AlertIcon />
          <Text flex="1" fontSize="sm">
            {typesError}
          </Text>
          <Button size="sm" variant="outline" onClick={reloadTypes}>
            Try again
          </Button>
        </Alert>
      ) : null}
      {typesStatus === "loading" && types.length === 0 ? (
        <Center py={10}>
          <LoadingSpinner label="Loading policy types…" />
        </Center>
      ) : (
    <DataTable
      layout="admin"
      items={sortedRows}
      columns={columns}
      getRowKey={(row) => row.key}
      sort={typeSort.sort}
      onSortChange={typeSort.onSortChange}
      paginate="client"
      paginationPosition="bottom"
      unfilteredCount={allRows.length}
      hasActiveFilters={Boolean(typeSearch)}
      onClearFilters={() => {
        setTypeSearch("");
      }}
      emptyMessage="No PII types yet."
      noResultsMessage="No PII types match your search."
      onRowClick={(row) => {
        if (row.type) openDrawer(viewEntityDrawer(row.type, row));
        else setDetail(row);
      }}
      filterToolbarRightContent={
        <HStack spacing={2}>
          <Button
            size="sm"
            variant="outline"
            onClick={reloadTypes}
            isLoading={typesStatus === "loading"}
            loadingText="Refreshing"
          >
            Refresh
          </Button>
          <CreateButton onClick={() => openDrawer({ kind: "add-type" })}>Add Policy Type</CreateButton>
        </HStack>
      }
      search={{
        value: typeSearch,
        onChange: setTypeSearch,
        placeholder: "Search PII types...",
        fields: ["entityName", "type.name"],
      }}
    />
      )}
      {detail ? (
        <FormDrawer
          isOpen
          onClose={() => setDetail(null)}
          title="View PII Type"
          footer={<FormActions cancelLabel="Close" onCancel={() => setDetail(null)} hideSubmit />}
        >
          <Stack spacing={4}>
            <ReadOnlyField label="Entity Name">{detail.entityName}</ReadOnlyField>
            <ReadOnlyField label="Mode">Model-supported</ReadOnlyField>
            <ReadOnlyField label="Language">{languageLabel("en")}</ReadOnlyField>
          </Stack>
        </FormDrawer>
      ) : null}
    </Box>
  );
}

function DomainTable() {
  const {
    domains,
    domainsStatus,
    domainsError,
    reloadDomains,
    domainSearch,
    setDomainSearch,
    openDrawer,
  } = usePiiPolicies();
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
    ],
    [],
  );

  if (domainsStatus === "loading" && domains.length === 0) {
    return (
      <Center py={10}>
        <LoadingSpinner label="Loading domains…" />
      </Center>
    );
  }

  return (
    <Box>
      {domainsStatus === "error" ? (
        <Alert status="error" borderRadius="md" mb={4}>
          <AlertIcon />
          <Text flex="1" fontSize="sm">
            {domainsError}
          </Text>
          <Button size="sm" variant="outline" onClick={reloadDomains}>
            Try again
          </Button>
        </Alert>
      ) : null}
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
    </Box>
  );
}

export function PlaygroundPanel() {
  const {
    policies,
    types,
    domains,
    playgroundPolicyId,
    playgroundInput,
    playgroundResult,
    playgroundRunning,
    playgroundError,
    setPlaygroundPolicy,
    setPlaygroundInput,
    loadPlaygroundSample,
    runPlayground,
  } = usePiiPolicies();
  const parentActive = useParentActive();
  const selected = policies.find((p) => p.policyId === playgroundPolicyId) ?? null;
  const canRun = Boolean(selected && playgroundInput.trim());
  const resultRows = useMemo(
    () => simulationRows(playgroundResult?.detected ?? []),
    [playgroundResult],
  );
  const resultSortAccessors = useMemo(
    () => ({
      type: (row: SimulationRow) => row.entityType,
      instances: (row: SimulationRow) => row.instances,
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
              onChange={(e) => setPlaygroundPolicy(e.target.value)}
            >
              {policies.map((p) => (
                <option key={p.policyId} value={p.policyId}>
                  {p.policyId} · {p.name}
                  {policyEffective(p, parentActive(p)) === "Active" ? "" : " (Inactive)"}
                </option>
              ))}
            </Select>
          </Box>
        </Flex>
        <Text fontSize="xs" color="ink.500" mt={3}>
          {PLAYGROUND_SIMULATION_HELP}
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
              onClick={() => loadPlaygroundSample(buildSample(selected, types, domains))}
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
        <Button
          mt={3}
          size="sm"
          isDisabled={!canRun}
          isLoading={playgroundRunning}
          loadingText="Running…"
          onClick={() => void runPlayground()}
        >
          Run Simulation
        </Button>
      </Box>

      {playgroundError ? (
        <Alert status="error" borderRadius="md" mb={4}>
          <AlertIcon />
          <Text fontSize="sm">{playgroundError}</Text>
        </Alert>
      ) : null}

      {playgroundResult ? (
        <Box>
          <Text fontSize="sm" fontWeight="semibold" mb={3}>
            Detected PII in this request
          </Text>
          {playgroundResult.detected.length === 0 ? (
            <Alert status="info" borderRadius="md" mb={4}>
              <AlertIcon />
              <Text fontSize="sm">
                No PII found in this text for the definitions in {playgroundResult.policyId}.
              </Text>
            </Alert>
          ) : (
            <Box mb={4}>
              <DataTable
                layout="admin"
                items={sortedResults}
                getRowKey={(row) => row.entityType}
                sort={resultSort.sort}
                onSortChange={resultSort.onSortChange}
                paginate="client"
                paginationPosition="bottom"
                columns={[
                  {
                    id: "type",
                    header: "PII Definition",
                    sortable: true,
                    sortAccessor: (row) => row.entityType,
                    cell: (row) => row.entityType,
                  },
                  {
                    id: "found",
                    header: "Found",
                    cell: (row) => (
                      <Text fontFamily="mono" fontSize="xs">
                        {row.found.join(", ")}
                      </Text>
                    ),
                  },
                  {
                    id: "instances",
                    header: "Instances",
                    sortable: true,
                    sortAccessor: (row) => row.instances,
                    cell: (row) => row.instances,
                  },
                  {
                    id: "output",
                    header: "Output",
                    cell: (row) => (
                      <Text fontFamily="mono" fontSize="xs" color="ink.500">
                        {row.outputs.join(", ")}
                      </Text>
                    ),
                  },
                ]}
              />
            </Box>
          )}
          <Flex direction={{ base: "column", lg: "row" }} gap={4}>
            <PayloadCard title="Original Payload" text={playgroundResult.originalText} />
            <PayloadCard
              title="Sanitized Payload"
              text={playgroundResult.sanitizedText}
            />
          </Flex>
        </Box>
      ) : null}
    </Box>
  );
}

function SimplePolicySummary({ policy }: { policy: Policy }) {
  const { types, domains } = usePiiPolicies();
  const entityNames = entityNamesForPolicy(policy, types, domains);
  return (
    <Flex wrap="wrap" gap={4} borderTopWidth="1px" borderColor="ink.200" pt={3} mt={3}>
      <Box>
        <FieldLabel variant="metric">Scope</FieldLabel>
        <Text fontSize="sm" mt={1.5}>
          {policy.scope}
        </Text>
      </Box>
      <Box flex="1" minW="200px">
        <FieldLabel variant="metric">Entity Names</FieldLabel>
        <Flex wrap="wrap" gap={1} mt={1.5}>
          {(entityNames.length > 0
            ? entityNames
            : sharedTypes(types)
                .filter((type) => policy.typeIds.includes(type.id))
                .map((type) => type.name)
          ).map((name) => (
            <Badge key={name} colorScheme="blue" textTransform="none">
              {name}
            </Badge>
          ))}
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
