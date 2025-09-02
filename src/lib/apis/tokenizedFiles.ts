import { apiFetch } from '$lib/apis/private-ai/fetchClients';

export async function fetchDocxFiles() {
  return await apiFetch('/files', { query: { type: 'docx' } });
}

export async function fetchCsvFiles() {
  return await apiFetch('/files', { query: { type: 'csv' } });
}

export async function fetchFilePreview(type: 'docx' | 'csv', path: string) {
  const params: Record<string, string> = {};
  const res = await apiFetch(`/file/preview/${type}/${path}`, { params });
  // Return both preview and metadata
  return res;
} 