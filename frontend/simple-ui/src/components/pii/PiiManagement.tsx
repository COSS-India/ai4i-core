import React, { useState, useEffect } from "react";
import { piiService } from "../../services/piiService";

// --- Type Definitions ---
interface Rule {
  entity_type: string;
  action: string;
  config: any;
  custom_regex?: string;
}

interface Domain {
  domain_id: string;
  is_active: boolean;
  description?: string | null;
}

interface TraceStep {
  step: string;
  status: string;
  time_ms?: number;
  details: string;
}

export interface PiiManagementProps {
  isAdmin?: boolean;
}

type AdminTab = "demo" | "admin" | "tenants";

export default function PiiManagement({ isAdmin = false }: PiiManagementProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>("demo");

  // --- Demo State ---
  const [activeDomains, setActiveDomains] = useState<string[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [activePolicyRules, setActivePolicyRules] = useState<Rule[]>([]);
  const [target, setTarget] = useState('user');
  const [inputText, setInputText] = useState('Address is No. 32, Bull Temple Road, Bangalore.');
  const [outputText, setOutputText] = useState('...');
  const [latency, setLatency] = useState(0);
  const [jsonOutput, setJsonOutput] = useState('{}');
  const [traceLog, setTraceLog] = useState<TraceStep[]>([]);
  const [showTrace, setShowTrace] = useState(true);

  // --- Admin State ---
  const [allDomains, setAllDomains] = useState<Domain[]>([]);
  const [checkedDomains, setCheckedDomains] = useState<Set<string>>(new Set());
  const [newDomainId, setNewDomainId] = useState('');
  const [editingDomainId, setEditingDomainId] = useState<string | null>(null);
  const [editingRules, setEditingRules] = useState<Rule[]>([]);
  
  // Custom Rule Form
  const [newEntity, setNewEntity] = useState('');
  const [newAction, setNewAction] = useState('REDACT_TAG');
  const [newExample, setNewExample] = useState('');
  const [newRegex, setNewRegex] = useState('');

  // --- Tenant → domain mapping (admin) ---
  const [tenantMappings, setTenantMappings] = useState<
    { tenant_id: string; domain_id: string; updated_at?: string }[]
  >([]);
  const [newMapTenantId, setNewMapTenantId] = useState("");
  const [newMapDomainId, setNewMapDomainId] = useState("");

  // --- Initial Load ---
  useEffect(() => {
    fetchActiveDomains();
    if (isAdmin) void fetchAllDomains();
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin && (activeTab === "admin" || activeTab === "tenants"))
      setActiveTab("demo");
  }, [isAdmin, activeTab]);

  useEffect(() => {
    if (isAdmin && activeTab === "tenants") {
      void fetchTenantMappings();
      if (allDomains.length === 0) void fetchAllDomains();
    }
  }, [isAdmin, activeTab]);

  useEffect(() => {
    if (selectedDomain) fetchPolicy(selectedDomain);
  }, [selectedDomain]);

  // --- API Handlers (Demo) ---
  const fetchActiveDomains = async () => {
    try {
      const res = await piiService.getDomains();
      setActiveDomains(res.data);
      if (res.data.length > 0 && !selectedDomain) setSelectedDomain(res.data[0]);
    } catch (e) { console.error("Failed to fetch domains", e); }
  };

  const fetchPolicy = async (domain: string) => {
    try {
      const res = await piiService.getPolicy(domain);
      setActivePolicyRules(res.data.rules || []);
    } catch (e) { console.error("Failed to fetch policy", e); }
  };

  const handleRedact = async () => {
    if (!selectedDomain) return alert("Select an active domain first.");
    
    setOutputText("Processing...");
    setTraceLog([]);
    
    let lang = 'en';
    if (selectedDomain.includes('hi')) lang = 'hi';
    if (selectedDomain.includes('mr')) lang = 'mr';
    if (selectedDomain.includes('ta')) lang = 'ta';

    try {
      const res = await piiService.redact({ text: inputText, domain: selectedDomain }, target, lang);
      setOutputText(res.data.redacted_text);
      setLatency(res.data.metadata?.processing_time_ms || 0);
      setJsonOutput(JSON.stringify(res.data, null, 2));
      if (res.data.trace && showTrace) setTraceLog(res.data.trace);
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string | unknown } };
        message?: string;
      };
      const d = err.response?.data?.detail;
      const msg =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? JSON.stringify(d)
            : err.message ?? "Request failed";
      setOutputText(`⛔ Error: ${msg}`);
    }
  };

  // --- API Handlers (Admin) ---
  const fetchAllDomains = async () => {
    try {
      const res = await piiService.getAllDomains();
      setAllDomains(res.data);
      const active = new Set(res.data.filter((d: Domain) => d.is_active).map((d: Domain) => d.domain_id));
      setCheckedDomains(active);
    } catch (e) { console.error("Failed to fetch all domains", e); }
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
      alert("Deployment Updated!");
      fetchActiveDomains();
      fetchAllDomains();
    } catch (e) { alert("Failed to apply domains"); }
  };

  const fetchTenantMappings = async () => {
    try {
      const res = await piiService.listTenantDomainMappings();
      setTenantMappings(res.data);
    } catch (e) {
      console.error("Failed to fetch tenant mappings", e);
      alert("Failed to load tenant → domain mappings");
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
      fetchAllDomains();
    } catch (e) { alert("Failed to create domain"); }
  };

  const loadDomainConfig = async (id: string) => {
    setEditingDomainId(id);
    try {
      const res = await piiService.getPolicy(id);
      setEditingRules(res.data.rules || []);
    } catch (e) { alert("Failed to load policy"); }
  };

  const generateRegex = async () => {
    try {
      const res = await piiService.generateRegex(newExample);
      setNewRegex(res.data.regex);
    } catch (e) { alert("Regex generation failed"); }
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
      alert("Saved! Click 'Apply Active Domains' to push to production.");
      fetchAllDomains();
    } catch (e) { alert("Save failed"); }
  };

  const removeRule = (index: number) => {
    setEditingRules(editingRules.filter((_, i) => i !== index));
  };

  // --- Render Helpers ---
  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case 'MASK': return 'bg-gray-800 text-white';
      case 'HASH': return 'bg-red-600 text-white';
      default: return 'bg-gray-200 text-gray-800';
    }
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen font-sans">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">🛡️ AI4I PII Guardrail</h1>
          <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full font-semibold">v0.2.4 Multi-Lingual</span>
        </div>
        <div className="flex items-center space-x-2">
          <label className="text-sm font-bold text-gray-600">LIVE TRACE</label>
          <input type="checkbox" className="toggle" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b mb-6 space-x-4">
        <button 
          type="button"
          className={`pb-2 px-4 font-semibold ${activeTab === 'demo' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
          onClick={() => setActiveTab('demo')}
        >
          🎮 Guardrail Playground
        </button>
        {isAdmin ? (
          <>
            <button 
              type="button"
              className={`pb-2 px-4 font-semibold ${activeTab === 'admin' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
              onClick={() => setActiveTab('admin')}
            >
              ⚙️ Policy Manager
            </button>
            <button 
              type="button"
              className={`pb-2 px-4 font-semibold ${activeTab === 'tenants' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
              onClick={() => setActiveTab('tenants')}
            >
              🔗 Tenant → Domain
            </button>
          </>
        ) : (
          <span className="pb-2 px-4 text-sm text-gray-400 self-center">
            Admin tabs require an admin role
          </span>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === "tenants" && isAdmin ? (
        <div className="max-w-4xl space-y-6">
          <div className="bg-white p-5 rounded-lg border shadow-sm">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 border-b pb-2">
              Map tenant to PII domain
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              When callers omit <code className="bg-gray-100 px-1 rounded">domain</code> in{" "}
              <code className="bg-gray-100 px-1 rounded">POST /redact</code>, the service resolves the domain from{" "}
              <strong>X-Tenant-Id</strong> or the JWT <strong>tenant_id</strong> using this table.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 items-end flex-wrap">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-semibold text-gray-600 mb-1">Tenant ID</label>
                <input
                  type="text"
                  placeholder="e.g. tenant-uuid or slug"
                  className="w-full border rounded p-2 text-sm"
                  value={newMapTenantId}
                  onChange={(e) => setNewMapTenantId(e.target.value)}
                />
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-semibold text-gray-600 mb-1">PII domain</label>
                <select
                  className="w-full border rounded p-2 text-sm"
                  value={newMapDomainId}
                  onChange={(e) => setNewMapDomainId(e.target.value)}
                >
                  <option value="">— select domain —</option>
                  {allDomains.map((d) => (
                    <option key={d.domain_id} value={d.domain_id}>
                      {d.domain_id}
                      {d.is_active ? " (active)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => void handleSaveTenantMapping()}
                className="bg-blue-600 text-white font-semibold px-4 py-2 rounded hover:bg-blue-700 text-sm"
              >
                Save mapping
              </button>
              <button
                type="button"
                onClick={() => void fetchTenantMappings()}
                className="border border-gray-300 px-4 py-2 rounded text-sm hover:bg-gray-50"
              >
                Refresh list
              </button>
            </div>
          </div>

          <div className="bg-white p-5 rounded-lg border shadow-sm overflow-x-auto">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">
              Current mappings
            </h2>
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-2">Tenant ID</th>
                  <th className="p-2">Domain</th>
                  <th className="p-2">Updated</th>
                  <th className="p-2 w-24">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tenantMappings.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-gray-400">
                      No mappings yet — add one above or use Policy Manager to ensure domains exist.
                    </td>
                  </tr>
                ) : (
                  tenantMappings.map((row) => (
                    <tr key={row.tenant_id} className="border-b">
                      <td className="p-2 font-mono text-xs">{row.tenant_id}</td>
                      <td className="p-2 font-semibold">{row.domain_id}</td>
                      <td className="p-2 text-gray-500 text-xs">
                        {row.updated_at
                          ? new Date(row.updated_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="p-2">
                        <button
                          type="button"
                          onClick={() => void handleDeleteTenantMapping(row.tenant_id)}
                          className="text-red-600 hover:underline text-xs"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : activeTab === 'demo' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Column 1: Config & Input */}
          <div className="space-y-6">
            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">1. Configuration</h2>
              
              <label className="block text-sm font-semibold mb-1">Select Domain</label>
              <select className="w-full border rounded p-2 mb-4" value={selectedDomain} onChange={e => setSelectedDomain(e.target.value)}>
                {activeDomains.map(d => <option key={d} value={d}>{d.toUpperCase()}</option>)}
              </select>

              <label className="block text-sm font-semibold mb-1 text-blue-600">Enforcement Target</label>
              <select className="w-full border-blue-300 border rounded p-2 mb-4" value={target} onChange={e => setTarget(e.target.value)}>
                <option value="user">👤 User Response (UX-First)</option>
                <option value="storage">💾 Storage / Logs (Strict Mode)</option>
              </select>

              <label className="block text-sm font-semibold mb-1">Active Rules</label>
              <div className="max-h-48 overflow-y-auto space-y-2 text-sm">
                {activePolicyRules.map((r, i) => (
                  <div key={i} className="flex justify-between border-b pb-1">
                    <span>{r.entity_type}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${getActionBadgeColor(r.action)}`}>{r.action}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">2. Input Data</h2>
              <textarea 
                className="w-full border rounded p-3 h-32 text-sm" 
                value={inputText} onChange={e => setInputText(e.target.value)}
              />
              <button onClick={handleRedact} className="w-full mt-4 bg-blue-600 text-white font-bold py-2 rounded hover:bg-blue-700 transition">
                🛡️ Run Protection
              </button>
            </div>
          </div>

          {/* Column 2: Output & Evidence */}
          <div className="space-y-6">
            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">3. Secure Output</h2>
              <div className="bg-gray-50 border rounded p-4 font-mono text-sm min-h-[100px] mb-4">
                {outputText}
              </div>
              <div className="flex justify-between text-sm border-t pt-3">
                <span className="text-gray-500">Latency</span>
                <span className="bg-yellow-100 text-yellow-800 px-2 rounded font-bold">{latency} ms</span>
              </div>
            </div>

            <div className="bg-white p-5 rounded-lg border shadow-sm">
              <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">4. Evidence (Audit Store)</h2>
              <pre className="bg-gray-900 text-green-400 p-4 rounded text-xs overflow-auto max-h-[250px] font-mono">
                {jsonOutput}
              </pre>
            </div>
          </div>

          {/* Column 3: Trace Panel */}
          {showTrace && (
            <div className="bg-white rounded-lg border shadow-sm overflow-hidden flex flex-col h-full">
              <div className="bg-gray-800 text-white p-3 font-bold flex justify-between items-center text-sm">
                <span>🚦 Activity Log</span>
                <span className="bg-gray-600 px-2 rounded text-xs">LIVE TRACE</span>
              </div>
              <div className="flex-1 bg-gray-50 overflow-y-auto p-0">
                {traceLog.length === 0 ? (
                  <div className="p-4 text-center text-gray-400 text-sm">Waiting for request...</div>
                ) : (
                  traceLog.map((log, i) => (
                    <div key={i} className={`p-3 border-b border-l-4 ${log.status.includes('Fail') ? 'border-l-red-500 bg-red-50' : 'border-l-green-500 bg-white'}`}>
                      <div className="flex justify-between font-semibold text-sm">
                        <span>{log.status.includes('Fail') ? '❌' : '✅'} {log.step}</span>
                        <span className="text-gray-500 text-xs">{log.time_ms || 0} ms</span>
                      </div>
                      <div className="text-xs text-gray-600 mt-1">{log.details}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      ) : activeTab === "admin" && isAdmin ? (
        /* ADMIN PANE */
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Admin Column 1: Domains */}
          <div className="bg-white p-5 rounded-lg border shadow-sm flex flex-col h-[600px]">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2">1. Domain Inventory</h2>
            <div className="flex-1 overflow-y-auto space-y-2 mb-4">
              {allDomains.map(d => (
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
                  <button className="text-xs text-blue-600 hover:bg-blue-50 p-1 rounded" onClick={() => loadDomainConfig(d.domain_id)}>✏️</button>
                </div>
              ))}
            </div>
            <button 
              disabled={checkedDomains.size === 0}
              onClick={applyActiveDomains}
              className="w-full bg-gray-800 text-white font-bold py-2 rounded disabled:opacity-50 mb-4"
            >
              ✅ Apply Active Domains ({checkedDomains.size})
            </button>
            <div className="border-t pt-4">
              <input 
                type="text" placeholder="New Domain ID" 
                className="w-full border rounded p-2 text-sm mb-2"
                value={newDomainId} onChange={e => setNewDomainId(e.target.value)}
              />
              <button onClick={handleCreateDomain} className="w-full border border-gray-800 text-gray-800 font-bold py-1.5 rounded text-sm hover:bg-gray-50">
                + Create Scope
              </button>
            </div>
          </div>

          {/* Admin Column 2: Rules Config */}
          <div className="md:col-span-2 bg-white p-5 rounded-lg border shadow-sm h-[600px] flex flex-col">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b pb-2 flex justify-between items-center">
              <span>2. Configure Rules</span>
              {editingDomainId && <span className="bg-yellow-100 text-yellow-800 px-2 rounded normal-case tracking-normal">Editing: {editingDomainId}</span>}
            </h2>

            <div className="flex-1 overflow-y-auto border rounded bg-gray-50 p-2 mb-4">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-200">
                  <tr>
                    <th className="p-2">Entity</th>
                    <th className="p-2">Action</th>
                    <th className="p-2">Remove</th>
                  </tr>
                </thead>
                <tbody>
                  {editingRules.map((r, i) => (
                    <tr key={i} className="border-b bg-white">
                      <td className="p-2 font-bold">{r.entity_type}</td>
                      <td className="p-2"><span className="border bg-gray-100 px-2 rounded text-xs">{r.action}</span></td>
                      <td className="p-2">
                        <button onClick={() => removeRule(i)} className="text-red-500 hover:underline text-xs">Drop</button>
                      </td>
                    </tr>
                  ))}
                  {editingRules.length === 0 && (
                    <tr><td colSpan={3} className="text-center p-4 text-gray-400">No rules configured for this domain.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="border rounded p-4 mb-4 bg-white">
              <h6 className="text-sm font-bold text-blue-600 mb-3">Add Custom Rule</h6>
              <div className="grid grid-cols-12 gap-2 mb-2">
                <input type="text" placeholder="Entity (e.g., PASSPORT)" className="col-span-3 border rounded px-2 py-1 text-sm" value={newEntity} onChange={e => setNewEntity(e.target.value)} />
                <select className="col-span-3 border rounded px-2 py-1 text-sm" value={newAction} onChange={e => setNewAction(e.target.value)}>
                  <option>REDACT_TAG</option><option>MASK</option><option>HASH</option>
                </select>
                <div className="col-span-6 flex">
                  <input type="text" placeholder="AI Example (e.g., A1234567)" className="flex-1 border rounded-l px-2 py-1 text-sm" value={newExample} onChange={e => setNewExample(e.target.value)} />
                  <button onClick={generateRegex} className="bg-gray-200 border border-l-0 rounded-r px-3 text-sm hover:bg-gray-300">Gen Regex</button>
                </div>
              </div>
              <input type="text" placeholder="Generated Regex / Pattern" readOnly className="w-full border rounded px-2 py-1 text-sm bg-gray-100 font-mono mb-2" value={newRegex} />
              <button onClick={addCustomRule} className="w-full border border-blue-600 text-blue-600 py-1 rounded hover:bg-blue-50 text-sm font-semibold">
                + Add to Rule List
              </button>
            </div>

            <button onClick={saveConfig} className="w-full bg-green-600 text-white font-bold py-2 rounded hover:bg-green-700">
              💾 Save Configuration
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}