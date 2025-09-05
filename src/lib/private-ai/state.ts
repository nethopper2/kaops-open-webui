// Centralized persistence for Private AI sidekick UI state.
// For now, this uses LocalStorage. Replace the implementations of
// loadPrivateAiSidekickState/savePrivateAiSidekickState with REST calls when ready.

export type PrivateAiSidekickCommonState = {
  // Which sidekick is this state for (e.g., 'private-ai-token-replacer')
  sidekickId: string;
};

export type TokenReplacerState = PrivateAiSidekickCommonState & {
  selectedTokenizedDocId?: string;
};

// Union of possible sidekick states; extend as more sidekicks are added
export type PrivateAiSidekickState = TokenReplacerState;

const STORAGE_KEY = 'private-ai:sidekick-state:v1';

function safeRead(): Record<string, Record<string, PrivateAiSidekickState>> {
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

function safeWrite(data: Record<string, Record<string, PrivateAiSidekickState>>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore write errors (e.g., storage disabled)
  }
}

// Key space: state[chatId][sidekickId] -> sidekickState
export async function loadPrivateAiSidekickState(
  chatId: string | null | undefined,
  sidekickId: string | null | undefined
): Promise<PrivateAiSidekickState | null> {
  if (!chatId || !sidekickId) return null;
  const store = safeRead();
  return store?.[chatId]?.[sidekickId] ?? null;
}

export async function savePrivateAiSidekickState(
  chatId: string | null | undefined,
  sidekickId: string | null | undefined,
  state: PrivateAiSidekickState
): Promise<void> {
  if (!chatId || !sidekickId) return;
  const store = safeRead();
  const byChat = store[chatId] ?? {};
  byChat[sidekickId] = state;
  store[chatId] = byChat;
  safeWrite(store);
}
