import React, { useEffect, useState } from "react";
import { piiService } from "../../services/piiService";
import styles from "./PiiManagement.module.css";
import { TableFilterToolbar, TablePaginationBar, TableSortHeader } from "../common/TableControls";

interface Rule {
  entity_type: string;
  action: string;
  config: Record<string, unknown>;
  custom_regex?: string;
}

interface Domain {
  domain_id: string;
  is_active: boolean;
  description?: string | null;
}

type PageTab = "admin" | "audit";

interface AuditLogRow {
  id: number;
  trace_id: string;
  tenant_id: string;
  domain_id: string;
  target_context: string;
  pii_count: number;
  processing_ms: number;
  trace_json: unknown;
  created_at: string;
}

export interface PiiManagementProps {
  isAdmin?: boolean;
}

export default function PiiManagement({ isAdmin = false }: PiiManagementProps) {
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
  const [activeTab, setActiveTab] = useState<PageTab>("admin");
  const [allDomains, setAllDomains] = useState<Domain[]>([]);
  const [checkedDomains, setCheckedDomains] = useState<Set<string>>(new Set());
  const [newDomainId, setNewDomainId] = useState("");
  const [editingDomainId, setEditingDomainId] = useState<string | null>(null);
  const [editingRules, setEditingRules] = useState<Rule[]>([]);
  const [tenantMappings, setTenantMappings] = useState<
    { tenant_id: string; domain_id: string; updated_at?: string }[]
  >([]);
  const [newMapTenantId, setNewMapTenantId] = useState("");
  const [newMapDomainId, setNewMapDomainId] = useState("");
  const [newEntity, setNewEntity] = useState("");
  const [newAction, setNewAction] = useState("REDACT_TAG");
  const [newExample, setNewExample] = useState("");
  const [newRegex, setNewRegex] = useState("");
  const [adminDataError, setAdminDataError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogRow[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [rulesSortDirection, setRulesSortDirection] = useState<"asc" | "desc">("asc");
  const [rulesPage, setRulesPage] = useState(1);
  const [rulesPageSize, setRulesPageSize] = useState(10);
  const [mappingSearch, setMappingSearch] = useState("");
  const [mappingSortDirection, setMappingSortDirection] = useState<"asc" | "desc">("asc");
  const [mappingPage, setMappingPage] = useState(1);
  const [mappingPageSize, setMappingPageSize] = useState(10);
  const [auditSearch, setAuditSearch] = useState("");
  const [auditSortDirection, setAuditSortDirection] = useState<"asc" | "desc">("desc");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(10);

  useEffect(() => {
    if (!isAdmin || activeTab !== "audit") return;
    void fetchAuditLogs();
  }, [isAdmin, activeTab]);

  // Loads domains + tenant mappings on admin-tab entry (mount and when returning from Audit).
  // Replaces a plain mount effect calling fetchAllDomains/fetchTenantMappings; uses retry + adminDataError.
  useEffect(() => {
    if (!isAdmin || activeTab !== "admin") return;
    void refreshAdminDataWithRetry();
  }, [isAdmin, activeTab]);

  const fetchAllDomains = async () => {
    const res = await piiService.getAllDomains();
    setAllDomains(res.data);
    const active = new Set(res.data.filter((d: Domain) => d.is_active).map((d: Domain) => d.domain_id));
    setCheckedDomains(active);
  };

  const handleToggleDomainActivate = (domainId: string) => {
    const next = new Set(checkedDomains);
    if (next.has(domainId)) next.delete(domainId);
    else next.add(domainId);
    setCheckedDomains(next);
  };

  const applyActiveDomains = async () => {
    try {
      await piiService.activateDomains(Array.from(checkedDomains));
      alert("Domain activation updated.");
      await fetchAllDomains();
    } catch {
      alert("Failed to apply domains");
    }
  };

  const fetchTenantMappings = async () => {
    const res = await piiService.listTenantDomainMappings();
    setTenantMappings(res.data);
  };

  const refreshAdminDataWithRetry = async () => {
    setAdminDataError(null);
    try {
      await Promise.all([fetchAllDomains(), fetchTenantMappings()]);
      return;
    } catch (e) {
      console.error("Admin data fetch failed, retrying once...", e);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
    try {
      await Promise.all([fetchAllDomains(), fetchTenantMappings()]);
    } catch (e) {
      console.error("Admin data fetch failed after retry", e);
      setAdminDataError("Could not load domains/mappings. Please click Refresh.");
    }
  };

  const handleSaveTenantMapping = async () => {
    const tid = newMapTenantId.trim();
    if (!tid || !newMapDomainId) {
      alert("Enter tenant ID and choose a domain");
      return;
    }
    try {
      await piiService.upsertTenantDomainMapping(tid, newMapDomainId);
      setNewMapTenantId("");
      await fetchTenantMappings();
    } catch (e) {
      alert("Failed to save mapping (check domain exists and permissions)");
    }
  };

  const handleDeleteTenantMapping = async (tenantId: string) => {
    if (
      typeof window !== "undefined" &&
      !window.confirm(`Remove mapping for tenant "${tenantId}"?`)
    )
      return;
    try {
      await piiService.deleteTenantDomainMapping(tenantId);
      await fetchTenantMappings();
    } catch (e) {
      alert("Failed to delete mapping");
    }
  };

  const handleCreateDomain = async () => {
    if (!newDomainId) return;
    try {
      await piiService.createDomain(newDomainId);
      setNewDomainId('');
      await fetchAllDomains();
    } catch {
      alert("Failed to create domain");
    }
  };

  const loadDomainConfig = async (id: string) => {
    setEditingDomainId(id);
    try {
      const res = await piiService.getPolicy(id);
      const rules = Array.isArray(res.data.rules) ? (res.data.rules as Rule[]) : [];
      setEditingRules(rules);
    } catch {
      alert("Failed to load policy");
    }
  };

  const generateRegex = async () => {
    try {
      const res = await piiService.generateRegex(newExample);
      setNewRegex(res.data.regex);
    } catch {
      alert("Regex generation failed");
    }
  };

  const addCustomRule = () => {
    if (!newEntity) return alert("Entity name required");
    const rule: Rule = { entity_type: newEntity.toUpperCase(), action: newAction, config: {} };
    if (newRegex.trim()) rule.custom_regex = newRegex;
    
    setEditingRules([...editingRules, rule]);
    setNewEntity('');
    setNewRegex('');
    setNewExample('');
  };

  const saveConfig = async () => {
    if (!editingDomainId) return alert("Select a domain to edit");
    try {
      await piiService.deployRules(editingDomainId, editingRules);
      alert("Policy rules saved.");
      await fetchAllDomains();
    } catch {
      alert("Save failed");
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const res = await piiService.getAuditLogs(100);
      setAuditLogs(res.data);
    } catch {
      alert("Failed to load audit logs");
    } finally {
      setAuditLoading(false);
    }
  };

  const removeRule = (index: number) => {
    setEditingRules(editingRules.filter((_, i) => i !== index));
  };

  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case 'MASK': return 'bg-gray-800 text-white';
      case 'HASH': return 'bg-red-600 text-white';
      default: return 'bg-gray-200 text-gray-800';
    }
  };

  const activeDomainCount = allDomains.filter((d) => d.is_active).length;

  const sortedRules = [...editingRules].sort((a, b) => {
    const nameCmp = (a.entity_type ?? "").localeCompare(b.entity_type ?? "", undefined, { sensitivity: "base" });
    return rulesSortDirection === "asc" ? nameCmp : -nameCmp;
  });
  const rulesTotal = sortedRules.length;
  const rulesTotalPages = Math.max(1, Math.ceil(rulesTotal / rulesPageSize));
  const rulesStartRow = rulesTotal === 0 ? 0 : (rulesPage - 1) * rulesPageSize + 1;
  const rulesEndRow = Math.min(rulesPage * rulesPageSize, rulesTotal);
  const paginatedRules = sortedRules.slice((rulesPage - 1) * rulesPageSize, rulesPage * rulesPageSize);

  const filteredMappings = tenantMappings.filter((row) => {
    const q = mappingSearch.trim().toLowerCase();
    if (!q) return true;
    return (row.tenant_id ?? "").toLowerCase().includes(q) || (row.domain_id ?? "").toLowerCase().includes(q);
  });
  const sortedMappings = [...filteredMappings].sort((a, b) => {
    const nameCmp = (a.tenant_id ?? "").localeCompare(b.tenant_id ?? "", undefined, { sensitivity: "base" });
    return mappingSortDirection === "asc" ? nameCmp : -nameCmp;
  });
  const mappingsTotal = sortedMappings.length;
  const mappingsTotalPages = Math.max(1, Math.ceil(mappingsTotal / mappingPageSize));
  const mappingsStartRow = mappingsTotal === 0 ? 0 : (mappingPage - 1) * mappingPageSize + 1;
  const mappingsEndRow = Math.min(mappingPage * mappingPageSize, mappingsTotal);
  const paginatedMappings = sortedMappings.slice((mappingPage - 1) * mappingPageSize, mappingPage * mappingPageSize);

  const filteredAuditLogs = auditLogs.filter((row) => {
    const q = auditSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      (row.trace_id ?? "").toLowerCase().includes(q) ||
      (row.tenant_id ?? "").toLowerCase().includes(q) ||
      (row.domain_id ?? "").toLowerCase().includes(q) ||
      (row.target_context ?? "").toLowerCase().includes(q)
    );
  });
  const sortedAuditLogs = [...filteredAuditLogs].sort((a, b) => {
    const timeA = new Date(a.created_at ?? "").getTime();
    const timeB = new Date(b.created_at ?? "").getTime();
    return auditSortDirection === "asc" ? timeA - timeB : timeB - timeA;
  });
  const auditTotal = sortedAuditLogs.length;
  const auditTotalPages = Math.max(1, Math.ceil(auditTotal / auditPageSize));
  const auditStartRow = auditTotal === 0 ? 0 : (auditPage - 1) * auditPageSize + 1;
  const auditEndRow = Math.min(auditPage * auditPageSize, auditTotal);
  const paginatedAuditLogs = sortedAuditLogs.slice((auditPage - 1) * auditPageSize, auditPage * auditPageSize);

  useEffect(() => {
    if (rulesPage > rulesTotalPages) setRulesPage(rulesTotalPages);
  }, [rulesPage, rulesTotalPages]);

  useEffect(() => {
    if (mappingPage > mappingsTotalPages) setMappingPage(mappingsTotalPages);
  }, [mappingPage, mappingsTotalPages]);

  useEffect(() => {
    if (auditPage > auditTotalPages) setAuditPage(auditTotalPages);
  }, [auditPage, auditTotalPages]);

  if (!isAdmin) {
    return (
      <div className={`${styles.root} p-6 bg-gray-50 min-h-screen font-sans`}>
        <div className="bg-white p-5 rounded-lg border shadow-sm">
          <h2 className="text-sm font-bold text-gray-800 mb-2">PII Management</h2>
          <p className="text-sm text-gray-600">
            You do not have access to this page. Admin permissions are required.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.root} p-6 bg-gray-50 min-h-screen font-sans`}>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">PII Management</h1>
          <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full font-semibold">
            Admin Console
          </span>
        </div>
      </div>

      <div className="flex border-b mb-6 space-x-4">
        <button
          type="button"
          className={`pb-2 px-4 font-semibold ${activeTab === 'admin' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
          onClick={() => setActiveTab('admin')}
        >
          Admin
        </button>
        <button
          type="button"
          className={`pb-2 px-4 font-semibold ${activeTab === 'audit' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
          onClick={() => setActiveTab('audit')}
        >
          Audit Logs
        </button>
      </div>

      {activeTab === "admin" ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white p-5 rounded-lg border shadow-sm flex flex-col h-[600px]">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">
              Domain Inventory
            </h2>
            <div className="flex-1 overflow-y-auto space-y-2 mb-4">
              {allDomains.map((d) => (
                <div key={d.domain_id} className="flex justify-between items-center p-2 border rounded hover:bg-gray-50">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      checked={checkedDomains.has(d.domain_id)}
                      onChange={() => handleToggleDomainActivate(d.domain_id)}
                    />
                    <span className="font-semibold text-sm cursor-pointer" onClick={() => loadDomainConfig(d.domain_id)}>
                      {d.domain_id.toUpperCase()}
                    </span>
                  </div>
                  <button className="text-xs text-blue-600 hover:bg-blue-50 p-1 rounded" onClick={() => loadDomainConfig(d.domain_id)}>
                    Edit
                  </button>
                </div>
              ))}
            </div>
            <button
              disabled={checkedDomains.size === 0}
              onClick={applyActiveDomains}
              className="w-full bg-gray-800 text-white font-bold py-2 rounded disabled:opacity-50 mb-4"
            >
              Apply Active Domains ({checkedDomains.size})
            </button>
            <div className="border-t pt-4">
              <input
                type="text"
                placeholder="New domain id"
                className="w-full border rounded p-2 text-sm mb-2"
                value={newDomainId}
                onChange={(e) => setNewDomainId(e.target.value)}
              />
              <button onClick={handleCreateDomain} className="w-full border border-gray-800 text-gray-800 font-bold py-1.5 rounded text-sm hover:bg-gray-50">
                Create Domain
              </button>
            </div>
          </div>

          <div className="md:col-span-2 bg-white p-5 rounded-lg border shadow-sm h-[600px] flex flex-col">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2 flex justify-between items-center">
              <span>Policy Rules</span>
              {editingDomainId && <span className="bg-yellow-100 text-yellow-800 px-2 rounded normal-case tracking-normal">Editing: {editingDomainId}</span>}
            </h2>

            <div className="flex-1 overflow-y-auto border rounded bg-gray-50 p-2 mb-4">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-200">
                  <tr>
                    <th className="p-2">
                      <TableSortHeader
                        label="Entity"
                        direction={rulesSortDirection}
                        onAsc={() => { setRulesSortDirection("asc"); setRulesPage(1); }}
                        onDesc={() => { setRulesSortDirection("desc"); setRulesPage(1); }}
                        ascAriaLabel="Sort rules by entity ascending"
                        descAriaLabel="Sort rules by entity descending"
                      />
                    </th>
                    <th className="p-2">Action</th>
                    <th className="p-2">Delete</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedRules.map((r, i) => (
                    <tr key={i} className="border-b bg-white">
                      <td className="p-2 font-bold">{r.entity_type}</td>
                      <td className="p-2"><span className="border bg-gray-100 px-2 rounded text-xs">{r.action}</span></td>
                      <td className="p-2">
                        <button onClick={() => removeRule((rulesPage - 1) * rulesPageSize + i)} className="text-red-500 hover:underline text-xs">Delete</button>
                      </td>
                    </tr>
                  ))}
                  {rulesTotal === 0 && (
                    <tr><td colSpan={3} className="text-center p-4 text-gray-400">No rules configured for this domain.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {rulesTotal > 0 ? (
              <TablePaginationBar
                startRow={rulesStartRow}
                endRow={rulesEndRow}
                totalItems={rulesTotal}
                page={rulesPage}
                totalPages={rulesTotalPages}
                pageSize={rulesPageSize}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                onPageSizeChange={(value) => { setRulesPageSize(value); setRulesPage(1); }}
                onFirst={() => setRulesPage(1)}
                onPrev={() => setRulesPage((p) => Math.max(1, p - 1))}
                onNext={() => setRulesPage((p) => Math.min(rulesTotalPages, p + 1))}
                onLast={() => setRulesPage(rulesTotalPages)}
                canPrev={rulesPage > 1}
                canNext={rulesPage < rulesTotalPages}
                borderColor="#e2e8f0"
                bg="white"
              />
            ) : null}

            <div className="border rounded p-4 mb-4 bg-white">
              <h6 className="text-sm font-bold text-blue-600 mb-3">Add Custom Rule</h6>
              <div className="grid grid-cols-12 gap-2 mb-2">
                <input type="text" placeholder="Entity (e.g., PASSPORT)" className="col-span-3 border rounded px-2 py-1 text-sm" value={newEntity} onChange={e => setNewEntity(e.target.value)} />
                <select className="col-span-3 border rounded px-2 py-1 text-sm" value={newAction} onChange={e => setNewAction(e.target.value)}>
                  <option>REDACT_TAG</option><option>MASK</option><option>HASH</option>
                </select>
                <div className="col-span-6 flex">
                  <input type="text" placeholder="AI Example (e.g., A1234567)" className="flex-1 border rounded-l px-2 py-1 text-sm" value={newExample} onChange={e => setNewExample(e.target.value)} />
                  <button onClick={generateRegex} className="bg-gray-200 border border-l-0 rounded-r px-3 text-sm hover:bg-gray-300">Generate Regex</button>
                </div>
              </div>
              <input type="text" placeholder="Generated Regex / Pattern" readOnly className="w-full border rounded px-2 py-1 text-sm bg-gray-100 font-mono mb-2" value={newRegex} />
              <button onClick={addCustomRule} className="w-full border border-blue-600 text-blue-600 py-1 rounded hover:bg-blue-50 text-sm font-semibold">
                Add Rule
              </button>
            </div>

            <button onClick={saveConfig} className="w-full bg-green-600 text-white font-bold py-2 rounded hover:bg-green-700">
              Save Policy
            </button>
          </div>

          <div className="md:col-span-3 bg-white p-5 rounded-lg border shadow-sm overflow-x-auto">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">
              Tenant to Domain Mapping
            </h2>
            <div className="flex flex-col sm:flex-row gap-3 items-end flex-wrap mb-4">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-semibold text-gray-600 mb-1">Tenant ID</label>
                <input
                  type="text"
                  placeholder="tenant uuid/slug"
                  className="w-full border rounded p-2 text-sm"
                  value={newMapTenantId}
                  onChange={(e) => setNewMapTenantId(e.target.value)}
                />
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-semibold text-gray-600 mb-1">Domain</label>
                <select
                  className="w-full border rounded p-2 text-sm"
                  value={newMapDomainId}
                  onChange={(e) => setNewMapDomainId(e.target.value)}
                >
                  <option value="">Select domain</option>
                  {allDomains.map((d) => (
                    <option key={d.domain_id} value={d.domain_id}>
                      {d.domain_id}
                      {d.is_active ? " (active)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <button type="button" onClick={() => void handleSaveTenantMapping()} className="bg-blue-600 text-white font-semibold px-4 py-2 rounded hover:bg-blue-700 text-sm">
                Save
              </button>
              <button type="button" onClick={() => void refreshAdminDataWithRetry()} className="border border-gray-300 px-4 py-2 rounded text-sm hover:bg-gray-50">
                Refresh
              </button>
            </div>
            {adminDataError ? (
              <div className="p-2 mb-2 text-xs rounded bg-red-50 text-red-600 border border-red-200">
                {adminDataError}
              </div>
            ) : null}
            <TableFilterToolbar
              hasActiveFilters={!!mappingSearch.trim()}
              onClear={() => { setMappingSearch(""); setMappingPage(1); }}
            >
              <input
                type="text"
                placeholder="Search tenant or domain..."
                className="border rounded p-2 text-sm min-w-[240px]"
                value={mappingSearch}
                onChange={(e) => { setMappingSearch(e.target.value); setMappingPage(1); }}
              />
            </TableFilterToolbar>
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-2">
                    <TableSortHeader
                      label="Tenant ID"
                      direction={mappingSortDirection}
                      onAsc={() => { setMappingSortDirection("asc"); setMappingPage(1); }}
                      onDesc={() => { setMappingSortDirection("desc"); setMappingPage(1); }}
                      ascAriaLabel="Sort mappings by tenant ascending"
                      descAriaLabel="Sort mappings by tenant descending"
                    />
                  </th>
                  <th className="p-2">Domain</th>
                  <th className="p-2">Updated</th>
                  <th className="p-2 w-24">Actions</th>
                </tr>
              </thead>
              <tbody>
                {mappingsTotal === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-gray-400">No mappings configured.</td>
                  </tr>
                ) : (
                  paginatedMappings.map((row) => (
                    <tr key={row.tenant_id} className="border-b">
                      <td className="p-2 font-mono text-xs">{row.tenant_id}</td>
                      <td className="p-2 font-semibold">{row.domain_id}</td>
                      <td className="p-2 text-gray-500 text-xs">{row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}</td>
                      <td className="p-2">
                        <button type="button" onClick={() => void handleDeleteTenantMapping(row.tenant_id)} className="text-red-600 hover:underline text-xs">
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            {mappingsTotal > 0 ? (
              <TablePaginationBar
                startRow={mappingsStartRow}
                endRow={mappingsEndRow}
                totalItems={mappingsTotal}
                page={mappingPage}
                totalPages={mappingsTotalPages}
                pageSize={mappingPageSize}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                onPageSizeChange={(value) => { setMappingPageSize(value); setMappingPage(1); }}
                onFirst={() => setMappingPage(1)}
                onPrev={() => setMappingPage((p) => Math.max(1, p - 1))}
                onNext={() => setMappingPage((p) => Math.min(mappingsTotalPages, p + 1))}
                onLast={() => setMappingPage(mappingsTotalPages)}
                canPrev={mappingPage > 1}
                canNext={mappingPage < mappingsTotalPages}
                borderColor="#e2e8f0"
                bg="white"
              />
            ) : null}
          </div>
        </div>
      ) : null}

      {activeTab === "audit" ? (
        <div className="space-y-6">
          <div className="bg-white p-5 rounded-lg border shadow-sm">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-sm font-bold text-gray-800 mb-2">Audit Logs</h2>
                <p className="text-sm text-gray-600">Recent redact events captured by `pii-service`.</p>
              </div>
              <button
                type="button"
                onClick={() => void fetchAuditLogs()}
                className="border border-gray-300 px-4 py-2 rounded text-sm hover:bg-gray-50"
              >
                Refresh
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Total Domains</p>
              <p className="text-2xl font-bold text-gray-900">{allDomains.length}</p>
            </div>
            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Active Domains</p>
              <p className="text-2xl font-bold text-gray-900">{activeDomainCount}</p>
            </div>
            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Tenant Mappings</p>
              <p className="text-2xl font-bold text-gray-900">{tenantMappings.length}</p>
            </div>
          </div>
          <div className="bg-white p-5 rounded-lg border shadow-sm overflow-x-auto">
            <TableFilterToolbar
              hasActiveFilters={!!auditSearch.trim()}
              onClear={() => { setAuditSearch(""); setAuditPage(1); }}
              rightContent={(
                <button
                  type="button"
                  onClick={() => void fetchAuditLogs()}
                  className="border border-gray-300 px-4 py-2 rounded text-sm hover:bg-gray-50"
                >
                  Refresh
                </button>
              )}
            >
              <input
                type="text"
                placeholder="Search trace/tenant/domain/target..."
                className="border rounded p-2 text-sm min-w-[260px]"
                value={auditSearch}
                onChange={(e) => { setAuditSearch(e.target.value); setAuditPage(1); }}
              />
            </TableFilterToolbar>
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-2">
                    <TableSortHeader
                      label="Time"
                      direction={auditSortDirection}
                      onAsc={() => { setAuditSortDirection("asc"); setAuditPage(1); }}
                      onDesc={() => { setAuditSortDirection("desc"); setAuditPage(1); }}
                      ascAriaLabel="Sort audit logs by time ascending"
                      descAriaLabel="Sort audit logs by time descending"
                    />
                  </th>
                  <th className="p-2">Trace ID</th>
                  <th className="p-2">Tenant</th>
                  <th className="p-2">Domain</th>
                  <th className="p-2">Target</th>
                  <th className="p-2">PII Count</th>
                  <th className="p-2">Latency</th>
                </tr>
              </thead>
              <tbody>
                {auditLoading ? (
                  <tr>
                    <td colSpan={7} className="p-4 text-center text-gray-500">Loading logs...</td>
                  </tr>
                ) : auditTotal === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-4 text-center text-gray-400">No audit logs found.</td>
                  </tr>
                ) : (
                  paginatedAuditLogs.map((row) => (
                    <tr key={row.id} className="border-b">
                      <td className="p-2 text-xs text-gray-600">
                        {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                      </td>
                      <td className="p-2 font-mono text-xs">{row.trace_id || "—"}</td>
                      <td className="p-2 font-mono text-xs">{row.tenant_id || "—"}</td>
                      <td className="p-2">{row.domain_id || "—"}</td>
                      <td className="p-2">{row.target_context || "—"}</td>
                      <td className="p-2">{row.pii_count ?? 0}</td>
                      <td className="p-2">{row.processing_ms ?? 0} ms</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            {!auditLoading && auditTotal > 0 ? (
              <TablePaginationBar
                startRow={auditStartRow}
                endRow={auditEndRow}
                totalItems={auditTotal}
                page={auditPage}
                totalPages={auditTotalPages}
                pageSize={auditPageSize}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                onPageSizeChange={(value) => { setAuditPageSize(value); setAuditPage(1); }}
                onFirst={() => setAuditPage(1)}
                onPrev={() => setAuditPage((p) => Math.max(1, p - 1))}
                onNext={() => setAuditPage((p) => Math.min(auditTotalPages, p + 1))}
                onLast={() => setAuditPage(auditTotalPages)}
                canPrev={auditPage > 1}
                canNext={auditPage < auditTotalPages}
                borderColor="#e2e8f0"
                bg="white"
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}