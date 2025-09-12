import { writable, get, type Writable, derived } from 'svelte/store';
import { getTokenizedFiles } from '$lib/apis/private-ai/sidekicks/token-replacer';
import { chatId } from '$lib/stores';

export type TokenFile = {
	fullPath: string;
	name: string;
	size: number;
	sourceName: string;
	lastModified: string; // timestamp
	metadata: { [key: string]: unknown };
};

// Holds the list of available tokenized files (fetched once per session lazily)
export const tokenizedFiles: Writable<TokenFile[]> = writable([]);
export const filesLoading: Writable<boolean> = writable(false);
export const filesFetched: Writable<boolean> = writable(false);

export const selectedTokenizedDocPath: Writable<string> = writable('');
export const isTokenizedDocSelected = derived(
	selectedTokenizedDocPath,
	($selectedTokenizedDocPath) => Boolean($selectedTokenizedDocPath)
);
export const selectedTokenizedDoc = derived(
	[tokenizedFiles, selectedTokenizedDocPath],
	([$files, $path]) => {
		return ($files ?? []).find((f) => String(f.fullPath) === String($path)) ?? null;
	}
);

// Manage which sub-view is shown within the token-replacer sidekick
export type TokenReplacerSubView = 'initial' | 'editValues';
export const currentTokenReplacerSubView: Writable<TokenReplacerSubView> = writable('editValues');

export async function ensureFilesFetched(): Promise<void> {
	if (get(filesFetched) || get(filesLoading)) return;
	filesLoading.set(true);
	try {
		const result = await getTokenizedFiles();
		const files = result?.data ?? [];

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
	selectedTokenizedDocPath.set('');
	currentTokenReplacerSubView.set('initial');
}

// Centralized chat change handling to avoid component lifecycle race conditions.
// This subscription runs at module load-time and persists across Pane/Drawer swaps.
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
			currentTokenReplacerSubView.set('editValues');
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

	// Starting a brand-new chat ('' -> someId): preserve the current selection; show actions
	if (prev === '' && newId !== '') {
		currentTokenReplacerSubView.set('editValues');
		return;
	}

	// Switching between existing chats (idA -> idB): clear per-chat state; show edit values
	if (prev !== '' && newId !== '' && newId !== prev) {
		resetTokenReplacerStores();
		currentTokenReplacerSubView.set('editValues');
		return;
	}
});
