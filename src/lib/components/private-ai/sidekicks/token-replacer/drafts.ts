// Token Replacer: lightweight draft persistence (no LocalStorage)
// Scoped strictly to the Token Replacer sidekick. Drafts are keyed by (chatId + modelId + tokenId).
// This keeps user input across component unmounts (e.g., closing the side panel) within a session
// and avoids any global/private-ai wide scope. Designed to be easily swapped to a REST-backed provider.

export type TokenReplacerDraft = {
  values: Record<string, string>;
  updatedAt: number;
};

// Provider interface to enable easy swap to REST API in the future
export type TokenReplacerDraftsProvider = {
  load: (
    chatId: string | null | undefined,
    modelId: string | null | undefined,
    tokenId: string | number | null | undefined
  ) => Promise<TokenReplacerDraft | null>;
  save: (
    chatId: string | null | undefined,
    modelId: string | null | undefined,
    tokenId: string | number | null | undefined,
    draft: TokenReplacerDraft
  ) => Promise<void>;
  clear: (
    chatId: string | null | undefined,
    modelId: string | null | undefined,
    tokenId: string | number | null | undefined
  ) => Promise<void>;
};

// In-memory implementation (no persistence across reloads)
// Shape: mem[chatId][modelId][tokenId] = draft
// This can be replaced by a REST-backed provider without changing call sites.

type MemStore = Record<string, Record<string, Record<string, TokenReplacerDraft>>>;
const memStore: MemStore = {};

function getKeys(
  chatId: string | null | undefined,
  modelId: string | null | undefined,
  tokenId: string | number | null | undefined
): { cId: string | null; mId: string | null; tId: string | null } {
  if (!chatId || !modelId || !tokenId) return { cId: null, mId: null, tId: null };
  return { cId: String(chatId), mId: String(modelId), tId: String(tokenId) };
}

const inMemoryProvider: TokenReplacerDraftsProvider = {
  async load(chatId, modelId, tokenId) {
    const { cId, mId, tId } = getKeys(chatId, modelId, tokenId);
    if (!cId || !mId || !tId) return null;
    return memStore[cId]?.[mId]?.[tId] ?? null;
  },
  async save(chatId, modelId, tokenId, draft) {
    const { cId, mId, tId } = getKeys(chatId, modelId, tokenId);
    if (!cId || !mId || !tId) return;
    const byChat = memStore[cId] ?? (memStore[cId] = {});
    const byModel = byChat[mId] ?? (byChat[mId] = {});
    byModel[tId] = draft;
  },
  async clear(chatId, modelId, tokenId) {
    const { cId, mId, tId } = getKeys(chatId, modelId, tokenId);
    if (!cId || !mId || !tId) return;
    const byChat = memStore[cId];
    if (!byChat) return;
    const byModel = byChat[mId];
    if (!byModel) return;
    if (byModel[tId]) {
      delete byModel[tId];
      if (Object.keys(byModel).length === 0) {
        delete byChat[mId];
      }
      if (Object.keys(byChat).length === 0) {
        delete memStore[cId];
      }
    }
  }
};

let provider: TokenReplacerDraftsProvider = inMemoryProvider;

// Allow swapping provider (e.g., to a REST client) without changing call sites.
export function setTokenReplacerDraftsProvider(p: TokenReplacerDraftsProvider) {
  provider = p ?? inMemoryProvider;
}

export async function loadTokenReplacerDraft(
  chatId: string | null | undefined,
  modelId: string | null | undefined,
  tokenId: string | number | null | undefined
): Promise<TokenReplacerDraft | null> {
  return provider.load(chatId, modelId, tokenId);
}

export async function saveTokenReplacerDraft(
  chatId: string | null | undefined,
  modelId: string | null | undefined,
  tokenId: string | number | null | undefined,
  draft: TokenReplacerDraft
): Promise<void> {
  return provider.save(chatId, modelId, tokenId, draft);
}

export async function clearTokenReplacerDraft(
  chatId: string | null | undefined,
  modelId: string | null | undefined,
  tokenId: string | number | null | undefined
): Promise<void> {
  return provider.clear(chatId, modelId, tokenId);
}
