import { ChevronDownIcon, ChevronRightIcon, ChevronUpIcon, DeleteIcon, EditIcon } from "@chakra-ui/icons";
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
import { FiDatabase, FiFileText, FiFolder, FiLayers, FiList, FiSettings, FiShield, FiUsers } from "react-icons/fi";
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
import { HierarchyDetail, HierarchyNameForm } from "./hierarchyForms";
import { ConfigurationPanel, PlaygroundPanel, PolicyList } from "./panels";
import {
  PiiPoliciesProvider,
  usePiiPolicies,
  type ConfirmState,
  type PiiTab,
} from "./PiiPoliciesProvider";
import { FlaskIcon, POLICY_COL_ACTIONS, POLICY_COL_STATUS, StatusToggle } from "./ui";

const ADOPTER_TABS: { id: PiiTab; label: string }[] = [
  { id: "policies", label: "Policies" },
  { id: "categories", label: "Categories" },
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
        ...POLICY_COL_STATUS,
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
  onView,
  onEdit,
  onDelete,
}: {
  category: PolicyCategory;
  subcategories: PolicySubcategory[];
  policiesBySubcategory: Map<string, Policy[]>;
  onView: (sub: PolicySubcategory) => void;
  onEdit: (sub: PolicySubcategory) => void;
  onDelete: (sub: PolicySubcategory) => Promise<boolean>;
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
            <IconButton
              aria-label={expanded.has(sub.id) ? `Hide policies in ${sub.name}` : `Show policies in ${sub.name}`}
              aria-expanded={expanded.has(sub.id)}
              icon={
                <ChevronRightIcon
                  boxSize={4}
                  transform={expanded.has(sub.id) ? "rotate(90deg)" : undefined}
                  transition="transform 0.15s"
                />
              }
              size="xs"
              variant="ghost"
              color="ink.500"
              onClick={(event) => {
                event.stopPropagation();
                toggle(sub.id);
              }}
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
        ...POLICY_COL_STATUS,
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
        ...POLICY_COL_ACTIONS,
        width: "188px",
        minWidth: "188px",
        getActions: (sub) => [
          ...(canManage
            ? [
                { id: "edit" as const, label: "Edit", icon: <EditIcon />, onClick: () => onEdit(sub) },
                {
                  id: "delete" as const,
                  label: "Delete",
                  onClick: () =>
                    askConfirm({
                      title: `Delete "${sub.name}"?`,
                      body: "This permanently deletes the sub-category. Delete its policies first.",
                      confirmLabel: "Delete",
                      confirmColorScheme: "red",
                      onConfirm: () => {
                        void onDelete(sub);
                      },
                    }),
                },
              ]
            : []),
          {
            id: "view-policies",
            label: "View policies",
            icon: <Icon as={FiList} boxSize={3.5} />,
            onClick: () => showSubcategoryPolicies(sub.id),
          },
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
      onEdit,
      onDelete,
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
      onRowClick={onView}
      rowAriaLabel={(sub) => `View ${sub.name}`}
      showRowChevron={false}
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
  const {
    categories,
    subcategories,
    policies,
    role,
    createSubCategory,
    updateCategory,
    updateSubCategory,
    deleteCategory,
    deleteSubCategory,
    askConfirm,
    setCategoryStatus,
    showCategoryPolicies,
    showSubcategoryPolicies,
  } = usePiiPolicies();
  const canManage = role === "adopter";
  const [subcategoryFormFor, setSubcategoryFormFor] = useState<PolicyCategory | null>(null);
  const [viewCategory, setViewCategory] = useState<PolicyCategory | null>(null);
  const [editCategory, setEditCategory] = useState<PolicyCategory | null>(null);
  const [viewSubcategory, setViewSubcategory] = useState<PolicySubcategory | null>(null);
  const [editSubcategory, setEditSubcategory] = useState<PolicySubcategory | null>(null);
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

  const viewedCategory = viewCategory ? categories.find((c) => c.id === viewCategory.id) ?? viewCategory : null;
  const viewedSubcategory = viewSubcategory
    ? subcategories.find((s) => s.id === viewSubcategory.id) ?? viewSubcategory
    : null;
  const viewedSubParent = viewedSubcategory
    ? categories.find((c) => c.id === viewedSubcategory.categoryId)
    : undefined;

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
            <Flex align="center" gap={4} px={5} py={4}>
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
              <Box
                flex="1"
                minW={0}
                cursor="pointer"
                onClick={() => setViewCategory(cat)}
                role="button"
                tabIndex={0}
                aria-label={`View ${cat.name}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setViewCategory(cat);
                  }
                }}
              >
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
              <HStack spacing={3} flexShrink={0}>
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
                {canManage ? (
                  <CreateButton size="xs" onClick={() => setSubcategoryFormFor(cat)}>
                    Add sub-category
                  </CreateButton>
                ) : null}
                {canManage ? (
                  <IconButton
                    aria-label={`Edit ${cat.name}`}
                    icon={<EditIcon />}
                    size="sm"
                    variant="ghost"
                    color="ink.600"
                    onClick={() => setEditCategory(cat)}
                  />
                ) : null}
                {canManage ? (
                  <IconButton
                    aria-label={`Delete ${cat.name}`}
                    icon={<DeleteIcon />}
                    size="sm"
                    variant="ghost"
                    color="ink.600"
                    _hover={{ color: "red.500", bg: "red.50" }}
                    onClick={() =>
                      askConfirm({
                        title: `Delete "${cat.name}"?`,
                        body: "This permanently deletes the category. Delete its sub-categories first.",
                        confirmLabel: "Delete",
                        confirmColorScheme: "red",
                        onConfirm: () => {
                          void deleteCategory(cat.id).then((deleted) => {
                            if (!deleted) return;
                            setViewCategory((current) => (current?.id === cat.id ? null : current));
                            setEditCategory((current) => (current?.id === cat.id ? null : current));
                            setViewSubcategory((current) =>
                              current?.categoryId === cat.id ? null : current,
                            );
                            setEditSubcategory((current) =>
                              current?.categoryId === cat.id ? null : current,
                            );
                            setSubcategoryFormFor((current) => (current?.id === cat.id ? null : current));
                          });
                        },
                      })
                    }
                  />
                ) : null}
                <IconButton
                  aria-label={isOpen ? `Collapse ${cat.name}` : `Expand ${cat.name}`}
                  aria-expanded={isOpen}
                  icon={isOpen ? <ChevronUpIcon boxSize={5} /> : <ChevronDownIcon boxSize={5} />}
                  size="sm"
                  variant="ghost"
                  color="ink.500"
                  onClick={() => toggleExpanded(cat.id)}
                />
              </HStack>
            </Flex>
            <Collapse in={isOpen} animateOpacity unmountOnExit>
              <Stack spacing={3} px={5} pb={5}>
                <SubcategoryTable
                  category={cat}
                  subcategories={children}
                  policiesBySubcategory={policiesBySubcategory}
                  onView={setViewSubcategory}
                  onEdit={setEditSubcategory}
                  onDelete={async (sub) => {
                    const deleted = await deleteSubCategory(sub.id);
                    if (!deleted) return false;
                    setViewSubcategory((current) => (current?.id === sub.id ? null : current));
                    setEditSubcategory((current) => (current?.id === sub.id ? null : current));
                    return true;
                  }}
                />
              </Stack>
            </Collapse>
          </Box>
        );
      })}

      {viewedCategory ? (
        <HierarchyDetail
          title={`View ${viewedCategory.name}`}
          rows={[
            { label: "Name", value: viewedCategory.name },
            { label: "Description", value: viewedCategory.description || "—" },
            {
              label: "Status",
              value: <StatusBadge status={categoryEffective(viewedCategory)} />,
            },
            {
              label: "Sub-categories",
              value: String(subcategories.filter((s) => s.categoryId === viewedCategory.id).length),
            },
          ]}
          onClose={() => setViewCategory(null)}
          onEdit={
            canManage
              ? () => {
                  setViewCategory(null);
                  setEditCategory(viewedCategory);
                }
              : undefined
          }
          onViewPolicies={() => {
            setViewCategory(null);
            showCategoryPolicies(viewedCategory.id);
          }}
        />
      ) : null}

      {viewedSubcategory ? (
        <HierarchyDetail
          title={`View ${viewedSubcategory.name}`}
          rows={[
            { label: "Name", value: viewedSubcategory.name },
            { label: "Description", value: viewedSubcategory.description || "—" },
            { label: "Category", value: viewedSubParent?.name || "—" },
            {
              label: "Status",
              value: <StatusBadge status={subcategoryEffective(viewedSubcategory, categories)} />,
            },
            {
              label: "Policies",
              value: String(policiesBySubcategory.get(viewedSubcategory.id)?.length ?? 0),
            },
          ]}
          onClose={() => setViewSubcategory(null)}
          onEdit={
            canManage
              ? () => {
                  setViewSubcategory(null);
                  setEditSubcategory(viewedSubcategory);
                }
              : undefined
          }
          onViewPolicies={() => {
            setViewSubcategory(null);
            showSubcategoryPolicies(viewedSubcategory.id);
          }}
        />
      ) : null}

      {editCategory ? (
        <HierarchyNameForm
          key={`edit-category-${editCategory.id}`}
          title={`Edit ${editCategory.name}`}
          submitLabel="Save"
          namePlaceholder="e.g. Service Routing"
          descriptionPlaceholder="What kind of policies live under this category?"
          initialName={editCategory.name}
          initialDescription={editCategory.description}
          onClose={() => setEditCategory(null)}
          onSave={(name, description) => updateCategory(editCategory.id, name, description)}
        />
      ) : null}

      {editSubcategory ? (
        <HierarchyNameForm
          key={`edit-subcategory-${editSubcategory.id}`}
          title={`Edit ${editSubcategory.name}`}
          submitLabel="Save"
          namePlaceholder="e.g. Rate Limiting"
          descriptionPlaceholder="What does this sub-category cover?"
          initialName={editSubcategory.name}
          initialDescription={editSubcategory.description}
          onClose={() => setEditSubcategory(null)}
          onSave={(name, description) => updateSubCategory(editSubcategory.id, name, description)}
        />
      ) : null}

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
    configTab,
    confirm,
    closeConfirm,
    createCategory,
    openDrawer,
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
  const headerAction = (() => {
    if (!canManage || hierarchyStatus !== "ready") return undefined;
    if (tab === "policies") {
      return <CreateButton onClick={() => openDrawer({ kind: "create-policy" })}>Create Policy</CreateButton>;
    }
    if (tab === "categories") {
      return <CreateButton onClick={() => setCategoryFormOpen(true)}>Add category</CreateButton>;
    }
    if (tab === "configuration" && configTab === "types") {
      return <CreateButton onClick={() => openDrawer({ kind: "add-type" })}>Add Policy Type</CreateButton>;
    }
    if (tab === "configuration" && configTab === "domain") {
      return <CreateButton onClick={() => openDrawer({ kind: "add-domain" })}>Create Domain</CreateButton>;
    }
    return undefined;
  })();

  return (
    <Box>
      <ManagementPageHeader
        title="Policy Management"
        description={
          canManage
            ? "Manage policy categories, sub-categories, and the policies under them."
            : "View the policies configured under every category."
        }
        actions={headerAction}
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
                <PolicyList />
              </TabPanel>
              <TabPanel px={0} pt={6}>
                <CategoriesPanel
                  search={categorySearch}
                  statusFilter={categoryStatusFilter}
                  onClearFilters={clearCategoryFilters}
                />
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
