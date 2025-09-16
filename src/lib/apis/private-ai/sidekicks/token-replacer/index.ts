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
export type TokenOccurrences = Record<string, string[]>;
export type TokenReplacementValuesResponse = {
	// All unique tokens discovered in the document (display order arbitrary unless coupled with occurrences)
	tokens: string[];
	// Latest values for each token
	values: Record<string, string>;
	// Map of token -> list of preview occurrence IDs in document order
	occurrences: TokenOccurrences;
};

// GET the available tokens and current values for a chat/model and selected document path
export async function getTokenReplacementValues(chatId: string, modelId: string) {
	const raw = await apiFetch<any>(
		`/tools/token-replacer/values/chat/${encodeURIComponent(chatId)}/model/${encodeURIComponent(modelId)}`
	);

	// New format example:
	// {
	//   tokens: [ { token: string, value: string, occurrenceIds: string[] }, ... ],
	//   ...metadata
	// }
	// Old formats (fallbacks) may include arrays of rows with `tokens` maps.
	const payload = (raw as any)?.data ?? raw;

	const tokens: string[] = [];
	const values: Record<string, string> = {};
	const occurrences: TokenOccurrences = {};

	if (payload && typeof payload === 'object' && Array.isArray((payload as any).tokens)) {
		// New schema detected
		for (const entry of (payload as any).tokens as any[]) {
			const t = String(entry?.token ?? '').trim();
			if (!t) continue;
			if (!tokens.includes(t)) tokens.push(t);
			const v = typeof entry?.value === 'string' ? entry.value : '';
			if (v && v.trim().length > 0) values[t] = v;
			const ids = Array.isArray(entry?.occurrenceIds) ? entry.occurrenceIds.filter((x: any) => typeof x === 'string') : [];
			if (ids.length > 0) occurrences[t] = ids;
		}
	} else if (Array.isArray(payload)) {
		// Legacy: array of rows with `tokens` maps
		const tokenSet = new Set<string>();
		for (const row of payload) {
			const m = row?.tokens ?? {};
			for (const k of Object.keys(m)) {
				tokenSet.add(k);
				const v = m[k];
				if (typeof v === 'string' && v.trim().length > 0) values[k] = v;
			}
		}
		for (const k of tokenSet) tokens.push(k);
	} else if (payload && typeof payload === 'object' && Array.isArray((payload as any).data)) {
		// Legacy: { data: [...] } with rows containing `tokens` map
		const tokenSet = new Set<string>();
		for (const row of (payload as any).data) {
			const m = row?.tokens ?? {};
			for (const k of Object.keys(m)) {
				tokenSet.add(k);
				const v = m[k];
				if (typeof v === 'string' && v.trim().length > 0) values[k] = v;
			}
		}
		for (const k of tokenSet) tokens.push(k);
	}

	const normalized: TokenReplacementValuesResponse = { tokens, values, occurrences };
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
