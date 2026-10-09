import { Box, Tab, TabList, TabPanel, TabPanels, Tabs, Text } from "@chakra-ui/react";
import React from "react";
import ConfirmDialog from "../../common/ConfirmDialog";
import ManagementPageHeader from "../../common/ManagementPageHeader";
import type { Crumb } from "../../common/PageBreadcrumb";
import {
  PII_SUBCATEGORY_ID,
  categoryEffective,
  subcategoryEffective,
  type PortalRole,
} from "./model";
import { PiiDrawers } from "./drawers";
import { ConfigurationPanel, InstitutionCatalog, PlaygroundPanel, PolicyList } from "./panels";
import { PiiPoliciesProvider, usePiiPolicies, type PiiTab } from "./PiiPoliciesProvider";
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

function ExperienceBody() {
  const store = usePiiPolicies();
  const {
    categories,
    subcategories,
    role,
    view,
    openHome,
    openCategory,
    openSubcategory,
    tab,
    setTab,
    openDrawer,
    toggleCategory,
    toggleSubcategory,
    confirm,
    closeConfirm,
  } = store;

  const category = view.kind === "category" ? categories.find((c) => c.id === view.categoryId) : undefined;
  const sub = view.kind === "sub" ? subcategories.find((s) => s.id === view.subcategoryId) : undefined;
  const parent = sub ? categories.find((c) => c.id === sub.categoryId) : undefined;
  const isPii = sub?.id === PII_SUBCATEGORY_ID;
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

      {view.kind === "home" ? (
        <CardGrid>
          {categories.map((cat) => {
            const count = subcategories.filter((s) => s.categoryId === cat.id).length;
            return (
              <NavCard
                key={cat.id}
                icon="shield"
                title={cat.name}
                description={cat.description}
                meta={`${count} sub-categor${count === 1 ? "y" : "ies"}`}
                status={cat.status}
                effective={categoryEffective(cat)}
                onOpen={() => openCategory(cat.id)}
                onToggle={canManage ? () => toggleCategory(cat.id) : undefined}
              />
            );
          })}
          {canManage ? <AddCard label="Add Category" onClick={() => openDrawer({ kind: "add-category" })} /> : null}
        </CardGrid>
      ) : null}

      {category ? (
        <CardGrid>
          {subcategories
            .filter((s) => s.categoryId === category.id)
            .map((s) => {
              const parentOff = category.status !== "Active";
              return (
                <NavCard
                  key={s.id}
                  icon={s.id === PII_SUBCATEGORY_ID ? "shield" : "flask"}
                  title={s.name}
                  description={s.description}
                  status={s.status}
                  effective={subcategoryEffective(s, categories)}
                  locked={parentOff}
                  lockedNote={`Disabled — "${category.name}" is inactive`}
                  onOpen={() => openSubcategory(s.id)}
                  onToggle={canManage ? () => toggleSubcategory(s.id) : undefined}
                />
              );
            })}
          {canManage ? (
            <AddCard
              label="Add Sub-category"
              onClick={() => openDrawer({ kind: "add-subcategory", categoryId: category.id })}
            />
          ) : null}
        </CardGrid>
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
