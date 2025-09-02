import { writable, get, type Writable, derived } from 'svelte/store';
import { fetchDocxFiles } from '$lib/apis/tokenizedFiles';

export type TokenFile = { id: number | string; url: string; name?: string; [key: string]: unknown };

// Holds the list of available tokenized files (fetched once per session lazily)
export const tokenizedFiles: Writable<TokenFile[]> = writable([]);
export const filesLoading: Writable<boolean> = writable(false);
export const filesFetched: Writable<boolean> = writable(false);

export const selectedTokenizedDocId: Writable<string> = writable('');
export const selectedTokenizedDoc = derived([tokenizedFiles, selectedTokenizedDocId], ([$files, $id]) => {
  return ($files ?? []).find((f) => String(f.id) === String($id)) ?? null;
});

// Manage which sub-view is shown within the token-replacer toolbar
export type TokenReplacerSubView = 'initial' | 'actions';
export const currentTokenReplacerSubView: Writable<TokenReplacerSubView> = writable('actions');

export async function ensureFilesFetched(): Promise<void> {
  if (get(filesFetched) || get(filesLoading)) return;
  filesLoading.set(true);
  try {
    const docxResult = await fetchDocxFiles();
    const files = (Array.isArray(docxResult) ? docxResult : (docxResult?.files ?? [])).map((file, id) => ({
      ...file,
      id
    }));
    tokenizedFiles.set(files);
    filesFetched.set(true);
  } finally {
    filesLoading.set(false);
  }
}

// Reset all token replacer stores when leaving the current chat UI
export function resetTokenReplacerStores(): void {
  tokenizedFiles.set([]);
  filesLoading.set(false);
  filesFetched.set(false);
  selectedTokenizedDocId.set('');
  currentTokenReplacerSubView.set('initial');
}
