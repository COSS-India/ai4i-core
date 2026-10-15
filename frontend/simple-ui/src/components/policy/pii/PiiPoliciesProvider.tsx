import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { piiService } from "../../../services/piiService";
import {
  definitionFromPolicyType,
  policyCreatePayload,
  policyFieldsFromDefinition,
  policyFromRecord,
  policyUpdatePayload,
  selectionForField,
} from "./apiMap";
import { policyOwnedType, policyOwnedTypeName } from "./policyCustomFields";
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
  simulatePolicy,
  updatePolicy,
  updatePolicyCategoryStatus,
  updatePolicySubCategoryStatus,
  updatePolicyType,
} from "../../../services/policyHierarchyService";
import type {
  PolicyCategoryItem,
  PolicySimulation,
  PolicySubCategoryItem,
} from "../../../services/dto/schemas/policyHierarchy";
import { showToast } from "../../../utils/toast";
import {
  type Domain,
  type PiiType,
  type Policy,
  type PolicyCategory,
  type PolicyField,
  type PolicyInput,
  type PolicySubcategory,
  type PortalRole,
  type RecordStatus,
} from "./model";

export type { PolicyInput } from "./model";

export type PiiTab = "categories" | "policies" | "configuration" | "playground";
export type ConfigTab = "types" | "domain";
export type CatalogScope = "all" | "subscribed";
/** A simulation response plus the policy it was run with. */
export interface PlaygroundResult extends PolicySimulation {
  policyId: string;
}

export interface TypeInput {
  name: string;
  fields: PolicyField[];
}

