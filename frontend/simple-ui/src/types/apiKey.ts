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
  /** Present on create: true when the key was seeded with nothing left to spend. */
  budget_exhausted?: boolean;
  permissions: string[];
  expires_at?: string;
  is_active?: boolean;
  is_revoked?: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string | null;
  /** When the previous value stops working after a rotation; absent if never rotated. */
  rotated_key_expires_at?: string;
  /** The previous value, masked, while it still works; absent otherwise. */
  rotated_key?: string;
  /** When the current value alone was revoked during a rotation; absent while it works. */
  api_key_revoked_at?: string;
  /** When the key was last rotated (its current value issued); absent if never. */
  rotated_at?: string;
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
