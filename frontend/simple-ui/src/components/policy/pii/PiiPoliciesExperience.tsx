import { Alert, AlertIcon, Box, Button, Center, Tab, TabList, TabPanel, TabPanels, Tabs, Text } from "@chakra-ui/react";
import React, { useEffect, useState } from "react";
import ConfirmDialog from "../../common/ConfirmDialog";
import LoadingSpinner from "../../common/LoadingSpinner";
import ManagementPageHeader from "../../common/ManagementPageHeader";
import type { Crumb } from "../../common/PageBreadcrumb";
import {
  categoryEffective,
  isPiiGuardrailsSubcategory,
  subcategoryEffective,
  type PortalRole,
} from "./model";
import { PiiDrawers } from "./drawers";
import { HierarchyNameForm } from "./hierarchyForms";
import { ConfigurationPanel, InstitutionCatalog, PlaygroundPanel, PolicyList } from "./panels";
import {
  PiiPoliciesProvider,
  usePiiPolicies,
  type ConfirmState,
  type PiiTab,
} from "./PiiPoliciesProvider";
import { AddCard, CardGrid, NavCard } from "./ui";

const TABS: { id: PiiTab; label: string }[] = [
  { id: "policies", label: "Policies" },
  { id: "configuration", label: "Configuration" },
  { id: "playground", label: "Playground" },
];

