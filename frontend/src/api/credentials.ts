import http from "./http";

export interface Credential {
  id: number;
  env: "sim" | "live";
  label: string;
  api_key_masked: string;
  created_at: string;
}

export interface CreateCredentialPayload {
  env: "sim" | "live";
  label: string;
  api_key: string;
  secret: string;
  passphrase: string;
}

/** GET /credentials/ — list current user's credentials */
export async function listCredentials(): Promise<Credential[]> {
  const r = await http.get<Credential[]>("/credentials/");
  return r.data;
}

/** POST /credentials/ — create a new credential (plaintext fields encrypted server-side) */
export async function createCredential(payload: CreateCredentialPayload): Promise<Credential> {
  const r = await http.post<Credential>("/credentials/", payload);
  return r.data;
}

/** DELETE /credentials/{id}/ — delete a credential */
export async function deleteCredential(id: number): Promise<void> {
  await http.delete(`/credentials/${id}/`);
}
