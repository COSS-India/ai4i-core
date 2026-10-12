import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  definitionFromPolicyType,
  domainNames,
  guardrailToApi,
  policyFieldsFromDefinition,
  policyFromRecord,
} from "./apiMap";
import {
  createPolicy,
  createPolicyCategory,
  createPolicySubCategory,
  createPolicyType,
  deletePolicy,
  deletePolicyType,
  listPolicies,
  listPolicyCategories,
  listPolicySubCategories,
  listPolicyTypes,
  updatePolicy,
  updatePolicyType,
} from "../../../services/policyHierarchyService";
import type {
  PolicyCategoryItem,
  PolicySubCategoryItem,
} from "../../../services/dto/schemas/policyHierarchy";
import { showToast } from "../../../utils/toast";
import type { DetectionResult } from "./detection";
import {
  createInitialCatalog,
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
  hierarchyStatus: "loading" | "ready" | "error";
  hierarchyError: string;
  reloadHierarchy: () => void;
  typesStatus: "loading" | "ready" | "error";
  typesError: string;
  reloadTypes: () => void;
  policiesStatus: "loading" | "ready" | "error";
  policiesError: string;
  reloadPolicies: () => void;
  /** Returns an error message, or null after the category is in the list. */
  createCategory: (name: string, description: string) => Promise<string | null>;
  /** Parent is the open category. Returns an error message, or null on success. */
  createSubCategory: (
    categoryId: string,
    name: string,
    description: string,
  ) => Promise<string | null>;
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
  addDomain: (name: string, description: string) => string | null;
  updateDomain: (id: string, name: string, description: string) => string | null;
  deleteDomain: (id: string) => void;
  addType: (input: TypeInput) => Promise<string | null>;
  updateType: (id: string, input: TypeInput) => Promise<string | null>;
  deleteType: (id: string) => Promise<void>;
  addPolicy: (input: PolicyInput) => Promise<string | null>;
  updatePolicy: (id: string, input: PolicyInput) => Promise<string | null>;
  deletePolicy: (id: string) => Promise<void>;
  setPolicyStatus: (id: string, status: RecordStatus) => Promise<void>;
  /** Local until the category status API exists. */
  setCategoryStatus: (id: string, status: RecordStatus) => void;
  /** Local until the sub-category status API exists. */
  setSubcategoryStatus: (id: string, status: RecordStatus) => void;
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
  const [types, setTypes] = useState<PiiType[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [categories, setCategories] = useState<PolicyCategory[]>([]);
  const [subcategories, setSubcategories] = useState<PolicySubcategory[]>([]);
  const [hierarchyStatus, setHierarchyStatus] = useState<"loading" | "ready" | "error">("loading");
  const [hierarchyError, setHierarchyError] = useState("");
  const [typesStatus, setTypesStatus] = useState<"loading" | "ready" | "error">("loading");
  const [typesError, setTypesError] = useState("");
  const [policiesStatus, setPoliciesStatus] = useState<"loading" | "ready" | "error">("loading");
  const [policiesError, setPoliciesError] = useState("");
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

  const hierarchyRequest = useRef(0);
  const reloadHierarchy = useCallback(() => {
    const requestId = ++hierarchyRequest.current;
    setHierarchyStatus("loading");
    setHierarchyError("");
    void Promise.all([listPolicyCategories(), listPolicySubCategories()])
      .then(([categoryItems, subcategoryItems]) => {
        if (requestId !== hierarchyRequest.current) return;
        setCategories(categoryItems.map(toCategory));
        setSubcategories(subcategoryItems.map(toSubcategory));
        setHierarchyStatus("ready");
      })
      .catch((error: unknown) => {
        if (requestId !== hierarchyRequest.current) return;
        setCategories([]);
        setSubcategories([]);
        setHierarchyError(apiErrorMessage(error));
        setHierarchyStatus("error");
      });
  }, []);

  const typesRequest = useRef(0);
  const reloadTypes = useCallback(() => {
    const requestId = ++typesRequest.current;
    setTypesStatus("loading");
    setTypesError("");
    void listPolicyTypes()
      .then((items) => {
        if (requestId !== typesRequest.current) return;
        setTypes(items.map(definitionFromPolicyType));
        setTypesStatus("ready");
      })
      .catch((error: unknown) => {
        if (requestId !== typesRequest.current) return;
        setTypes([]);
        setTypesError(apiErrorMessage(error, "Couldn't load PII definitions."));
        setTypesStatus("error");
      });
  }, []);

  const domainsRef = useRef(domains);
  domainsRef.current = domains;
  const policiesRequest = useRef(0);
  const reloadPolicies = useCallback(() => {
    const requestId = ++policiesRequest.current;
    setPoliciesStatus("loading");
    setPoliciesError("");
    void listPolicies()
      .then((items) => {
        if (requestId !== policiesRequest.current) return;
        setPolicies(items.map((item) => policyFromRecord(item, domainsRef.current)));
        setPoliciesStatus("ready");
      })
      .catch((error: unknown) => {
        if (requestId !== policiesRequest.current) return;
        setPolicies([]);
        setPoliciesError(apiErrorMessage(error, "Couldn't load policies."));
        setPoliciesStatus("error");
      });
  }, []);

  useEffect(() => {
    reloadHierarchy();
    return () => {
      hierarchyRequest.current += 1;
    };
  }, [reloadHierarchy]);

  useEffect(() => {
    reloadTypes();
    return () => {
      typesRequest.current += 1;
    };
  }, [reloadTypes]);

  useEffect(() => {
    reloadPolicies();
    return () => {
      policiesRequest.current += 1;
    };
  }, [reloadPolicies]);

  const value = useMemo<PiiPoliciesContextValue>(() => {
    const toast = (message: string) => showToast({ type: "success", message, messageOnly: true });

    return {
      domains,
      types,
      policies,
      categories,
      subcategories,
      hierarchyStatus,
      hierarchyError,
      reloadHierarchy,
      typesStatus,
      typesError,
      reloadTypes,
      policiesStatus,
      policiesError,
      reloadPolicies,
      createCategory: async (name, description) => {
        const trimmed = name.trim();
        if (!trimmed) return "Enter a name.";
        if (duplicateName(categories, trimmed)) {
          return "A category with this name already exists.";
        }
        try {
          const created = await createPolicyCategory({
            name: trimmed,
            description: blankToNull(description),
          });
          setCategories((prev) => appendById(prev, toCategory(created)));
          toast("Category created.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the category.");
        }
      },
      createSubCategory: async (categoryId, name, description) => {
        const trimmed = name.trim();
        if (!trimmed) return "Enter a name.";
        if (duplicateName(subcategories, trimmed)) {
          return "A sub-category with this name already exists.";
        }
        const parentId = Number(categoryId);
        if (!Number.isInteger(parentId) || parentId <= 0) {
          return "Couldn't create the sub-category.";
        }
        try {
          const created = await createPolicySubCategory({
            name: trimmed,
            description: blankToNull(description),
            category_id: parentId,
          });
          setSubcategories((prev) => appendById(prev, toSubcategory(created)));
          toast("Sub-category created.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the sub-category.");
        }
      },
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
      addType: async (input) => {
        if (duplicateName(types, input.name)) return "A PII type with this name already exists.";
        try {
          const saved = await createPolicyType({
            policy_type: input.name,
            policy_fields: policyFieldsFromDefinition(input),
          });
          setTypes((prev) => appendById(prev, definitionFromPolicyType(saved)));
          toast("PII type added.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the PII definition.");
        }
      },
      updateType: async (id, input) => {
        const current = types.find((t) => t.id === id);
        if (!current) return "PII type not found.";
        if (!current.isDefault && duplicateName(types, input.name, id)) {
          return "A PII type with this name already exists.";
        }
        const typeId = numericId(id);
        if (typeId == null) return "Couldn't update the PII definition.";
        try {
          const saved = await updatePolicyType(typeId, policyFieldsFromDefinition(input));
          const next = definitionFromPolicyType(saved);
          setTypes((prev) => prev.map((t) => (t.id === id ? next : t)));
          toast("PII type updated.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't update the PII definition.");
        }
      },
      deleteType: async (id) => {
        const typeId = numericId(id);
        if (typeId == null) {
          showToast({ type: "error", message: "Couldn't delete the PII definition.", messageOnly: true });
          return;
        }
        try {
          await deletePolicyType(typeId);
          setTypes((prev) => prev.filter((t) => t.id !== id));
          toast("PII type deleted.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't delete the PII definition."),
            messageOnly: true,
          });
        }
      },
      addPolicy: async (input) => {
        if (view.kind !== "sub") return "Open a sub-category before creating a policy.";
        if (duplicateName(policies, input.name)) return "A policy with this name already exists.";
        const subCategoryId = numericId(view.subcategoryId);
        const typeIds = numericIds(input.typeIds);
        if (subCategoryId == null || typeIds.length !== input.typeIds.length) {
          return "Couldn't create the policy.";
        }
        try {
          const saved = await createPolicy({
            name: input.name,
            description: blankToNull(input.description),
            domain: domainNames(input.domainIds, domains),
            guardrail_scope: guardrailToApi(input.scope),
            is_global: input.policyType === "Global",
            sub_category_id: subCategoryId,
            is_active: false,
            output_parse_pii: true,
            policy_type_id: typeIds,
          });
          setPolicies((prev) =>
            appendById(prev, {
              ...policyFromRecord(saved, domains),
              languages: [...input.languages],
            }),
          );
          setPoliciesStatus("ready");
          setPoliciesError("");
          toast("Policy created.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the policy.");
        }
      },
      updatePolicy: async (id, input) => {
        const current = policies.find((p) => p.id === id);
        if (!current) return "Policy not found.";
        if (duplicateName(policies, input.name, id)) return "A policy with this name already exists.";
        const policyId = numericId(id);
        const subCategoryId = numericId(current.subcategoryId);
        const typeIds = numericIds(input.typeIds);
        if (policyId == null || subCategoryId == null || typeIds.length !== input.typeIds.length) {
          return "Couldn't update the policy.";
        }
        try {
          const saved = await updatePolicy(policyId, {
            description: blankToNull(input.description),
            domain: domainNames(input.domainIds, domains),
            guardrail_scope: guardrailToApi(input.scope),
            is_global: input.policyType === "Global",
            sub_category_id: subCategoryId,
            policy_type_id: typeIds,
          });
          const next = { ...policyFromRecord(saved, domains), languages: input.languages };
          setPolicies((prev) => prev.map((p) => (p.id === id ? next : p)));
          toast("Policy updated.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't update the policy.");
        }
      },
      deletePolicy: async (id) => {
        const policyId = numericId(id);
        if (policyId == null) {
          showToast({ type: "error", message: "Couldn't delete the policy.", messageOnly: true });
          return;
        }
        try {
          await deletePolicy(policyId);
          setPolicies((prev) => prev.filter((p) => p.id !== id));
          toast("Policy deleted.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't delete the policy."),
            messageOnly: true,
          });
        }
      },
      setPolicyStatus: async (id, status) => {
        const policyId = numericId(id);
        if (policyId == null) {
          showToast({ type: "error", message: "Couldn't update the policy.", messageOnly: true });
          return;
        }
        try {
          const saved = await updatePolicy(policyId, { is_active: status === "Active" });
          const next = policyFromRecord(saved, domains);
          setPolicies((prev) =>
            prev.map((p) => (p.id === id ? { ...next, languages: p.languages } : p)),
          );
          toast(status === "Active" ? "Policy activated." : "Policy deactivated.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't update the policy."),
            messageOnly: true,
          });
        }
      },
      setCategoryStatus: (id, status) => {
        setCategories((prev) => prev.map((c) => (c.id === id ? { ...c, status } : c)));
        toast(status === "Active" ? "Category activated." : "Category deactivated.");
      },
      setSubcategoryStatus: (id, status) => {
        setSubcategories((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s)));
        toast(status === "Active" ? "Sub-category activated." : "Sub-category deactivated.");
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
    hierarchyStatus,
    hierarchyError,
    reloadHierarchy,
    typesStatus,
    typesError,
    reloadTypes,
    policiesStatus,
    policiesError,
    reloadPolicies,
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

