export interface Rule {
  entity_type: string;
  action: string;
  config: Record<string, unknown>;
  custom_regex?: string;
}

export interface Domain {
  domain_id: string;
  is_active: boolean;
  description?: string | null;
}

export type PageTab = "admin" | "audit";

export type TenantDomainMappingRow = {
  tenant_id: string;
  domain_id: string;
  updated_at?: string;
};

export interface AuditLogRow {
  id: number;
  trace_id: string;
  tenant_id: string;
  domain_id: string;
  target_context: string;
  pii_count: number;
  processing_ms: number;
  trace_json: unknown;
  created_at: string | null;
}

export interface PiiManagementProps {
  isAdmin?: boolean;
}