export type DrawerState =
  | { kind: "none" }
  | { kind: "add-type" }
  | { kind: "edit-type"; id: string }
  | { kind: "view-type"; id: string; entity?: { name: string; mode: PolicyField["mode"] } }
  | { kind: "add-domain" }
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
  domainsStatus: "loading" | "ready" | "error";
  domainsError: string;
  reloadDomains: () => void;
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
  /** Returns an error message, or null on success. */
  createSubCategory: (
    categoryId: string,
    name: string,
    description: string,
  ) => Promise<string | null>;
  subscriptions: Record<string, string[]>;
  role: PortalRole;
  institutionId: string;
  /** Switches to the Policies tab filtered to this category. */
  showCategoryPolicies: (categoryId: string) => void;
  /** Switches to the Policies tab filtered to this sub-category and its category. */
  showSubcategoryPolicies: (subcategoryId: string) => void;
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
  policyCategoryFilter: string;
  setPolicyCategoryFilter: (value: string) => void;
  policySubcategoryFilter: string;
  setPolicySubcategoryFilter: (value: string) => void;
  typeSearch: string;
  setTypeSearch: (value: string) => void;
  domainSearch: string;
  setDomainSearch: (value: string) => void;
  playgroundPolicyId: string;
  playgroundInput: string;
  playgroundResult: PlaygroundResult | null;
  playgroundRunning: boolean;
  playgroundError: string;
  setPlaygroundPolicy: (policyId: string) => void;
  setPlaygroundInput: (value: string) => void;
  loadPlaygroundSample: (sample: string) => void;
  runPlayground: () => Promise<void>;
  /** Switches to the Playground tab with this policy selected. */
  openPlayground: (policyId: string) => void;
  drawer: DrawerState;
  openDrawer: (drawer: Exclude<DrawerState, { kind: "none" }>) => void;
  closeDrawer: () => void;
  confirm: ConfirmState | null;
  askConfirm: (confirm: ConfirmState) => void;
  closeConfirm: () => void;
  addDomain: (name: string, description: string) => Promise<string | null>;
  addType: (input: TypeInput) => Promise<string | null>;
  updateType: (id: string, input: TypeInput) => Promise<string | null>;
  deleteType: (id: string) => Promise<void>;
  addPolicy: (input: PolicyInput) => Promise<string | null>;
  updatePolicy: (id: string, input: PolicyInput) => Promise<string | null>;
  deletePolicy: (id: string) => Promise<void>;
  setPolicyStatus: (id: string, status: RecordStatus) => Promise<void>;
  setCategoryStatus: (id: string, status: RecordStatus) => Promise<void>;
  setSubcategoryStatus: (id: string, status: RecordStatus) => Promise<void>;
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
  // Institution admins may only read policies; the hierarchy and policy-type APIs return 403 for them.
  const canManage = role === "adopter";
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainsStatus, setDomainsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [domainsError, setDomainsError] = useState("");
  const [types, setTypes] = useState<PiiType[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [categories, setCategories] = useState<PolicyCategory[]>([]);
  const [subcategories, setSubcategories] = useState<PolicySubcategory[]>([]);
  const [hierarchyStatus, setHierarchyStatus] = useState<"loading" | "ready" | "error">(
    canManage ? "loading" : "ready",
  );
  const [hierarchyError, setHierarchyError] = useState("");
  const [typesStatus, setTypesStatus] = useState<"loading" | "ready" | "error">("loading");
  const [typesError, setTypesError] = useState("");
  const [policiesStatus, setPoliciesStatus] = useState<"loading" | "ready" | "error">("loading");
  const [policiesError, setPoliciesError] = useState("");
  const [subscriptions, setSubscriptions] = useState<Record<string, string[]>>({});

  const [tab, setTab] = useState<PiiTab>(canManage ? "categories" : "policies");
  const [configTab, setConfigTab] = useState<ConfigTab>("types");
  const [catalogScope, setCatalogScope] = useState<CatalogScope>("all");
  const [policySearch, setPolicySearch] = useState("");
  const [policyDomainFilter, setPolicyDomainFilter] = useState("");
  const [policyCategoryFilter, setPolicyCategoryFilter] = useState("");
  const [policySubcategoryFilter, setPolicySubcategoryFilter] = useState("");
  const [typeSearch, setTypeSearch] = useState("");
  const [domainSearch, setDomainSearch] = useState("");
  const [playgroundPolicyId, setPlaygroundPolicyId] = useState("");
  const [playgroundInput, setPlaygroundInputState] = useState("");
  const [playgroundResult, setPlaygroundResult] = useState<PlaygroundResult | null>(null);
  const [playgroundRunning, setPlaygroundRunning] = useState(false);
  const [playgroundError, setPlaygroundError] = useState("");
  const playgroundRequest = useRef(0);
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

  const domainsRequest = useRef(0);
  const reloadDomains = useCallback(() => {
    const requestId = ++domainsRequest.current;
    setDomainsStatus("loading");
    setDomainsError("");
    void fetchDomains(role === "adopter")
      .then((next) => {
        if (requestId !== domainsRequest.current) return;
        setDomains(next);
        setDomainsStatus("ready");
      })
      .catch((error: unknown) => {
        if (requestId !== domainsRequest.current) return;
        setDomains([]);
        setDomainsError(apiErrorMessage(error, "Couldn't load domains."));
        setDomainsStatus("error");
      });
  }, [role]);

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
    if (!canManage) return;
    reloadHierarchy();
    return () => {
      hierarchyRequest.current += 1;
    };
  }, [canManage, reloadHierarchy]);

  useEffect(() => {
    if (!canManage) return;
    reloadTypes();
    return () => {
      typesRequest.current += 1;
    };
  }, [canManage, reloadTypes]);

  // The policy form needs the types on load; opening Configuration → PII Types fetches them again.
  const typesTabOpen = tab === "configuration" && configTab === "types";
  useEffect(() => {
    if (typesTabOpen) reloadTypes();
  }, [typesTabOpen, reloadTypes]);

  useEffect(() => {
    reloadDomains();
    return () => {
      domainsRequest.current += 1;
    };
  }, [reloadDomains]);

  // Policies map domain names onto this list, so they load once domains have settled.
  useEffect(() => {
    if (domainsStatus === "loading") return;
    reloadPolicies();
    return () => {
      policiesRequest.current += 1;
    };
  }, [domainsStatus, reloadPolicies]);

  const value = useMemo<PiiPoliciesContextValue>(() => {
    const toast = (message: string) => showToast({ type: "success", message, messageOnly: true });
    const clearPlaygroundRun = () => {
      playgroundRequest.current += 1;
      setPlaygroundRunning(false);
      setPlaygroundError("");
      setPlaygroundResult(null);
    };
    const refreshTypes = async () => {
      const items = await listPolicyTypes();
      setTypes(items.map(definitionFromPolicyType));
      setTypesStatus("ready");
      setTypesError("");
    };
    /** Writes the policy's own fields to its owned type, creating the type when it has none. */
    const writeOwnedType = async (
      policyName: string,
      ownedId: string | undefined,
      fields: PolicyField[],
    ): Promise<{ id: string; created: boolean } | { error: string }> => {
      const policyFields = policyFieldsFromDefinition({ fields });
      // A type left behind by a create that failed after the type was written is reused.
      const name = policyOwnedTypeName(policyName);
      const targetId = ownedId ?? types.find((type) => type.name === name)?.id;
      try {
        if (targetId) {
          const numeric = numericId(targetId);
          if (numeric == null) return { error: "Couldn't save the policy's custom fields." };
          const saved = await updatePolicyType(numeric, policyFields);
          const next = definitionFromPolicyType(saved);
          setTypes((prev) => prev.map((t) => (t.id === targetId ? next : t)));
          return { id: targetId, created: false };
        }
        const createdId = await createPolicyType({ policy_type: name, policy_fields: policyFields });
        await refreshTypes();
        return { id: String(createdId), created: true };
      } catch (error: unknown) {
        return { error: `Couldn't save the policy's custom fields. ${apiErrorMessage(error, "")}`.trim() };
      }
    };
    const discardOwnedType = async (id: string) => {
      const numeric = numericId(id);
      if (numeric == null) return;
      try {
        await deletePolicyType(numeric);
        setTypes((prev) => prev.filter((t) => t.id !== id));
      } catch {
        // Left in place; it is hidden from every list and reused if the policy adds custom fields again.
      }
    };
    const withOwnedType = (input: PolicyInput, ownedId: string): PolicyInput => ({
      ...input,
      typeIds: [...input.typeIds.filter((id) => id !== ownedId), ownedId],
      selectedFields: input.selectedFields
        ? [...input.selectedFields, ...input.ownFields.map((field) => selectionForField(ownedId, field))]
        : null,
    });

    return {
      domains,
      domainsStatus,
      domainsError,
      reloadDomains,
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
      showCategoryPolicies: (categoryId) => {
        setPolicyCategoryFilter(categoryId);
        setPolicySubcategoryFilter("");
        setTab("policies");
      },
      showSubcategoryPolicies: (subcategoryId) => {
        const sub = subcategories.find((s) => s.id === subcategoryId);
        setPolicyCategoryFilter(sub?.categoryId ?? "");
        setPolicySubcategoryFilter(subcategoryId);
        setTab("policies");
      },
      tab,
      setTab: (next) => {
        if (next === "policies") {
          setPolicyCategoryFilter("");
          setPolicySubcategoryFilter("");
        }
        setTab(next);
      },
      configTab,
      setConfigTab,
      catalogScope,
      setCatalogScope,
      policySearch,
      setPolicySearch,
      policyDomainFilter,
      setPolicyDomainFilter,
      policyCategoryFilter,
      setPolicyCategoryFilter,
      policySubcategoryFilter,
      setPolicySubcategoryFilter,
      typeSearch,
      setTypeSearch,
      domainSearch,
      setDomainSearch,
      playgroundPolicyId,
      playgroundInput,
      playgroundResult,
      playgroundRunning,
      playgroundError,
      setPlaygroundPolicy: (policyId) => {
        clearPlaygroundRun();
        setPlaygroundPolicyId(policyId);
      },
      setPlaygroundInput: (input) => {
        clearPlaygroundRun();
        setPlaygroundInputState(input);
      },
      loadPlaygroundSample: (sample) => {
        clearPlaygroundRun();
        setPlaygroundInputState(sample);
      },
      runPlayground: async () => {
        const policy = policies.find((p) => p.policyId === playgroundPolicyId);
        const text = playgroundInput;
        if (!policy || !text.trim()) return;
        const requestId = ++playgroundRequest.current;
        setPlaygroundRunning(true);
        setPlaygroundError("");
        setPlaygroundResult(null);
        try {
          const id = numericId(policy.id);
          if (id == null) {
            setPlaygroundError("Couldn't run the simulation.");
            return;
          }
          const simulation = await simulatePolicy(text, id);
          if (requestId !== playgroundRequest.current) return;
          setPlaygroundResult({ ...simulation, policyId: policy.policyId });
        } catch (error: unknown) {
          if (requestId !== playgroundRequest.current) return;
          setPlaygroundError(apiErrorMessage(error, "Couldn't run the simulation."));
        } finally {
          if (requestId === playgroundRequest.current) setPlaygroundRunning(false);
        }
      },
      openPlayground: (policyId) => {
        clearPlaygroundRun();
        setPlaygroundPolicyId(policyId);
        setTab("playground");
      },
      drawer,
      openDrawer: (next) => setDrawer(next),
      closeDrawer: () => setDrawer({ kind: "none" }),
      confirm,
      askConfirm: setConfirm,
      closeConfirm: () => setConfirm(null),
      addDomain: async (name, description) => {
        const domainId = name.trim();
        if (!domainId) return "Domain name is required.";
        if (domainId.length > 50) return "Domain name is limited to 50 characters.";
        if (duplicateName(domains, domainId)) return "A domain with this name already exists.";
        try {
          await piiService.createDomain(domainId, description.trim());
          const next = await fetchDomains(true);
          setDomains(next);
          setDomainsStatus("ready");
          setDomainsError("");
          toast("Domain created.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the domain.");
        }
      },
      addType: async (input) => {
       // if (duplicateName(types, input.name)) return "A policy type with this name already exists.";
        try {
          const createdId = await createPolicyType({
            policy_type: input.name,
            policy_fields: policyFieldsFromDefinition(input),
          });
          const items = await listPolicyTypes();
          setTypes(items.map(definitionFromPolicyType));
          setTypesStatus("ready");
          setTypesError("");
          if (!items.some((item) => item.id === createdId)) {
            return "The PII definition was created, but it is not in the list yet.";
          }
          toast("Policy type added.");
          return null;
        } catch (error: unknown) {
          return apiErrorMessage(error, "Couldn't create the PII definition.");
        }
      },
      updateType: async (id, input) => {
        const current = types.find((t) => t.id === id);
        if (!current) return "PII type not found.";
        // if (duplicateName(types, input.name, id)) {
        //   return "A policy type with this name already exists.";
        // }
        const typeId = numericId(id);
        if (typeId == null) return "Couldn't update the PII definition.";
        try {
          const saved = await updatePolicyType(typeId, policyFieldsFromDefinition(input));
          const next = definitionFromPolicyType(saved);
          setTypes((prev) => prev.map((t) => (t.id === id ? next : t)));
          toast("Policy type updated.");
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
          toast("Policy type deleted.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't delete the PII definition."),
            messageOnly: true,
          });
        }
      },
      addPolicy: async (input) => {
        if (duplicateName(policies, input.name)) return "A policy with this name already exists.";
        let owned: { id: string; created: boolean } | null = null;
        if (input.ownFields.length > 0) {
          const result = await writeOwnedType(input.name, undefined, input.ownFields);
          if ("error" in result) return result.error;
          owned = result;
        }
        const payload = policyCreatePayload(owned ? withOwnedType(input, owned.id) : input, domains);
        if (!payload) return "Couldn't create the policy.";
        try {
          await createPolicy(payload);
        } catch (error: unknown) {
          if (owned?.created) await discardOwnedType(owned.id);
          return apiErrorMessage(error, "Couldn't create the policy.");
        }
        try {
          const items = await listPolicies();
          setPolicies(items.map((item) => policyFromRecord(item, domains)));
          setPoliciesStatus("ready");
          setPoliciesError("");
        } catch {
          reloadPolicies();
        }
        toast("Policy created.");
        return null;
      },
      updatePolicy: async (id, input) => {
        const current = policies.find((p) => p.id === id);
        if (!current) return "Policy not found.";
        if (duplicateName(policies, input.name, id)) return "A policy with this name already exists.";
        // Without the types, the policy's own fields are unknown and saving would drop them.
        if (typesStatus !== "ready") return "PII types are still loading. Try again in a moment.";
        const policyId = numericId(id);
        if (policyId == null) return "Couldn't update the policy.";
        const ownedBefore = policyOwnedType(current, types);
        let ownedId = ownedBefore?.id;
        let createdOwned = false;
        if (input.ownFields.length > 0 && !ownedId) {
          const result = await writeOwnedType(current.name, undefined, input.ownFields);
          if ("error" in result) return result.error;
          ownedId = result.id;
          createdOwned = result.created;
        }
        const keepOwned = input.ownFields.length > 0 && ownedId;
        const payload = policyUpdatePayload(keepOwned ? withOwnedType(input, ownedId as string) : input, domains);
        if (!payload) return "Couldn't update the policy.";
        try {
          const saved = await updatePolicy(policyId, payload);
          const next = policyFromRecord(saved, domains);
          setPolicies((prev) => prev.map((p) => (p.id === id ? next : p)));
        } catch (error: unknown) {
          if (createdOwned && ownedId) await discardOwnedType(ownedId);
          return apiErrorMessage(error, "Couldn't update the policy.");
        }
        if (keepOwned && ownedBefore) {
          const result = await writeOwnedType(current.name, ownedBefore.id, input.ownFields);
          if ("error" in result) return result.error;
        } else if (!keepOwned && ownedBefore) {
          await discardOwnedType(ownedBefore.id);
        }
        toast("Policy updated.");
        return null;
      },
      deletePolicy: async (id) => {
        const policyId = numericId(id);
        if (policyId == null) {
          showToast({ type: "error", message: "Couldn't delete the policy.", messageOnly: true });
          return;
        }
        const current = policies.find((p) => p.id === id);
        const owned = current ? policyOwnedType(current, types) : undefined;
        try {
          await deletePolicy(policyId);
          setPolicies((prev) => prev.filter((p) => p.id !== id));
          if (owned) await discardOwnedType(owned.id);
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
          setPolicies((prev) => prev.map((p) => (p.id === id ? next : p)));
          toast(status === "Active" ? "Policy activated." : "Policy deactivated.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't update the policy."),
            messageOnly: true,
          });
        }
      },
      setCategoryStatus: async (id, status) => {
        const categoryId = numericId(id);
        if (categoryId == null) {
          showToast({ type: "error", message: "Couldn't update the category.", messageOnly: true });
          return;
        }
        try {
          const saved = await updatePolicyCategoryStatus(categoryId, status === "Active");
          const next = toCategory(saved);
          setCategories((prev) => prev.map((c) => (c.id === id ? next : c)));
          toast(status === "Active" ? "Category activated." : "Category deactivated.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't update the category."),
            messageOnly: true,
          });
        }
      },
      setSubcategoryStatus: async (id, status) => {
        const subCategoryId = numericId(id);
        if (subCategoryId == null) {
          showToast({
            type: "error",
            message: "Couldn't update the sub-category.",
            messageOnly: true,
          });
          return;
        }
        try {
          const saved = await updatePolicySubCategoryStatus(subCategoryId, status === "Active");
          const next = toSubcategory(saved);
          setSubcategories((prev) => prev.map((s) => (s.id === id ? next : s)));
          toast(status === "Active" ? "Sub-category activated." : "Sub-category deactivated.");
        } catch (error: unknown) {
          showToast({
            type: "error",
            message: apiErrorMessage(error, "Couldn't update the sub-category."),
            messageOnly: true,
          });
        }
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
    domainsStatus,
    domainsError,
    reloadDomains,
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
    tab,
    configTab,
    catalogScope,
    policySearch,
    policyDomainFilter,
    policyCategoryFilter,
    policySubcategoryFilter,
    typeSearch,
    domainSearch,
    playgroundPolicyId,
    playgroundInput,
    playgroundResult,
    playgroundRunning,
    playgroundError,
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

/**
 * Adopters read every domain, including descriptions. Everyone else reads the
 * public list of active domain ids. A failed admin read falls back to that list.
 */
async function fetchDomains(includeAll: boolean): Promise<Domain[]> {
  if (includeAll) {
    try {
      const response = await piiService.getAllDomains();
      return response.data.map((row) => ({
        id: row.domain_id,
        name: row.domain_id,
        description: row.description?.trim() ?? "",
      }));
    } catch {
      // The public list still fills the picker.
    }
  }
  const response = await piiService.getDomains();
  return response.data.map((id) => ({ id, name: id, description: "" }));
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

export function apiErrorMessage(error: unknown, fallback = "Couldn't load policy categories."): string {
  if (!error || typeof error !== "object") {
    return error instanceof Error && error.message ? error.message : fallback;
  }
  const data = (
    error as {
      response?: {
        data?: { detail?: unknown; message?: string; error?: { message?: string } };
      };
    }
  ).response?.data;
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
  if (typeof data?.error?.message === "string" && data.error.message.trim()) return data.error.message;
  if (typeof data?.message === "string" && data.message.trim()) return data.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
