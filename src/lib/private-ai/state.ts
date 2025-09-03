// Centralized persistence for Private AI toolbar UI state.
// For now, this uses LocalStorage. Replace the implementations of
// loadPrivateAiToolbarState/savePrivateAiToolbarState with REST calls when ready.

export type PrivateAiToolbarCommonState = {
  // Which toolbar is this state for (e.g., 'private-ai-token-replacer')
  toolbarId: string;
};

export type TokenReplacerState = PrivateAiToolbarCommonState & {
  selectedTokenizedDocId?: string;
};

// Union of possible toolbar states; extend as more toolbars are added
export type PrivateAiToolbarState = TokenReplacerState;

const STORAGE_KEY = 'private-ai:toolbar-state:v1';

function safeRead(): Record<string, Record<string, PrivateAiToolbarState>> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') return parsed;
    return {};
  } catch {
    return {};
  }
}

function safeWrite(data: Record<string, Record<string, PrivateAiToolbarState>>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore write errors (e.g., storage disabled)
  }
}

// Key space: state[chatId][toolbarId] -> toolbarState
export async function loadPrivateAiToolbarState(
  chatId: string | null | undefined,
  toolbarId: string | null | undefined
): Promise<PrivateAiToolbarState | null> {
  if (!chatId || !toolbarId) return null;
  const store = safeRead();
  return store?.[chatId]?.[toolbarId] ?? null;
}

export async function savePrivateAiToolbarState(
  chatId: string | null | undefined,
  toolbarId: string | null | undefined,
  state: PrivateAiToolbarState
): Promise<void> {
  if (!chatId || !toolbarId) return;
  const store = safeRead();
  const byChat = store[chatId] ?? {};
  byChat[toolbarId] = state;
  store[chatId] = byChat;
  safeWrite(store);
}
