/**
 * User and permission listing (admin / tenant admin).
 */

import type { Permission, User } from "../../types/auth";
import { z } from "zod";
import { authUnwrappedSchema } from "../dto/authUnwrappedSchema";
import { permissionListSchema, userListItemSchema, userSchema } from "../dto/schemas/auth";
import { apiEndpoints } from "../apiEndpoints";
import { authValidatedRequest } from "./request";

const authPath = apiEndpoints.auth.paths;

export async function getAllUsers(): Promise<User[]> {
  return authValidatedRequest(
    authPath.usersInitial,
    authUnwrappedSchema(z.array(userListItemSchema)),
    { method: "GET" }
  );
}

export async function listUsersPage(offset: number, limit = 100): Promise<User[]> {
  return authValidatedRequest(
    authPath.usersPage(offset, limit),
    authUnwrappedSchema(z.array(userListItemSchema)),
    { method: "GET" }
  );
}

export async function getUserById(userId: string): Promise<User> {
  return authValidatedRequest(
    authPath.userById(userId),
    authUnwrappedSchema(userSchema),
    { method: "GET" }
  );
}

export async function getAllPermissions(): Promise<Permission[]> {
  const endpoints = [authPath.inferencePermissions, authPath.permissions, "/permissions"];
  for (const endpoint of endpoints) {
    try {
      const rows = await authValidatedRequest(
        endpoint,
        authUnwrappedSchema(permissionListSchema),
        { method: "GET" }
      );
      if (Array.isArray(rows) && rows.length > 0) {
        return rows;
      }
    } catch (err) {
      console.warn(`getAllPermissions failed for ${endpoint}:`, err);
    }
  }
  return [];
}
