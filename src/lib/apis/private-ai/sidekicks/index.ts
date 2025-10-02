import { apiFetch } from '$lib/apis/private-ai/fetchClients';

export async function getSidekickState(chatId: string, modelId: string) {
	return await apiFetch<SidekickStateRecord>(`/sidekick/state/chat/${chatId}/model/${modelId}`);
}

export type PrivateAiSidekickState<T extends Record<string, unknown> = Record<string, unknown>> = T

export async function putSidekickState(
	chatId: string,
	modelId: string,
	state: PrivateAiSidekickState
) {
	await apiFetch('/sidekick/state', { method: 'PUT', body: { chatId, modelId, stateData: state } });
}

export type SidekickStateRecord = {
	chatId: string;
	modelId: string;
	stateData: PrivateAiSidekickState | null;
};
