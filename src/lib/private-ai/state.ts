// Centralized persistence for Private AI sidekick UI state.

import {
	getSidekickState,
	type PrivateAiSidekickState,
	putSidekickState
} from '$lib/apis/private-ai/sidekicks';

// Load sidekick UI state for a given chat+sidekick from the backend
export async function loadPrivateAiSidekickState(
	chatId: string | null | undefined,
	modelId: string | null | undefined
): Promise<PrivateAiSidekickState | null> {
	if (!chatId || !modelId) return null;
	try {
		// Expecting backend GET /sidekicks/state?chatId=...&modelId=...
		const res = await getSidekickState(chatId, modelId);

		if (res) {
			return res.stateData;
		}
	} catch {
		// Silently ignore to avoid breaking UI if backend not available
	}

	return null;
}

// Save sidekick UI state for a given chat+sidekick to the backend
export async function savePrivateAiSidekickState(
	chatId: string | null | undefined,
	modelId: string | null | undefined,
	state: PrivateAiSidekickState
): Promise<void> {
	if (!chatId || !modelId) return;
	try {
		// Expecting backend PUT /sidekicks/state with JSON body
		await putSidekickState(chatId, modelId, state);
	} catch {
		// Ignore persistence errors; UI should continue functioning
	}
}
