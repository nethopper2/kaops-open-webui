// Centralized persistence for Private AI sidekick UI state.

import {
	getSidekickState,
	type PrivateAiSidekickState,
	putSidekickState
} from '$lib/apis/private-ai/sidekicks';

// Simple per-session memoization to prevent duplicate concurrent and rapid repeat loads
const inFlight = new Map<string, Promise<PrivateAiSidekickState | null>>();
const cache = new Map<string, PrivateAiSidekickState | null>();

function makeKey(chatId?: string | null, modelId?: string | null) {
	return `${chatId || ''}|${modelId || ''}`;
}

// Load sidekick UI state for a given chat+sidekick from the backend
export async function loadPrivateAiSidekickState(
	chatId: string | null | undefined,
	modelId: string | null | undefined,
	opts?: { force?: boolean }
): Promise<PrivateAiSidekickState | null> {
	if (!chatId || !modelId) return null;
	const key = makeKey(chatId, modelId);
	if (!opts?.force) {
		// Return cached result if available
		if (cache.has(key)) return cache.get(key) ?? null;
		// Return in-flight promise if already loading
		const inflight = inFlight.get(key);
		if (inflight) return inflight;
	}
	const p = (async () => {
		try {
			// Expecting backend GET /sidekicks/state?chatId=...&modelId=...
			const res = await getSidekickState(chatId, modelId);
			const state = res ? (res.stateData as PrivateAiSidekickState | null) : null;
			cache.set(key, state);
			return state;
		} catch {
			// Silently ignore to avoid breaking UI if backend not available
			return null;
		} finally {
			inFlight.delete(key);
		}
	})();
	inFlight.set(key, p);
	return p;
}

// Save sidekick UI state for a given chat+sidekick to the backend
export async function savePrivateAiSidekickState(
	chatId: string | null | undefined,
	modelId: string | null | undefined,
	state: PrivateAiSidekickState
): Promise<void> {
	if (!chatId || !modelId) return;
	const key = makeKey(chatId, modelId);
	try {
		// Expecting backend PUT /sidekicks/state with JSON body
		await putSidekickState(chatId, modelId, state);
		// Update cache on successful save so readers immediately see latest selection
		cache.set(key, state);
	} catch {
		// Ignore persistence errors; UI should continue functioning
	} finally {
		// Clear any in-flight promise for this key to allow fresh loads if needed
		inFlight.delete(key);
	}
}
