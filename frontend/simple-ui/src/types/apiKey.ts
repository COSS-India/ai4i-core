/** Application-scoped API key (list / create contract). */
export interface ApiKeyRecord {
  id: number;
  key_name: string;
  /** Masked on list; full value only on create. */
  api_key?: string;
  application_id: string;
  application_name?: string;
  allocated_percentage: number | null;
  allocated_budget: number | null;
  permissions: string[];
  expires_at?: string;
  is_active?: boolean;
  is_revoked?: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string | null;
}

export interface ApiKeyApplicationGroup {
  application_id: string;
  api_keys: ApiKeyRecord[];
}

export interface ApiKeyGroupedListResult {
  groups: ApiKeyApplicationGroup[];
}

export interface CreateApiKeyPayload {
  key_name: string;
  permissions: string[];
  expires_days?: number;
  application_id: string;
  allocated_percentage: number;
}

export interface ListApiKeysParams {
  application_id?: string;
}
