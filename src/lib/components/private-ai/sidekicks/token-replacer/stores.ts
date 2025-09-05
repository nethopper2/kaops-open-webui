import { writable, get, type Writable, derived } from 'svelte/store';
import { fetchDocxFiles } from '$lib/apis/tokenizedFiles';
import { chatId } from '$lib/stores';

export type TokenFile = { id: number | string; url: string; name?: string; [key: string]: unknown };

// Holds the list of available tokenized files (fetched once per session lazily)
export const tokenizedFiles: Writable<TokenFile[]> = writable([]);
export const filesLoading: Writable<boolean> = writable(false);
export const filesFetched: Writable<boolean> = writable(false);

export const selectedTokenizedDocId: Writable<string> = writable('');
export const isTokenizedDocSelected = derived(selectedTokenizedDocId, ($selectedTokenizedDocId) => Boolean($selectedTokenizedDocId));
export const selectedTokenizedDoc = derived([tokenizedFiles, selectedTokenizedDocId], ([$files, $id]) => {
  return ($files ?? []).find((f) => String(f.id) === String($id)) ?? null;
});

// Manage which sub-view is shown within the token-replacer sidekick
export type TokenReplacerSubView = 'initial' | 'actions' | 'editValues';
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

// Centralized chat change handling to avoid component lifecycle race conditions.
// This subscription runs at module load and persists across Pane/Drawer swaps.
let __prevChatId: string = '';
let __initializing = true;
chatId.subscribe((newIdRaw) => {
  const newId = newIdRaw || '';

  if (__initializing) {
    __prevChatId = newId;
    __initializing = false;
    // Normalize sub-view on initial value
    if (newId === '') {
      currentTokenReplacerSubView.set('initial');
    } else {
      currentTokenReplacerSubView.set('actions');
    }
    return;
  }

  const prev = __prevChatId || '';
  if (newId === prev) return; // no change

  __prevChatId = newId;

  // Leaving chat UI entirely
  if (newId === '') {
    resetTokenReplacerStores();
    currentTokenReplacerSubView.set('initial');
    return;
  }

  // Starting a brand-new chat ('' -> someId): preserve current selection; show actions
  if (prev === '' && newId !== '') {
    currentTokenReplacerSubView.set('actions');
    return;
  }

  // Switching between existing chats (idA -> idB): clear per-chat state; show actions
  if (prev !== '' && newId !== '' && newId !== prev) {
    resetTokenReplacerStores();
    currentTokenReplacerSubView.set('actions');
    return;
  }
});
