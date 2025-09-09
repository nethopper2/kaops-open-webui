import { apiFetch } from '$lib/apis/private-ai/fetchClients';

// Token Replacer specific APIs
export async function fetchTokenizedFiles() {
  return await apiFetch('/files/tokenized-documents', { query: {} });
}

export async function fetchFilePreview(type: 'docx' | 'csv', path: string) {
  const params: Record<string, string> = {};
  const res = await apiFetch(`/file/preview/${type}/${path}`, { params });
  // Return both preview and metadata
  return res;
}