function toCategory(item: PolicyCategoryItem): PolicyCategory {
  return {
    id: String(item.id),
    name: item.name,
    description: item.description?.trim() ?? "",
    status: item.is_active ? "Active" : "Inactive",
  };
}

function toSubcategory(item: PolicySubCategoryItem): PolicySubcategory {
  return {
    id: String(item.id),
    categoryId: String(item.category_id),
    name: item.name,
    description: item.description?.trim() ?? "",
    status: item.is_active ? "Active" : "Inactive",
  };
}

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function appendById<T extends { id: string }>(items: T[], next: T): T[] {
  if (items.some((item) => item.id === next.id)) return items;
  return [...items, next];
}

function numericId(id: string): number | null {
  const value = Number(id);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function numericIds(ids: string[]): number[] {
  return ids.flatMap((id) => {
    const value = numericId(id);
    return value == null ? [] : [value];
  });
}

function apiErrorMessage(error: unknown, fallback = "Couldn't load policy categories."): string {
  if (!error || typeof error !== "object") {
    return error instanceof Error && error.message ? error.message : fallback;
  }
  const data = (error as { response?: { data?: { detail?: unknown; message?: string } } }).response
    ?.data;
  const detail = data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const first = detail.find((item) => item && typeof item === "object" && "msg" in item) as
      | { msg?: unknown }
      | undefined;
    if (typeof first?.msg === "string" && first.msg.trim()) return first.msg;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  if (typeof data?.message === "string" && data.message.trim()) return data.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
