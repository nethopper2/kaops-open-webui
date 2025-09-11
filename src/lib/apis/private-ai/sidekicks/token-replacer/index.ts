import { apiFetch } from '$lib/apis/private-ai/fetchClients';

// Token Replacer specific APIs
export async function getTokenizedFiles() {
	return await apiFetch('/tools/token-replacer/documents', { query: {} });
}

export async function getFilePreview(type: 'docx' | 'csv', path: string) {
	const params: Record<string, string> = {};
	return apiFetch(`/files/preview/${type}/${path}`, { params });
}

// Types for Token Replacer values API
export type TokenReplacementValue = { token: string; value: string };
export type TokenReplacementValuesResponse = {
	tokens: string[];
	values: Record<string, string>;
};

// GET the available tokens and current values for a chat/model and selected document path
export async function getTokenReplacementValues(chatId: string, modelId: string) {
	// The backend returns an object with metadata and a `data` array of rows,
	// where each row has a ` tokens ` map. We normalize it into { tokens, values }.
	const raw = await apiFetch<any>(
		`/tools/token-replacer/values/chat/${encodeURIComponent(chatId)}/model/${encodeURIComponent(modelId)}`
	);

	const wrapped = (raw as any)?.data ?? raw;

	// Collect all token keys from all rows (defensive union)
	const tokenSet = new Set<string>();
	if (Array.isArray(wrapped)) {
		for (const row of wrapped) {
			const m = row?.tokens ?? {};
			for (const k of Object.keys(m)) tokenSet.add(k);
		}
	} else if (wrapped && typeof wrapped === 'object' && Array.isArray(wrapped?.data)) {
		// Some servers double-wrap; handle { data: [...] }
		for (const row of wrapped.data) {
			const m = row?.tokens ?? {};
			for (const k of Object.keys(m)) tokenSet.add(k);
		}
	}

 // Build values map from server data if provided; prefer non-empty string values
	const tokens = Array.from(tokenSet);
	const values: Record<string, string> = {};

	const rows = Array.isArray(wrapped)
		? wrapped
		: (wrapped && typeof wrapped === 'object' && Array.isArray((wrapped as any).data))
		? (wrapped as any).data
		: [];

	for (const row of rows) {
		const m = row?.tokens ?? {};
		for (const [k, v] of Object.entries(m)) {
			if (typeof v === 'string' && v.trim().length > 0) {
				values[k] = v;
			}
		}
	}

	const normalized: TokenReplacementValuesResponse = { tokens, values };
	return normalized;
}

// PUT updated values for the tokens for a chat/model and selected document path
export async function putTokenReplacementValues(
	chatId: string,
	modelId: string,
	values: TokenReplacementValue[]
) {
	// Build maps the backend expects.
	const tokens: Record<string, string> = {};
	for (const { token, value } of values) {
		const t = String(token);
		const v = String(value ?? '');
		if (t.trim().length > 0) tokens[t] = v;
	}

	return apiFetch<any>(
		`/tools/token-replacer/values/chat/${encodeURIComponent(chatId)}/model/${encodeURIComponent(modelId)}`,
		{ method: 'PUT', body: { tokens } }
	);
}
