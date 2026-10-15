import { ChevronDownIcon, ChevronRightIcon, ChevronUpIcon } from "@chakra-ui/icons";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Center,
  Collapse,
  Flex,
  HStack,
  Icon,
  IconButton,
  Stack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Td,
  Text,
  Tr,
} from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import type { IconType } from "react-icons";
import { FiDatabase, FiFileText, FiFolder, FiLayers, FiSettings, FiShield, FiUsers } from "react-icons/fi";
import ConfirmDialog from "../../common/ConfirmDialog";
import CreateButton from "../../common/CreateButton";
import LoadingSpinner from "../../common/LoadingSpinner";
import ManagementPageHeader from "../../common/ManagementPageHeader";
import DataTable, {
  TableSearchField,
  TableSelectField,
  createActionsColumn,
  type DataTableColumn,
} from "../../common/table";
import { TableFilterToolbar } from "../../common/TableControls";
import {
  categoryEffective,
  isPiiGuardrailsSubcategory,
  policyEffective,
  policyParentActive,
  subcategoryEffective,
  type Policy,
  type PolicyCategory,
  type PolicySubcategory,
  type PortalRole,
  type RecordStatus,
} from "./model";
import { PiiDrawers } from "./drawers";
import { HierarchyNameForm } from "./hierarchyForms";
import { ConfigurationPanel, PlaygroundPanel, PolicyList } from "./panels";
import {
  PiiPoliciesProvider,
  usePiiPolicies,
  type ConfirmState,
  type PiiTab,
} from "./PiiPoliciesProvider";
import { FlaskIcon, StatusToggle } from "./ui";

const ADOPTER_TABS: { id: PiiTab; label: string }[] = [
  { id: "categories", label: "Categories" },
  { id: "policies", label: "Policies" },
  { id: "configuration", label: "Configuration" },
  { id: "playground", label: "Playground" },
];

const INSTITUTION_TABS: { id: PiiTab; label: string }[] = [{ id: "policies", label: "Policies" }];

type StatusFilter = "all" | RecordStatus;

/** Category marks cycle through these in list order. */
const CATEGORY_MARKS: { icon: IconType; bg: string; color: string }[] = [
  { icon: FiShield, bg: "blue.50", color: "blue.600" },
  { icon: FiFolder, bg: "purple.50", color: "purple.600" },
  { icon: FiUsers, bg: "orange.50", color: "orange.600" },
  { icon: FiSettings, bg: "green.50", color: "green.600" },
  { icon: FiFileText, bg: "red.50", color: "red.500" },
  { icon: FiDatabase, bg: "teal.50", color: "teal.600" },
  { icon: FiLayers, bg: "pink.50", color: "pink.500" },
];

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function requestStatus(
  askConfirm: (confirm: ConfirmState) => void,
  name: string,
  active: boolean,
  activateBody: string,
  deactivateBody: string,
  onConfirm: () => void,
) {
  const nextActive = !active;
  askConfirm({
    title: `${nextActive ? "Activate" : "Deactivate"} "${name}"?`,
    body: nextActive ? activateBody : deactivateBody,
    confirmLabel: nextActive ? "Activate" : "Deactivate",
    confirmColorScheme: nextActive ? "blue" : "red",
    onConfirm,
  });
}

function StatusBadge({ status }: { status: RecordStatus }) {
  return (
    <Badge colorScheme={status === "Active" ? "green" : "gray"} textTransform="none">
      {status}
    </Badge>
  );
}