function crumbClick(navigate: () => void) {
  return (event: React.MouseEvent) => {
    event.preventDefault();
    navigate();
  };
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

function ExperienceBody() {
  const store = usePiiPolicies();
  const {
    categories,
    subcategories,
    hierarchyStatus,
    hierarchyError,
    reloadHierarchy,
    role,
    view,
    openHome,
    openCategory,
    openSubcategory,
    tab,
    setTab,
    confirm,
    closeConfirm,
    createCategory,
    createSubCategory,
    askConfirm,
    setCategoryStatus,
    setSubcategoryStatus,
  } = store;
  const [categoryFormOpen, setCategoryFormOpen] = useState(false);
  const [subcategoryFormOpen, setSubcategoryFormOpen] = useState(false);
  const viewKey =
    view.kind === "home"
      ? "home"
      : view.kind === "category"
        ? view.categoryId
        : view.subcategoryId;

  useEffect(() => {
    setCategoryFormOpen(false);
    setSubcategoryFormOpen(false);
  }, [viewKey]);

  const category = view.kind === "category" ? categories.find((c) => c.id === view.categoryId) : undefined;
  const sub = view.kind === "sub" ? subcategories.find((s) => s.id === view.subcategoryId) : undefined;
  const parent = sub ? categories.find((c) => c.id === sub.categoryId) : undefined;
  const isPii = sub ? isPiiGuardrailsSubcategory(sub) : false;
  const canManage = role === "adopter";

  let title = "Policies";
  let subtitle = "Browse policy categories across AI4I Orchestrate.";
  if (category) {
    title = category.name;
    subtitle = category.description;
  } else if (sub && parent) {
    title = sub.name;
    subtitle = isPii
      ? role === "institution"
        ? "Browse available PII policies and subscribe the ones your institution needs"
        : "Detect and sanitize PII in requests, responses, and storage using policy-specific configuration"
      : sub.description;
  }

  const crumbs: Crumb[] | false =
    view.kind === "home"
      ? false
      : category
        ? [
            { label: "Policies", href: "/policy-management", onClick: crumbClick(openHome) },
            { label: category.name },
          ]
        : sub && parent
          ? [
              { label: "Policies", href: "/policy-management", onClick: crumbClick(openHome) },
              {
                label: parent.name,
                href: "/policy-management",
                onClick: crumbClick(() => openCategory(parent.id)),
              },
              { label: sub.name },
            ]
          : false;

  return (
    <Box>
      <ManagementPageHeader
        title={title}
        description={subtitle}
        crumbs={crumbs}
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

      {hierarchyStatus === "ready" && view.kind === "home" ? (
        categories.length === 0 && !canManage ? (
          <Text fontSize="sm" color="ink.500">
            No categories yet.
          </Text>
        ) : (
          <CardGrid>
            {categories.map((cat) => {
              const count = subcategories.filter((s) => s.categoryId === cat.id).length;
              return (
                <NavCard
                  key={cat.id}
                  icon="shield"
                  title={cat.name}
                  description={cat.description || "No description"}
                  meta={`${count} sub-categor${count === 1 ? "y" : "ies"}`}
                  status={cat.status}
                  effective={categoryEffective(cat)}
                  onOpen={() => openCategory(cat.id)}
                  onToggle={
                    canManage
                      ? () =>
                          requestStatus(
                            askConfirm,
                            cat.name,
                            cat.status === "Active",
                            "Activating this category makes its sub-categories available. Continue?",
                            "Deactivating this category disables every sub-category under it. Continue?",
                            () =>
                              setCategoryStatus(
                                cat.id,
                                cat.status === "Active" ? "Inactive" : "Active",
                              ),
                          )
                      : undefined
                  }
                />
              );
            })}
            {canManage ? (
              <AddCard label="Add Category" onClick={() => setCategoryFormOpen(true)} />
            ) : null}
          </CardGrid>
        )
      ) : null}

      {hierarchyStatus === "ready" && category ? (
        subcategories.every((s) => s.categoryId !== category.id) && !canManage ? (
          <Text fontSize="sm" color="ink.500">
            No sub-categories yet.
          </Text>
        ) : (
        <CardGrid>
          {subcategories
            .filter((s) => s.categoryId === category.id)
            .map((s) => {
              const parentOff = category.status !== "Active";
              return (
                <NavCard
                  key={s.id}
                  icon={isPiiGuardrailsSubcategory(s) ? "shield" : "flask"}
                  title={s.name}
                  description={s.description || "No description"}
                  status={s.status}
                  effective={subcategoryEffective(s, categories)}
                  locked={parentOff}
                  lockedNote={`Disabled — "${category.name}" is inactive`}
                  onOpen={() => openSubcategory(s.id)}
                  onToggle={
                    canManage
                      ? () =>
                          requestStatus(
                            askConfirm,
                            s.name,
                            s.status === "Active",
                            "Activating this sub-category makes its policies available. Continue?",
                            "Deactivating this sub-category disables the policies under it. Continue?",
                            () =>
                              setSubcategoryStatus(
                                s.id,
                                s.status === "Active" ? "Inactive" : "Active",
                              ),
                          )
                      : undefined
                  }
                />
              );
            })}
          {canManage ? (
            <AddCard label="Add Sub-category" onClick={() => setSubcategoryFormOpen(true)} />
          ) : null}
        </CardGrid>
        )
      ) : null}

      {sub && !isPii ? (
        <Text fontSize="sm" color="ink.500">
          Nothing configured here yet. {sub.description}
        </Text>
      ) : null}

      {sub && isPii && canManage ? (
        <Tabs
          variant="enclosed"
          colorScheme="blue"
          index={Math.max(0, TABS.findIndex((item) => item.id === tab))}
          onChange={(index) => {
            const next = TABS[index];
            if (next) setTab(next.id);
          }}
        >
          <TabList>
            {TABS.map((item) => (
              <Tab key={item.id} fontWeight="semibold">
                {item.label}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
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
        </Tabs>
      ) : null}

      {sub && isPii && role === "institution" ? <InstitutionCatalog /> : null}

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
      {subcategoryFormOpen && category ? (
        <HierarchyNameForm
          title="Add Sub-category"
          submitLabel="Add Sub-category"
          namePlaceholder="e.g. Rate Limiting"
          descriptionPlaceholder="What does this sub-category cover?"
          onClose={() => setSubcategoryFormOpen(false)}
          onSave={(name, description) => createSubCategory(category.id, name, description)}
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
