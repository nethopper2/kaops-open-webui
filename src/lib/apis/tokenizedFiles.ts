import { apiFetch } from '$lib/apis/private-ai/fetchClients';

export async function fetchDocxFiles() {
  return await apiFetch('/files', { query: { type: 'docx' } });
}

export async function fetchCsvFiles() {
  return await apiFetch('/files', { query: { type: 'csv' } });
} 