function CategoriesToolbar({
  search,
  onSearch,
  statusFilter,
  onStatusFilter,
  onClear,
}: {
  search: string;
  onSearch: (value: string) => void;
  statusFilter: StatusFilter;
  onStatusFilter: (value: StatusFilter) => void;
  onClear: () => void;
}) {
  return (
    <Box pb={2}>
      <TableFilterToolbar
        hasActiveFilters={Boolean(search) || statusFilter !== "all"}
        onClear={onClear}
        alignActionsToInputs={false}
        align="center"
      >
        <TableSearchField
          label="Search categories"
          hideLabel
          value={search}
          onChange={onSearch}
          placeholder="Search categories..."
          formControlProps={{ w: { base: "full", md: "240px" } }}
        />
        <TableSelectField
          label="Status"
          hideLabel
          value={statusFilter}
          onChange={(value) => onStatusFilter(value as StatusFilter)}
          formControlProps={{ w: "140px" }}
        >
          <option value="all">All statuses</option>
          <option value="Active">Active</option>
          <option value="Inactive">Inactive</option>
        </TableSelectField>
      </TableFilterToolbar>
    </Box>
  );
}

function SubcategoryPolicies({ policies }: { policies: Policy[] }) {
  const { categories, subcategories, openDrawer } = usePiiPolicies();
  const columns = useMemo<DataTableColumn<Policy>[]>(
    () => [
      {
        id: "policyId",
        header: "Policy ID",
        width: "160px",
        cell: (row) => (
          <Badge fontFamily="mono" textTransform="none">
            {row.policyId}
          </Badge>
        ),
      },
      {
        id: "name",
        header: "Policy Name",
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium" color="ink.800">
            {row.name}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        width: "120px",
        cell: (row) => (
          <StatusBadge status={policyEffective(row, policyParentActive(row, subcategories, categories))} />
        ),
      },
    ],
    [categories, subcategories],
  );

  return (
    <DataTable
      variant="compact"
      columns={columns}
      rows={policies}
      rowKey={(row) => row.id}
      sortable={false}
      isEmpty={policies.length === 0}
      emptyMessage="No policies in this sub-category yet."
      asyncStateHeight="48px"
      onRowClick={(row) => openDrawer({ kind: "view-policy", id: row.id })}
      rowAriaLabel={(row) => `View ${row.name}`}
      showRowChevron
    />
  );
}

