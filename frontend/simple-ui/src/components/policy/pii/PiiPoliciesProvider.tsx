import React, { createContext, useContext, useMemo, useRef, useState } from "react";
import { showToast } from "../../../utils/toast";
import type { DetectionResult } from "./detection";
import {
  createInitialCatalog,
  nextPolicyCode,
  type Domain,
  type Handling,
  type MaskingPattern,
  type DetectionMode,
  type PiiType,
  type Policy,
  type PolicyCategory,
  type PolicyScope,
  type PolicySubcategory,
  type PolicyType,
  type PortalRole,
  type RecordStatus,
} from "./model";

export type PolicyView =
  | { kind: "home" }
  | { kind: "category"; categoryId: string }
  | { kind: "sub"; subcategoryId: string };

export type PiiTab = "policies" | "configuration" | "playground";
export type ConfigTab = "types" | "domain";
export type CatalogScope = "all" | "subscribed";
export type ProcessingTarget = "response" | "storage";

export interface TypeInput {
  name: string;
  examples: string[];
  handling: Handling;
  maskingPattern: MaskingPattern | null;
  detectionMode: DetectionMode;
  regex: string;
  nerModel: string;
}

export interface PolicyInput {
  name: string;
  description: string;
  domainIds: string[];
  languages: string[];
  typeIds: string[];
  policyType: PolicyType;
  scope: PolicyScope;
}

export type DrawerState =
  | { kind: "none" }
  | { kind: "add-type" }
  | { kind: "edit-type"; id: string }
  | { kind: "view-type"; id: string }
  | { kind: "add-category" }
  | { kind: "add-subcategory"; categoryId: string }
  | { kind: "add-domain" }
  | { kind: "edit-domain"; id: string }
  | { kind: "create-policy" }
  | { kind: "edit-policy"; id: string }
  | { kind: "view-policy"; id: string };

export interface ConfirmState {
  title: string;
  body: string;
  confirmLabel: string;
  confirmColorScheme: string;
  onConfirm: () => void;
}

interface PiiPoliciesContextValue {
  domains: Domain[];
  types: PiiType[];
  policies: Policy[];
  categories: PolicyCategory[];
  subcategories: PolicySubcategory[];
  subscriptions: Record<string, string[]>;
  role: PortalRole;
  institutionId: string;
  view: PolicyView;
  openHome: () => void;
  openCategory: (categoryId: string) => void;
  openSubcategory: (subcategoryId: string) => void;
  tab: PiiTab;
  setTab: (tab: PiiTab) => void;
  configTab: ConfigTab;
  setConfigTab: (tab: ConfigTab) => void;
  catalogScope: CatalogScope;
  setCatalogScope: (scope: CatalogScope) => void;
  policySearch: string;
  setPolicySearch: (value: string) => void;
  policyDomainFilter: string;
  setPolicyDomainFilter: (value: string) => void;
  typeSearch: string;
  setTypeSearch: (value: string) => void;
  typeHandlingFilter: string;
  setTypeHandlingFilter: (value: string) => void;
  domainSearch: string;
  setDomainSearch: (value: string) => void;
  playgroundPolicyId: string;
  playgroundTarget: ProcessingTarget;
  playgroundInput: string;
  playgroundResult: DetectionResult | null;
  setPlaygroundPolicy: (policyId: string, sample: string) => void;
  setPlaygroundTarget: (target: ProcessingTarget) => void;
  setPlaygroundInput: (value: string) => void;
  setPlaygroundResult: (result: DetectionResult | null) => void;
  loadPlaygroundSample: (sample: string) => void;
  drawer: DrawerState;
  openDrawer: (drawer: Exclude<DrawerState, { kind: "none" }>) => void;
  closeDrawer: () => void;
  confirm: ConfirmState | null;
  askConfirm: (confirm: ConfirmState) => void;
  closeConfirm: () => void;
  addCategory: (name: string, description: string) => string | null;
  addSubcategory: (categoryId: string, name: string, description: string) => string | null;
  toggleCategory: (id: string) => void;
  toggleSubcategory: (id: string) => void;
  addDomain: (name: string, description: string) => string | null;
  updateDomain: (id: string, name: string, description: string) => string | null;
  deleteDomain: (id: string) => void;
  addType: (input: TypeInput) => string | null;
  updateType: (id: string, input: TypeInput) => string | null;
  deleteType: (id: string) => void;
  addPolicy: (input: PolicyInput) => string | null;
  updatePolicy: (id: string, input: PolicyInput) => string | null;
  deletePolicy: (id: string) => void;
  setPolicyStatus: (id: string, status: RecordStatus) => void;
  toggleSubscription: (policyId: string, institutionId: string) => void;
}

const PiiPoliciesContext = createContext<PiiPoliciesContextValue | null>(null);

