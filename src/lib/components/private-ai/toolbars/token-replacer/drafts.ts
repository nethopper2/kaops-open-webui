// Token Replacer: lightweight local draft persistence for replacement values
// Scoped strictly to the Token Replacer toolbar. Drafts are keyed by (chatId + docId).
// This keeps user input across component unmounts (e.g., closing the side panel)
// and avoids any global/private-ai wide scope.

export type TokenReplacerDraft = {
  values: Record<string, string>;
  updatedAt: number;
};

const DRAFTS_STORAGE_KEY = 'private-ai:token-replacer-drafts:v1';

type DraftsStore = Record<string, Record<string, TokenReplacerDraft>>; // drafts[chatId][docId]

function readDrafts(): DraftsStore {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') return parsed as DraftsStore;
    return {};
  } catch {
    return {};
  }
}

function writeDrafts(data: DraftsStore): void {
  try {
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

export async function loadTokenReplacerDraft(
  chatId: string | null | undefined,
  docId: string | number | null | undefined
): Promise<TokenReplacerDraft | null> {
  if (!chatId || !docId) return null;
  const store = readDrafts();
  const byChat = store[String(chatId)] ?? {};
  return byChat[String(docId)] ?? null;
}

export async function saveTokenReplacerDraft(
  chatId: string | null | undefined,
  docId: string | number | null | undefined,
  draft: TokenReplacerDraft
): Promise<void> {
  if (!chatId || !docId) return;
  const store = readDrafts();
  const cId = String(chatId);
  const dId = String(docId);
  const byChat = store[cId] ?? {};
  byChat[dId] = draft;
  store[cId] = byChat;
  writeDrafts(store);
}

export async function clearTokenReplacerDraft(
  chatId: string | null | undefined,
  docId: string | number | null | undefined
): Promise<void> {
  if (!chatId || !docId) return;
  const store = readDrafts();
  const cId = String(chatId);
  const dId = String(docId);
  const byChat = store[cId];
  if (!byChat) return;
  if (byChat[dId]) {
    delete byChat[dId];
    if (Object.keys(byChat).length === 0) {
      delete store[cId];
    }
    writeDrafts(store);
  }
}