function SubcategoryTable({
  category,
  subcategories,
  policiesBySubcategory,
}: {
  category: PolicyCategory;
  subcategories: PolicySubcategory[];
  policiesBySubcategory: Map<string, Policy[]>;
}) {
  const { categories, role, askConfirm, setSubcategoryStatus, showSubcategoryPolicies } = usePiiPolicies();
  const canManage = role === "adopter";
  const categoryInactive = categoryEffective(category) === "Inactive";
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const columns = useMemo<DataTableColumn<PolicySubcategory>[]>(
    () => [
      {
        id: "name",
        header: `Sub-categories (${subcategories.length})`,
        cell: (sub) => (
          <HStack spacing={3} minW={0}>
            <ChevronRightIcon
              boxSize={4}
              color="ink.500"
              transform={expanded.has(sub.id) ? "rotate(90deg)" : undefined}
              transition="transform 0.15s"
            />
            <Flex
              w={8}
              h={8}
              borderRadius="md"
              bg="blue.50"
              color="blue.600"
              align="center"
              justify="center"
              flexShrink={0}
            >
              {isPiiGuardrailsSubcategory(sub) ? <Icon as={FiFileText} boxSize={3.5} /> : <FlaskIcon boxSize={3.5} />}
            </Flex>
            <Box minW={0}>
              <Text fontSize="sm" fontWeight="semibold" color="ink.800" noOfLines={1}>
                {sub.name}
              </Text>
              <Text fontSize="xs" color="ink.500" noOfLines={1}>
                {sub.description || "No description"}
              </Text>
            </Box>
          </HStack>
        ),
      },
      {
        id: "policies",
        header: "Policies",
        width: "110px",
        align: "center",
        cell: (sub) => (
          <Text fontSize="sm" color="ink.700">
            {policiesBySubcategory.get(sub.id)?.length ?? 0}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        width: "140px",
        cell: (sub) =>
          canManage ? (
            <StatusToggle
              status={sub.status}
              effective={subcategoryEffective(sub, categories)}
              locked={categoryInactive}
              label={
                categoryInactive
                  ? `${sub.name} status, locked because ${category.name} is inactive`
                  : `${sub.name} status`
              }
              onToggle={() =>
                requestStatus(
                  askConfirm,
                  sub.name,
                  sub.status === "Active",
                  "Activating this sub-category makes its policies available. Continue?",
                  "Deactivating this sub-category disables the policies under it. Continue?",
                  () => setSubcategoryStatus(sub.id, sub.status === "Active" ? "Inactive" : "Active"),
                )
              }
            />
          ) : (
            <StatusBadge status={subcategoryEffective(sub, categories)} />
          ),
      },
      createActionsColumn<PolicySubcategory>({
        width: "100px",
        minWidth: "100px",
        align: "center",
        getActions: (sub) => [
          { id: "view", label: "View policies", onClick: () => showSubcategoryPolicies(sub.id) },
        ],
      }),
    ],
    [
      subcategories.length,
      expanded,
      policiesBySubcategory,
      canManage,
      categories,
      categoryInactive,
      category.name,
      askConfirm,
      setSubcategoryStatus,
      showSubcategoryPolicies,
    ],
  );

  return (
    <DataTable
      variant="compact"
      columns={columns}
      rows={subcategories}
      rowKey={(sub) => sub.id}
      sortable={false}
      isEmpty={subcategories.length === 0}
      emptyMessage="No sub-categories yet."
      asyncStateHeight="64px"
      onRowClick={(sub) => toggle(sub.id)}
      rowAriaLabel={(sub) => `${expanded.has(sub.id) ? "Hide" : "Show"} policies in ${sub.name}`}
      renderAfterRow={(sub) =>
        expanded.has(sub.id) ? (
          <Tr>
            <Td colSpan={columns.length} bg="ink.50" px={4} py={3}>
              <SubcategoryPolicies policies={policiesBySubcategory.get(sub.id) ?? []} />
            </Td>
          </Tr>
        ) : null
      }
    />
  );
}

function CategoriesPanel({
  search,
  statusFilter,
  onClearFilters,
}: {
  search: string;
  statusFilter: StatusFilter;
  onClearFilters: () => void;
}) {
  const { categories, subcategories, policies, role, createSubCategory, askConfirm, setCategoryStatus } =
    usePiiPolicies();
  const canManage = role === "adopter";
  const [subcategoryFormFor, setSubcategoryFormFor] = useState<PolicyCategory | null>(null);
  // The first category starts open, as in the reference layout.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(categories[0] ? [categories[0].id] : []));

  const policiesBySubcategory = useMemo(() => {
    const groups = new Map<string, Policy[]>();
    policies.forEach((p) => groups.set(p.subcategoryId, [...(groups.get(p.subcategoryId) ?? []), p]));
    return groups;
  }, [policies]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return categories.filter((cat) => {
      if (statusFilter !== "all" && categoryEffective(cat) !== statusFilter) return false;
      if (!query) return true;
      if (`${cat.name} ${cat.description}`.toLowerCase().includes(query)) return true;
      return subcategories.some((s) => s.categoryId === cat.id && s.name.toLowerCase().includes(query));
    });
  }, [categories, subcategories, search, statusFilter]);

  const toggleExpanded = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (categories.length === 0) {
    return (
      <Text fontSize="sm" color="ink.500">
        No categories yet.
      </Text>
    );
  }

  if (visible.length === 0) {
    return (
      <Flex direction="column" align="center" py={10} gap={2}>
        <Text fontSize="sm" color="ink.500">
          No categories match your search or filter.
        </Text>
        <Button size="sm" variant="link" colorScheme="blue" onClick={onClearFilters}>
          Clear filters
        </Button>
      </Flex>
    );
  }

  return (
    <Stack spacing={3}>
      {visible.map((cat) => {
        const index = categories.findIndex((c) => c.id === cat.id);
        const mark = CATEGORY_MARKS[index % CATEGORY_MARKS.length];
        const children = subcategories.filter((s) => s.categoryId === cat.id);
        const total = children.reduce((sum, s) => sum + (policiesBySubcategory.get(s.id)?.length ?? 0), 0);
        const isOpen = expanded.has(cat.id);
        return (
          <Box
            key={cat.id}
            as="section"
            aria-label={cat.name}
            bg="white"
            borderWidth="1px"
            borderColor="ink.200"
            borderRadius="14px"
          >
            <Flex
              align="center"
              gap={4}
              px={5}
              py={4}
              cursor="pointer"
              onClick={() => toggleExpanded(cat.id)}
            >
              <Flex
                w={10}
                h={10}
                borderRadius="lg"
                bg={mark.bg}
                color={mark.color}
                align="center"
                justify="center"
                flexShrink={0}
              >
                <Icon as={mark.icon} boxSize={4} />
              </Flex>
              <Box flex="1" minW={0}>
                <Text fontSize="md" fontWeight="semibold" color="ink.800">
                  {cat.name}
                </Text>
                <Text fontSize="xs" color="ink.500" noOfLines={1}>
                  {cat.description || "No description"}
                </Text>
                <HStack spacing={2} mt={1} fontSize="xs" color="ink.500">
                  <Text>{plural(children.length, "sub-category", "sub-categories")}</Text>
                  <Text color="ink.300">|</Text>
                  <Text>{plural(total, "policy", "policies")}</Text>
                </HStack>
              </Box>
              <HStack spacing={4} flexShrink={0}>
                {canManage ? (
                  <StatusToggle
                    status={cat.status}
                    effective={categoryEffective(cat)}
                    label={`${cat.name} status`}
                    onToggle={() =>
                      requestStatus(
                        askConfirm,
                        cat.name,
                        cat.status === "Active",
                        "Activating this category makes its sub-categories available. Continue?",
                        "Deactivating this category disables every sub-category under it. Continue?",
                        () => setCategoryStatus(cat.id, cat.status === "Active" ? "Inactive" : "Active"),
                      )
                    }
                  />
                ) : (
                  <StatusBadge status={categoryEffective(cat)} />
                )}
                <IconButton
                  aria-label={isOpen ? `Collapse ${cat.name}` : `Expand ${cat.name}`}
                  aria-expanded={isOpen}
                  icon={isOpen ? <ChevronUpIcon boxSize={5} /> : <ChevronDownIcon boxSize={5} />}
                  size="sm"
                  variant="ghost"
                  color="ink.500"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpanded(cat.id);
                  }}
                />
              </HStack>
            </Flex>
            <Collapse in={isOpen} animateOpacity unmountOnExit>
              <Stack spacing={3} px={5} pb={5}>
                {canManage ? (
                  <Flex justify="flex-end">
                    <CreateButton onClick={() => setSubcategoryFormFor(cat)}>
                      Add sub-category
                    </CreateButton>
                  </Flex>
                ) : null}
                <SubcategoryTable
                  category={cat}
                  subcategories={children}
                  policiesBySubcategory={policiesBySubcategory}
                />
              </Stack>
            </Collapse>
          </Box>
        );
      })}

      {subcategoryFormFor ? (
        <HierarchyNameForm
          title={`Add Sub-category to ${subcategoryFormFor.name}`}
          submitLabel="Add Sub-category"
          namePlaceholder="e.g. Rate Limiting"
          descriptionPlaceholder="What does this sub-category cover?"
          onClose={() => setSubcategoryFormFor(null)}
          onSave={(name, description) => createSubCategory(subcategoryFormFor.id, name, description)}
        />
      ) : null}
    </Stack>
  );
}

