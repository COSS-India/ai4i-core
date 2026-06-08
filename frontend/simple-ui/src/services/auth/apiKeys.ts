/**
 * API key management endpoints.
 */

import type {
  APIKeyCreate,
  APIKeyListResponse,
  APIKeyResponse,
  AdminAPIKeyWithUserResponse,
} from "../../types/auth";
import { z } from "zod";
import { authUnwrappedSchema } from "../dto/authUnwrappedSchema";
import {
  adminApiKeyWithUserSchema,
  apiKeyListResponseSchema,
  apiKeyResponseSchema,
  createApiKeyResponseSchema,
  messageResponseSchema,
} from "../dto/schemas/auth";
import { apiEndpoints } from "../apiEndpoints";
import { buildApiKeyRevokePathTokens } from "../../utils/apiKeyUtils";
import { authValidatedRequest } from "./request";

const authPath = apiEndpoints.auth.paths;

export async function createApiKey(data: APIKeyCreate): Promise<APIKeyResponse> {
  return authValidatedRequest(
    authPath.apiKeys,
    authUnwrappedSchema(createApiKeyResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(data),
    }
  );
}

export async function createApiKeyForUser(
  data: APIKeyCreate & { user_id: string }
): Promise<APIKeyResponse> {
  const payload = {
    key_name: data.key_name,
    permissions: data.permissions,
    expires_days: data.expires_days,
    user_id: data.user_id,
  };
  return authValidatedRequest(
    authPath.apiKeys,
    authUnwrappedSchema(createApiKeyResponseSchema),
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function listApiKeys(): Promise<APIKeyListResponse> {
  const data = await authValidatedRequest(
    authPath.apiKeys,
    authUnwrappedSchema(apiKeyListResponseSchema),
    { method: "GET" }
  );
  return { api_keys: Array.isArray(data?.api_keys) ? data.api_keys : [] };
}

export async function listAllApiKeys(): Promise<AdminAPIKeyWithUserResponse[]> {
  return authValidatedRequest(
    authPath.apiKeysAll,
    authUnwrappedSchema(z.array(adminApiKeyWithUserSchema)),
    { method: "GET" }
  );
}

export async function revokeApiKey(apiKeyToken: string): Promise<{ message: string }> {
  const encoded = encodeURIComponent(apiKeyToken);
  return authValidatedRequest(
    `${authPath.apiKeys}/${encoded}`,
    authUnwrappedSchema(messageResponseSchema),
    { method: "DELETE" }
  );
}

export async function updateApiKey(
  apiKeyHex: string,
  updateData: {
    key_name?: string;
    permissions?: number[];
    expires_days?: number;
    is_active?: boolean;
  }
): Promise<APIKeyResponse> {
  const encoded = encodeURIComponent(apiKeyHex);
  return authValidatedRequest(
    `${authPath.apiKeys}/${encoded}`,
    authUnwrappedSchema(apiKeyResponseSchema),
    {
      method: "PATCH",
      body: JSON.stringify(updateData),
    }
  );
}

export async function revokeApiKeyRecord(key: APIKeyResponse): Promise<{ message: string }> {
  const tokens = buildApiKeyRevokePathTokens(key);
  if (!tokens.length) {
    throw new Error(
      "This API key cannot be revoked from the UI. Refresh the list or recreate the key."
    );
  }

  let lastError: unknown;
  for (const token of tokens) {
    try {
      return await revokeApiKey(token);
    } catch (error: unknown) {
      lastError = error;
      const status = (error as { status?: number })?.status;
      if (status === 404) {
        try {
          await updateApiKey(token, { is_active: false });
          return { message: "API key revoked." };
        } catch (patchError) {
          lastError = patchError;
        }
      }
      if (status === 400 || status === 404) continue;
      throw error;
    }
  }

  const message = lastError instanceof Error ? lastError.message : "Failed to revoke API key";
  throw new Error(message);
}