function duplicateName(items: { name: string; id?: string }[], name: string, ignoreId?: string) {
  return items.some(
    (item) => item.id !== ignoreId && item.name.toLowerCase() === name.toLowerCase(),
  );
}

export function PiiPoliciesProvider({
  role,
  institutionId,
  children,
}: {
  role: PortalRole;
  institutionId: string;
  children: React.ReactNode;
}) {
  const initial = useMemo(() => createInitialCatalog(), []);
  const idRef = useRef(1000);
  const nextId = (prefix: string) => `${prefix}-${idRef.current++}`;

  const [domains, setDomains] = useState(initial.domains);
  const [types, setTypes] = useState(initial.types);
  const [policies, setPolicies] = useState(initial.policies);
  const [categories, setCategories] = useState(initial.categories);
  const [subcategories, setSubcategories] = useState(initial.subcategories);
  const [subscriptions, setSubscriptions] = useState(initial.subscriptions);

  const [view, setView] = useState<PolicyView>({ kind: "home" });
  const [tab, setTab] = useState<PiiTab>("policies");
  const [configTab, setConfigTab] = useState<ConfigTab>("types");
  const [catalogScope, setCatalogScope] = useState<CatalogScope>("all");
  const [policySearch, setPolicySearch] = useState("");
  const [policyDomainFilter, setPolicyDomainFilter] = useState("");
  const [typeSearch, setTypeSearch] = useState("");
  const [typeHandlingFilter, setTypeHandlingFilter] = useState("");
  const [domainSearch, setDomainSearch] = useState("");
  const [playgroundPolicyId, setPlaygroundPolicyId] = useState("");
  const [playgroundTarget, setPlaygroundTargetState] = useState<ProcessingTarget>("response");
  const [playgroundInput, setPlaygroundInputState] = useState("");
  const [playgroundResult, setPlaygroundResult] = useState<DetectionResult | null>(null);
  const [drawer, setDrawer] = useState<DrawerState>({ kind: "none" });
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);

  const value = useMemo<PiiPoliciesContextValue>(() => {
    const toast = (message: string) => showToast({ type: "success", message, messageOnly: true });

    return {
      domains,
      types,
      policies,
      categories,
      subcategories,
      subscriptions,
      role,
      institutionId,
      view,
      openHome: () => setView({ kind: "home" }),
      openCategory: (categoryId) => setView({ kind: "category", categoryId }),
      openSubcategory: (subcategoryId) => {
        setTab("policies");
        setView({ kind: "sub", subcategoryId });
      },
      tab,
      setTab,
      configTab,
      setConfigTab,
      catalogScope,
      setCatalogScope,
      policySearch,
      setPolicySearch,
      policyDomainFilter,
      setPolicyDomainFilter,
      typeSearch,
      setTypeSearch,
      typeHandlingFilter,
      setTypeHandlingFilter,
      domainSearch,
      setDomainSearch,
      playgroundPolicyId,
      playgroundTarget,
      playgroundInput,
      playgroundResult,
      setPlaygroundPolicy: (policyId, sample) => {
        setPlaygroundPolicyId(policyId);
        setPlaygroundInputState(sample);
        setPlaygroundResult(null);
      },
      setPlaygroundTarget: (target) => {
        setPlaygroundTargetState(target);
        setPlaygroundResult(null);
      },
      setPlaygroundInput: (input) => {
        setPlaygroundInputState(input);
        setPlaygroundResult(null);
      },
      setPlaygroundResult,
      loadPlaygroundSample: (sample) => {
        setPlaygroundInputState(sample);
        setPlaygroundResult(null);
      },
      drawer,
      openDrawer: (next) => setDrawer(next),
      closeDrawer: () => setDrawer({ kind: "none" }),
      confirm,
      askConfirm: setConfirm,
      closeConfirm: () => setConfirm(null),
      addCategory: (name, description) => {
        if (duplicateName(categories, name)) return "A category with this name already exists.";
        const id = nextId("cat");
        setCategories((prev) => [...prev, { id, name, description, status: "Active" }]);
        setView({ kind: "category", categoryId: id });
        toast("Category added.");
        return null;
      },
      addSubcategory: (categoryId, name, description) => {
        const id = nextId("sub");
        setSubcategories((prev) => [
          ...prev,
          { id, categoryId, name, description, status: "Active" },
        ]);
        toast("Sub-category added.");
        return null;
      },
      toggleCategory: (id) => {
        setCategories((prev) =>
          prev.map((c) =>
            c.id === id ? { ...c, status: c.status === "Active" ? "Inactive" : "Active" } : c,
          ),
        );
        const current = categories.find((c) => c.id === id);
        toast(current?.status === "Active" ? "Category deactivated." : "Category activated.");
      },
      toggleSubcategory: (id) => {
        setSubcategories((prev) =>
          prev.map((s) =>
            s.id === id ? { ...s, status: s.status === "Active" ? "Inactive" : "Active" } : s,
          ),
        );
        const current = subcategories.find((s) => s.id === id);
        toast(
          current?.status === "Active" ? "Sub-category deactivated." : "Sub-category activated.",
        );
      },
      addDomain: (name, description) => {
        if (duplicateName(domains, name)) return "A domain with this name already exists.";
        setDomains((prev) => [...prev, { id: nextId("dom"), name, description, isDefault: false }]);
        toast("Domain created.");
        return null;
      },
      updateDomain: (id, name, description) => {
        if (duplicateName(domains, name, id)) return "A domain with this name already exists.";
        setDomains((prev) =>
          prev.map((d) =>
            d.id === id ? { ...d, name: d.isDefault ? d.name : name, description } : d,
          ),
        );
        toast("Domain updated.");
        return null;
      },
      deleteDomain: (id) => {
        setDomains((prev) => prev.filter((d) => d.id !== id));
        toast("Domain deleted.");
      },
      addType: (input) => {
        if (duplicateName(types, input.name)) return "A PII type with this name already exists.";
        setTypes((prev) => [
          ...prev,
          {
            id: nextId("pii"),
            domainId: null,
            isDefault: false,
            ...input,
            examples: [...input.examples],
          },
        ]);
        toast("PII type added.");
        return null;
      },
      updateType: (id, input) => {
        const current = types.find((t) => t.id === id);
        if (!current) return "PII type not found.";
        if (!current.isDefault && duplicateName(types, input.name, id)) {
          return "A PII type with this name already exists.";
        }
        setTypes((prev) =>
          prev.map((t) =>
            t.id === id
              ? {
                  ...t,
                  ...input,
                  name: t.isDefault ? t.name : input.name,
                  examples: [...input.examples],
                }
              : t,
          ),
        );
        toast("PII type updated.");
        return null;
      },
      deleteType: (id) => {
        setTypes((prev) => prev.filter((t) => t.id !== id));
        toast("PII type deleted.");
      },
      addPolicy: (input) => {
        if (duplicateName(policies, input.name)) return "A policy with this name already exists.";
        const policyId = nextPolicyCode(policies);
        setPolicies((prev) => [
          ...prev,
          {
            id: nextId("policy"),
            policyId,
            status: "Active",
            ...input,
            domainIds: [...input.domainIds],
            languages: [...input.languages],
            typeIds: [...input.typeIds],
          },
        ]);
        toast("Policy created.");
        return null;
      },
      updatePolicy: (id, input) => {
        if (duplicateName(policies, input.name, id)) return "A policy with this name already exists.";
        setPolicies((prev) =>
          prev.map((p) =>
            p.id === id
              ? {
                  ...p,
                  ...input,
                  domainIds: [...input.domainIds],
                  languages: [...input.languages],
                  typeIds: [...input.typeIds],
                }
              : p,
          ),
        );
        toast("Policy updated.");
        return null;
      },
      deletePolicy: (id) => {
        setPolicies((prev) => prev.filter((p) => p.id !== id));
        toast("Policy deleted.");
      },
      setPolicyStatus: (id, status) => {
        setPolicies((prev) => prev.map((p) => (p.id === id ? { ...p, status } : p)));
        toast(status === "Active" ? "Policy activated." : "Policy deactivated.");
      },
      toggleSubscription: (policyId, instId) => {
        setSubscriptions((prev) => {
          const list = prev[policyId] ? [...prev[policyId]] : [];
          const idx = list.indexOf(instId);
          if (idx >= 0) list.splice(idx, 1);
          else list.push(instId);
          return { ...prev, [policyId]: list };
        });
        const subscribed = (subscriptions[policyId] ?? []).includes(instId);
        toast(subscribed ? `Unsubscribed from ${policyId}.` : `Subscribed to ${policyId}.`);
      },
    };
  }, [
    domains,
    types,
    policies,
    categories,
    subcategories,
    subscriptions,
    role,
    institutionId,
    view,
    tab,
    configTab,
    catalogScope,
    policySearch,
    policyDomainFilter,
    typeSearch,
    typeHandlingFilter,
    domainSearch,
    playgroundPolicyId,
    playgroundTarget,
    playgroundInput,
    playgroundResult,
    drawer,
    confirm,
  ]);

  return <PiiPoliciesContext.Provider value={value}>{children}</PiiPoliciesContext.Provider>;
}

export function usePiiPolicies() {
  const ctx = useContext(PiiPoliciesContext);
  if (!ctx) throw new Error("usePiiPolicies must be used within PiiPoliciesProvider");
  return ctx;
}