function ExperienceBody() {
  const {
    hierarchyStatus,
    hierarchyError,
    reloadHierarchy,
    role,
    tab,
    setTab,
    confirm,
    closeConfirm,
    createCategory,
  } = usePiiPolicies();
  const canManage = role === "adopter";
  const tabs = canManage ? ADOPTER_TABS : INSTITUTION_TABS;
  const [categoryFormOpen, setCategoryFormOpen] = useState(false);
  const [categorySearch, setCategorySearch] = useState("");
  const [categoryStatusFilter, setCategoryStatusFilter] = useState<StatusFilter>("all");
  const onCategories = canManage && tab === "categories" && hierarchyStatus === "ready";
  const clearCategoryFilters = () => {
    setCategorySearch("");
    setCategoryStatusFilter("all");
  };

  return (
    <Box>
      <ManagementPageHeader
        title="Policy Management"
        description={
          canManage
            ? "Manage policy categories, sub-categories, and the policies under them."
            : "View the policies configured under every category."
        }
        actions={
          onCategories ? (
            <CreateButton onClick={() => setCategoryFormOpen(true)}>Add category</CreateButton>
          ) : undefined
        }
      />

      {hierarchyStatus === "loading" ? (
        <Center py={16}>
          <LoadingSpinner label="Loading categories…" />
        </Center>
      ) : null}

      {hierarchyStatus === "error" ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          <Text flex="1" fontSize="sm">
            {hierarchyError}
          </Text>
          <Button size="sm" variant="outline" onClick={reloadHierarchy}>
            Try again
          </Button>
        </Alert>
      ) : null}

      {hierarchyStatus === "ready" ? (
        <Tabs
          variant="line"
          colorScheme="blue"
          index={Math.max(0, tabs.findIndex((item) => item.id === tab))}
          onChange={(index) => {
            const next = tabs[index];
            if (next) setTab(next.id);
          }}
        >
          <Flex
            align="flex-end"
            justify="space-between"
            wrap="wrap"
            gap={2}
            borderBottomWidth="1px"
            borderColor="ink.200"
          >
            <TabList borderBottom="none" mb="-1px">
              {tabs.map((item) => (
                <Tab key={item.id} fontWeight="semibold">
                  {item.label}
                </Tab>
              ))}
            </TabList>
            {onCategories ? (
              <CategoriesToolbar
                search={categorySearch}
                onSearch={setCategorySearch}
                statusFilter={categoryStatusFilter}
                onStatusFilter={setCategoryStatusFilter}
                onClear={clearCategoryFilters}
              />
            ) : null}
          </Flex>
          {canManage ? (
            <TabPanels>
              <TabPanel px={0} pt={6}>
                <CategoriesPanel
                  search={categorySearch}
                  statusFilter={categoryStatusFilter}
                  onClearFilters={clearCategoryFilters}
                />
              </TabPanel>
              <TabPanel px={0} pt={6}>
                <PolicyList />
              </TabPanel>
              <TabPanel px={0} pt={6}>
                <ConfigurationPanel />
              </TabPanel>
              <TabPanel px={0} pt={6}>
                <PlaygroundPanel />
              </TabPanel>
            </TabPanels>
          ) : (
            <TabPanels>
              <TabPanel px={0} pt={6}>
                <PolicyList />
              </TabPanel>
            </TabPanels>
          )}
        </Tabs>
      ) : null}

      {categoryFormOpen ? (
        <HierarchyNameForm
          title="Add Category"
          submitLabel="Add Category"
          namePlaceholder="e.g. Service Routing"
          descriptionPlaceholder="What kind of policies live under this category?"
          onClose={() => setCategoryFormOpen(false)}
          onSave={createCategory}
        />
      ) : null}
      <PiiDrawers />
      <ConfirmDialog
        isOpen={Boolean(confirm)}
        onClose={closeConfirm}
        onConfirm={() => {
          confirm?.onConfirm();
          closeConfirm();
        }}
        title={confirm?.title ?? ""}
        body={confirm?.body ?? ""}
        confirmLabel={confirm?.confirmLabel}
        confirmColorScheme={confirm?.confirmColorScheme}
        isCentered
      />
    </Box>
  );
}

export default function PiiPoliciesExperience({
  role,
  institutionId,
}: {
  role: PortalRole;
  institutionId: string;
}) {
  return (
    <PiiPoliciesProvider role={role} institutionId={institutionId}>
      <ExperienceBody />
    </PiiPoliciesProvider>
  );
}
