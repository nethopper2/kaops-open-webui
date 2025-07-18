import { apiFetch } from '$lib/apis/private-ai/fetchClients';

export async function fetchDocxFiles() {
  return await apiFetch('/files', { query: { type: 'docx' } });
}

export async function fetchCsvFiles() {
  return await apiFetch('/files', { query: { type: 'csv' } });
}

export async function fetchFilePreview(type: 'docx' | 'csv' | 'mineral', path: string) {
  const params: Record<string, string> = {};
  let endpointType = type;
  if (type === 'mineral') {
    params.delimiter = '\\[\\[.*?\\]\\]';
    endpointType = 'docx';
  }
  const res = await apiFetch(`/file/preview/${endpointType}/${path}`, { params });
  // Return both preview and metadata
  return res;
} 