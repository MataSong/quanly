import http from "./http";
import type { ApiEnvelope } from "./types";

export interface PermItem { zh: string; en: string; }
export interface PermGroup {
  label_zh: string;
  label_en: string;
  items: Record<string, PermItem>;
}
export type PermissionsRegistry = Record<string, PermGroup>;

export interface Role {
  id: number;
  name: string;
  description: string;
  permissions: string[];
  is_system: boolean;
  created_at: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  roles: number[];
  auth_source: "local" | "sso";
}

export interface Override {
  id: number;
  permission: string;
  effect: "grant" | "deny";
}

// GET /accounts/permissions/ returns {data: PermissionsRegistry}
export async function fetchPermissions(): Promise<PermissionsRegistry> {
  const r = await http.get<ApiEnvelope<PermissionsRegistry>>("/accounts/permissions/");
  return r.data.data ?? {};
}

export async function listRoles(): Promise<Role[]> {
  const r = await http.get<Role[]>("/accounts/roles/");
  return r.data;
}

export async function createRole(payload: Partial<Role>): Promise<Role> {
  const r = await http.post<Role>("/accounts/roles/", payload);
  return r.data;
}

export async function updateRole(id: number, payload: Partial<Role>): Promise<Role> {
  const r = await http.patch<Role>(`/accounts/roles/${id}/`, payload);
  return r.data;
}

export async function deleteRole(id: number): Promise<void> {
  await http.delete(`/accounts/roles/${id}/`);
}

export async function listUsers(): Promise<AdminUser[]> {
  const r = await http.get<AdminUser[]>("/accounts/users/");
  return r.data;
}

export async function createUser(payload: {
  username: string;
  email?: string;
  auth_source: "local" | "sso";
  password?: string;
  external_id?: string;
}): Promise<AdminUser> {
  const r = await http.post<AdminUser>("/accounts/users/", payload);
  return r.data;
}

export async function deleteUser(id: number): Promise<void> {
  await http.delete(`/accounts/users/${id}/`);
}

export async function setUserRoles(id: number, roleIds: number[]): Promise<void> {
  await http.put(`/accounts/users/${id}/roles/`, { role_ids: roleIds });
}

export async function setUserActive(id: number, isActive: boolean): Promise<void> {
  await http.post(`/accounts/users/${id}/set_active/`, { is_active: isActive });
}

export async function resetUserPassword(id: number, password: string): Promise<void> {
  await http.post(`/accounts/users/${id}/reset_password/`, { password });
}

export async function listOverrides(id: number): Promise<Override[]> {
  const r = await http.get<ApiEnvelope<Override[]>>(`/accounts/users/${id}/overrides/`);
  return r.data.data ?? [];
}

export async function addOverride(
  id: number,
  permission: string,
  effect: "grant" | "deny",
): Promise<void> {
  await http.post(`/accounts/users/${id}/overrides/`, { permission, effect });
}

export async function deleteOverride(userId: number, overrideId: number): Promise<void> {
  await http.delete(`/accounts/users/${userId}/overrides/${overrideId}/`);
}
