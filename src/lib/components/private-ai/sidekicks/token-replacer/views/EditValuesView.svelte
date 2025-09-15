<script lang="ts">
import { getContext, onDestroy, onMount } from 'svelte';
import { toast } from 'svelte-sonner';
import { ensureFilesFetched, selectedTokenizedDoc, selectedTokenizedDocPath } from '../stores';
import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
import { appHooks } from '$lib/utils/hooks';
import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
import { chatId, currentSelectedModelId } from '$lib/stores';
import {
	getTokenReplacementValues,
	putTokenReplacementValues,
	type TokenReplacementValue
} from '$lib/apis/private-ai/sidekicks/token-replacer';
import {
	clearTokenReplacerDraft,
	loadTokenReplacerDraft,
	saveTokenReplacerDraft,
	type TokenReplacerDraft
} from '../drafts';
import Spinner from '$lib/components/common/Spinner.svelte';
import Eye from '$lib/components/icons/Eye.svelte';

const i18n = getContext('i18n');

function openPreviewPanel() {
	const file = $selectedTokenizedDoc;
	if (file) {
		appHooks.callHook('chat.overlay', {
			action: 'open',
			title: $i18n.t('Preview'),
			component: TokenizedDocPreview,
			props: { file, previewType: 'docx' }
		});
		isPreviewOpen = true;
	}
}

function onPreviewTokenClick(idx: number, token: string) {
	// Placeholder token ids: nh-token-1, nh-token-2, ...
	const id = `nh-token-${idx + 1}`;
	const v = (values[token] ?? '').trim();
	const s = (savedValues[token] ?? '').trim();
	const state: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
	appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state });
	lastPreviewSelection = { id, state };
	lastPreviewToken = token;
}

// Stubbed data types
type Token = string;
type ReplacementValues = Record<string, string>;

// Prevent re-saving drafts during certain lifecycle windows (e.g., right after successful submit)
let suppressDraftPersistence = false;

let isLoading = true;
let isSubmitting = false;
let loadError: string | null = null;
let submitError: string | null = null;
let submitSuccess = false;

// Local state
let tokens: Token[] = [];
// values = current editable values (may include drafts)
let values: ReplacementValues = {};
// savedValues = last known server-saved values from GET or after successful PUT
let savedValues: ReplacementValues = {};
let searchQuery = '';
let showConfirm = false;
let showGenerateConfirm = false;

// Track if the TokenizedDocPreview overlay is open
let isPreviewOpen = false;
let removeOverlayHook: (() => void) | null = null;
let removePreviewClosedHook: (() => void) | null = null;
// Track the last previewed token selection to update highlight state on edits
let lastPreviewSelection: { id: string; state: 'draft' | 'saved' } | null = null;
let lastPreviewToken: string | null = null;

// Local overlay for token occurrences
let isTokenOverlayOpen = false;
let overlayToken: string | null = null;
let overlayTokenIndex = -1; // index in filteredTokens when opened
let overlayOccurrences: string[] = [];
let overlayCurrentIdx = 0;

$: overlayState = overlayToken ? computeTokenState(overlayToken) : 'saved';

function onOverlayFocus() {
	selectOverlayOccurrence(overlayCurrentIdx);
}

function onOverlayInput(e: Event) {
	if (!overlayToken) return;
	const target = e.currentTarget as HTMLInputElement;
	const v = target.value;
	updateValue(overlayToken, v);
	if (isPreviewOpen) {
		const id = overlayOccurrences[overlayCurrentIdx];
		const newState = computeTokenState(overlayToken, v);
		appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
		lastPreviewSelection = { id, state: newState };
		lastPreviewToken = overlayToken;
	}
}

function computeTokenState(token: string, valueOverride?: string): 'draft' | 'saved' {
	const v = ((valueOverride ?? values[token]) ?? '').trim();
	const s = (savedValues[token] ?? '').trim();
	return v === s ? 'saved' : 'draft';
}

function selectOverlayOccurrence(idx: number) {
	if (!overlayToken || !isPreviewOpen) return;
	overlayCurrentIdx = Math.max(0, Math.min(idx, overlayOccurrences.length - 1));
	const id = overlayOccurrences[overlayCurrentIdx];
	const state = computeTokenState(overlayToken);
	appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state });
	lastPreviewSelection = { id, state };
	lastPreviewToken = overlayToken;
}

function openTokenOverlay(i: number, token: string) {
	overlayToken = token;
	overlayTokenIndex = i;
	// Placeholder: single occurrence id matching existing preview id convention
	overlayOccurrences = [`nh-token-${i + 1}`];
	isTokenOverlayOpen = true;
	// On open, highlight the first occurrence in the preview if open
	if (isPreviewOpen) {
		selectOverlayOccurrence(0);
	}
}

function closeTokenOverlay() {
	isTokenOverlayOpen = false;
}

function gotoPrevOccurrence() {
	if (overlayOccurrences.length <= 1) return;
	const next = (overlayCurrentIdx - 1 + overlayOccurrences.length) % overlayOccurrences.length;
	selectOverlayOccurrence(next);
}

function gotoNextOccurrence() {
	if (overlayOccurrences.length <= 1) return;
	const next = (overlayCurrentIdx + 1) % overlayOccurrences.length;
	selectOverlayOccurrence(next);
}

// Sticky helpers for measuring header height
let headerEl: HTMLDivElement | null = null;
let headerHeight = 0;
let headerRO: ResizeObserver | null = null;
let headerResizeHandler: (() => void) | null = null;

function updateHeaderHeight() {
	headerHeight = headerEl?.offsetHeight ?? 0;
}

// Derived counts and stats
$: totalTokens = tokens.length;
$: providedCount = tokens.reduce((acc, t) => {
	const v = (values[t] ?? '').trim();
	const s = (savedValues[t] ?? '').trim();
	return v.length > 0 && v === s ? acc + 1 : acc;
}, 0);
$: emptyCount = tokens.reduce((acc, t) => (((values[t] ?? '').trim().length === 0) ? acc + 1 : acc), 0);
$: draftCount = tokens.reduce((acc, t) => ((values[t] ?? '').trim() !== (savedValues[t] ?? '').trim() ? acc + 1 : acc), 0);
$: progressPercent = totalTokens > 0 ? Math.round((providedCount / totalTokens) * 100) : 0;

// Build confirmation message (markdown supported by ConfirmDialog)
$: confirmMessage = `${$i18n.t('You are about to submit all token/value pairs for the selected document.')}<br><br>` +
	`${$i18n.t('Tokens total')}: <b>${totalTokens}</b><br>` +
	`${$i18n.t('Replacement values provided')}: <b>${providedCount}</b><br>` +
	`${$i18n.t('Replacement values empty')}: <b>${emptyCount}</b><br><br>` +
	`${$i18n.t('All tokens will be submitted, including those not currently visible due to search filters.')}<br><br>` +
	`${$i18n.t('Do you want to continue?')}`;

// Load tokens and values from API
async function loadTokensAndValues(): Promise<{ tokens: Token[]; values: ReplacementValues }> {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	if (!cId || !mId) {
		throw new Error('Missing context: chat or model');
	}
	const res = await getTokenReplacementValues(cId, mId);
	const data = (res as any)?.data ?? res;
	const tokensFromApi: string[] = data?.tokens ?? [];
	const valuesFromApi: Record<string, string> = data?.values ?? {};
	return { tokens: tokensFromApi, values: valuesFromApi };
}

// Submit replacement values to API
async function submitReplacementValues(payload: { token: string; value: string }[]): Promise<void> {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	const dPath = $selectedTokenizedDocPath as string | null;
	if (!cId || !mId || !dPath) {
		throw new Error('Missing context: chat, model, or document path');
	}
	// Filter to TokenReplacementValue type explicitly
	const valuesToSend: TokenReplacementValue[] = payload.map((p) => ({
		token: String(p.token),
		value: String(p.value ?? '')
	}));
	await putTokenReplacementValues(cId, mId, valuesToSend);
}

// Trigger generation of the replacement document via app hook
async function handleGenerate() {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	const dPath = $selectedTokenizedDocPath as string | null;
	if (!cId || !mId || !dPath) {
		toast.error($i18n.t('Missing context: chat, model, or document path'));
		return;
	}
	let dismiss: (() => void) | undefined;
	try {
		// TODO: call the REST api via a new function in `src/lib/apis/private-ai/sidekicks/token-replacer/index.ts`
		dismiss = toast.success($i18n.t('TODO: Generation requested'));
	} catch (e) {
		console.error(e);
		toast.error($i18n.t('Failed to start generation'));
	} finally {
		try {
			dismiss && dismiss();
		} catch {
		}
	}
}

function onGenerateClick() {
	if (draftCount > 0) {
		showGenerateConfirm = true;
	} else {
		void handleGenerate();
	}
}

async function confirmSaveThenGenerate() {
	await handleSubmit();
	// Only proceed to generate if submission didn't error out
	if (!submitError) {
		await handleGenerate();
	}
}

function proceedGenerateWithoutSaving() {
	void handleGenerate();
}

// Derived filtered tokens with an optional "needs value" filter
let isOnlyNeedingValues = true;
$: query = searchQuery.trim().toLowerCase();
$: filteredTokens = tokens
	// Only hide rows that already have a value SAVED on the server.
	.filter((t) => (isOnlyNeedingValues ? !(typeof savedValues[t] === 'string' && savedValues[t].trim().length > 0) : true))
	.filter((t) => (query ? t.toLowerCase().includes(query) : true));

function updateValue(token: string, value: string) {
	suppressDraftPersistence = false; // user changed something; allow drafts to persist again
	values = { ...values, [token]: value };
	persistDraftDebounced();
}

function handleInput(token: string, id?: string) {
	return (e: Event) => {
		const target = e.currentTarget as HTMLInputElement;
		updateValue(token, target.value);
		// If this token is currently selected in preview, update highlight state when it flips.
		if (isPreviewOpen && id && lastPreviewSelection?.id === id) {
			const v = (target.value ?? '').trim();
			const s = (savedValues[token] ?? '').trim();
			const newState: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
			if (lastPreviewSelection.state !== newState) {
				appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
				lastPreviewSelection.state = newState;
			}
		}
	};
}

function handleClearTokenToggle(token: string, id?: string) {
	return (e: Event) => {
		const target = e.currentTarget as HTMLInputElement;
		if (target.checked) {
			// Clearing the value marks it as cleared. We still submit an empty string.
			updateValue(token, '');
			if (isPreviewOpen && id && lastPreviewSelection?.id === id) {
				const v = ''.trim();
				const s = (savedValues[token] ?? '').trim();
				const newState: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
				if (lastPreviewSelection.state !== newState) {
					appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
					lastPreviewSelection.state = newState;
				}
			}
		}
	};
}

function getInputId(token: string): string {
	return `input-${token.replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase().slice(0, 64)}`;
}

function getContextIds() {
	const cId = $chatId as string | null;
	const dId = $selectedTokenizedDocPath as string | null;
	return { cId, dId };
}

function mergeDraftValues(base: ReplacementValues, draftVals: Record<string, string> | undefined, allowedTokens: string[]): ReplacementValues {
	if (!draftVals) return base;
	const allowed = new Set(allowedTokens);
	const filtered: ReplacementValues = {};
	for (const [k, v] of Object.entries(draftVals)) {
		if (allowed.has(k)) {
			filtered[k] = v ?? '';
		}
	}
	// Important: API (base) takes precedence over drafts on conflict.
	// Draft values are used only for tokens that are not provided by the API.
	return { ...filtered, ...base };
}

let saveTimeout: ReturnType<typeof setTimeout> | null = null;
const DEBOUNCE_MS = 250;

async function persistDraftNow() {
	if (suppressDraftPersistence) return;
	const { cId, dId } = getContextIds();
	if (!cId || !dId) return;
	// If no non-empty values, clear any existing draft instead of saving empties
	const hasAny = tokens.some((t) => (values[t]?.trim()?.length ?? 0) > 0);
	if (!hasAny) {
		await clearTokenReplacerDraft(cId, dId);
		return;
	}
	const draft: TokenReplacerDraft = { values, updatedAt: Date.now() };
	await saveTokenReplacerDraft(cId, dId, draft);
}

function persistDraftDebounced() {
	if (saveTimeout) clearTimeout(saveTimeout);
	saveTimeout = setTimeout(() => {
		persistDraftNow();
	}, DEBOUNCE_MS);
}

async function handleSubmit() {
	submitError = null;
	submitSuccess = false;
	isSubmitting = true;
	const dismiss = toast.info($i18n.t('Submitting replacement values...'));
	try {
		// Build payload from ALL tokens, not only filtered ones
		const payload = tokens.map((t) => ({ token: t, value: values[t] ?? '' }));
		await submitReplacementValues(payload);
		// On success, server-saved values now match local edits
		savedValues = { ...values };
		submitSuccess = true;
		suppressDraftPersistence = true; // prevent re-saving this session unless user edits again
		// If a token is currently selected in preview, ensure its highlight reflects saved state now
		if (isPreviewOpen && lastPreviewSelection && lastPreviewToken) {
			const newState: 'draft' | 'saved' = 'saved';
			if (lastPreviewSelection.state !== newState) {
				appHooks.callHook('private-ai.token-replacer.preview.select-token', {
					id: lastPreviewSelection.id,
					state: newState
				});
				lastPreviewSelection.state = newState;
			}
		}
		// Clear the saved draft on successful submit so future sessions start fresh
		const { cId, dId } = getContextIds();
		if (cId && dId) {
			await clearTokenReplacerDraft(cId, dId);
		}
		toast.success($i18n.t('🎉 Replacement values submitted!'));
	} catch (e) {
		console.error(e);
		submitError = $i18n.t('Failed to submit replacement values.');
		toast.error(submitError);
	} finally {
		isSubmitting = false;
		if (dismiss && typeof dismiss === 'function') {
			try {
				dismiss();
			} catch {
			}
		}
	}
}

onMount(async () => {
	// Track overlay open/close to show preview buttons only when preview is open
	try {
		const overlayHandler = (params: { action: 'open' | 'close' | 'update'; title?: string; component?: any }) => {
			if (params.action === 'open') {
				isPreviewOpen = params.component === TokenizedDocPreview;
			} else if (params.action === 'close') {
				isPreviewOpen = false;
			}
		};
		appHooks.hook('chat.overlay', overlayHandler);
		removeOverlayHook = () => {
			try {
				appHooks.removeHook('chat.overlay', overlayHandler);
			} catch {
			}
		};
	} catch {
	}
	// Also respond to a direct preview-closed notification from the preview component
	try {
		const previewClosedHandler = () => {
			isPreviewOpen = false;
			isTokenOverlayOpen = false;
		};
		appHooks.hook('private-ai.token-replacer.preview.closed', previewClosedHandler);
		removePreviewClosedHook = () => {
			try {
				appHooks.removeHook('private-ai.token-replacer.preview.closed', previewClosedHandler);
			} catch {
			}
		};
	} catch {
	}
	// Ensure the list of tokenized files is loaded so the selected document summary can resolve on refresh
	try {
		await ensureFilesFetched();
	} catch {
	}
	// Measure header height and watch for changes
	updateHeaderHeight();
	try {
		headerRO = new ResizeObserver(() => updateHeaderHeight());
		if (headerEl) headerRO.observe(headerEl);
	} catch {
	}
	headerResizeHandler = () => updateHeaderHeight();
	window.addEventListener('resize', headerResizeHandler);

	isLoading = true;
	loadError = null;
	try {
		const { tokens: tk, values: vals } = await loadTokensAndValues();
		tokens = tk;
		// Track server-saved values separately from editable values
		savedValues = vals;
		let merged = vals;
		const { cId, dId } = getContextIds();
		if (cId && dId) {
			const draft = await loadTokenReplacerDraft(cId, dId);
			if (draft?.values) {
				merged = mergeDraftValues(vals, draft.values, tk);
			}
		}
		values = merged;
	} catch (e) {
		console.error(e);
		loadError = $i18n.t('Failed to load tokens.');
	} finally {
		isLoading = false;
	}
});

onDestroy(() => {
	if (saveTimeout) {
		clearTimeout(saveTimeout);
		saveTimeout = null;
	}
	// Cleanup header observers/listeners
	try {
		headerRO?.disconnect();
	} catch {
	}
	headerRO = null;
	if (headerResizeHandler) {
		window.removeEventListener('resize', headerResizeHandler);
		headerResizeHandler = null;
	}
	// Remove overlay hook listener
	try {
		removeOverlayHook && removeOverlayHook();
	} catch {
	}
	// Persist the latest state when the component is destroyed (e.g., panel closes)
	void persistDraftNow();
});
</script>

<div class="flex flex-col w-full items-stretch justify-start">
	<!-- Header -->
	<div
		bind:this={headerEl}
		class="px-4 py-2 sticky top-0 bg-white dark:bg-gray-900 z-20">
		<div class="flex items-center justify-between">
			<div class="hidden sm:flex items-center gap-1 text-[11px] text-gray-700 dark:text-gray-300">
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 border border-green-300/70 dark:border-green-700/60 text-green-800 dark:text-green-300">
					{$i18n.t('Complete')}: {providedCount}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 border border-amber-300/70 dark:border-amber-700/60 text-amber-800 dark:text-amber-300">
					{$i18n.t('Incomplete')}: {emptyCount}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800/50 border border-gray-300/70 dark:border-gray-700/60 text-gray-800 dark:text-gray-200">
					{$i18n.t('Total')}: {totalTokens}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 border border-amber-300/70 dark:border-amber-700/60 text-amber-800 dark:text-amber-300">
					{$i18n.t('Drafts')}: {draftCount}
				</span>
			</div>
		</div>
		<div class="mt-1 w-full h-1.5 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden" role="progressbar"
				 aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPercent}
				 aria-label={$i18n.t('Completion progress')}>
			<div class="h-full bg-green-500 dark:bg-green-400 transition-[width] duration-300"
					 style={`width: ${progressPercent}%`}></div>
		</div>
	</div>

	<!-- Content area container (page scroll) -->
	<div class="relative">
		<!-- Selected document summary (non-sticky) -->
		<div class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
			<SelectedDocumentSummary on:preview={openPreviewPanel} />
		</div>

		<!-- Overlay scope wrapper: covers from below SelectedDocumentSummary -->
		<div class="relative">
			<!-- Search and filtering (sticky within scroll container) -->

			<!-- Content area -->
			{#if isTokenOverlayOpen && overlayToken}
				<!-- Token occurrences overlay (scoped within EditValuesView search+content area) -->
				<div
					class="sticky z-30 bg-gray-50 dark:bg-gray-900 border-l border-r border-gray-200 dark:border-gray-800 overflow-y-auto"
					style={`top: ${headerHeight}px; height: calc(100vh - ${headerHeight}px); min-height: calc(100vh - ${headerHeight}px);`}>
					<div class="p-3 sm:p-4">
						<div class="flex items-start justify-between gap-3 mb-3">
							<div class="space-y-1">
								<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Token')}</div>
								<div
									class="text-sm font-semibold text-gray-800 dark:text-gray-100 break-words whitespace-pre-wrap">{overlayToken}</div>
								<div class="text-xs text-gray-600 dark:text-gray-300">{$i18n.t('Occurrences')}:
									{overlayOccurrences.length}</div>
							</div>
							<button type="button"
											class="inline-flex items-center justify-center h-8 w-8 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
											aria-label={$i18n.t('Close')} on:click={closeTokenOverlay}>
								<span aria-hidden="true">✕</span>
							</button>
						</div>

						<!-- Navigation -->
						<div class="flex flex-wrap items-center gap-2 mb-3">
							<button type="button"
											class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 text-xs text-gray-700 dark:text-gray-300 disabled:opacity-50"
											on:click={gotoPrevOccurrence} disabled={overlayOccurrences.length <= 1}>
								{$i18n.t('Prev')}
							</button>
							<button type="button"
											class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 text-xs text-gray-700 dark:text-gray-300 disabled:opacity-50"
											on:click={gotoNextOccurrence} disabled={overlayOccurrences.length <= 1}>
								{$i18n.t('Next')}
							</button>
							<div class="flex flex-wrap items-center gap-1">
								{#each overlayOccurrences as occId, idx}
									<button type="button"
													class={`px-2 py-1 rounded border text-xs ${idx === overlayCurrentIdx ? 'bg-gray-200 dark:bg-gray-800 border-gray-400 dark:border-gray-600 text-gray-900 dark:text-gray-100' : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
													on:click={() => selectOverlayOccurrence(idx)}>
										{idx + 1}
									</button>
								{/each}
							</div>
						</div>

						<!-- Synced input -->
						<div class="space-y-2">
							<label for="overlay-input"
										 class="block text-xs text-gray-600 dark:text-gray-300">{$i18n.t('Replacement value')}</label>
							<input id="overlay-input"
										 class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 ${overlayState === 'draft' ? 'ring-1 ring-amber-400 border-amber-400 dark:ring-amber-500 dark:border-amber-500' : ''}`}
										 type="text" placeholder={$i18n.t('Replacement value')}
										 value={overlayToken ? (values[overlayToken] ?? '') : ''} on:focus={onOverlayFocus}
										 on:input={onOverlayInput} autocomplete="off" />
						</div>
					</div>
				</div>
			{/if}

			<div
				class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 sticky bg-white dark:bg-gray-900 z-10 shadow"
				style={`top: ${headerHeight}px`}>
				<div class="flex items-center justify-between gap-2 mb-1">
					<label class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300 select-none">
						<input
							type="checkbox"
							class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
							bind:checked={isOnlyNeedingValues}
						/>
						<span>{$i18n.t('Hide completed')}</span>
					</label>
					<button
						class="px-2 py-1 rounded bg-gray-700 text-xs text-white hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-gray-700 dark:hover:bg-gray-800 text-nowrap"
						disabled={isLoading || isSubmitting || tokens.length === 0}
						on:click={onGenerateClick}
					>
						{$i18n.t('Generate Document')}
					</button>
				</div>
				<input
					id="token-search"
					class="w-full px-3 py-2 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
					type="text"
					bind:value={searchQuery}
					placeholder={$i18n.t('Type to filter tokens...')}
					autocomplete="off"
					spellcheck={false}
				/>
			</div>


			<div class="relative px-4 py-2 pb-24 space-y-3">
				{#if isLoading}
					<div class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300" aria-live="polite">
						<Spinner />{$i18n.t('Loading tokens...')}</div>
				{:else if loadError}
					<div class="text-sm text-red-600 dark:text-red-400" role="alert">{loadError}</div>
				{:else}
					{#if filteredTokens.length === 0}
						<div class="text-sm text-gray-600 dark:text-gray-300">
							{#if isOnlyNeedingValues}
								{$i18n.t('No tokens need a value for the current search.')}
							{:else}
								{$i18n.t('No tokens match your search.')}
							{/if}
						</div>
					{:else}
						<div class="space-y-4">
							{#each filteredTokens as token, i}
								<div class="grid grid-cols-1 lg:grid-cols-3 gap-2 lg:gap-4 items-start">
									<div
										class="lg:col-span-1 text-[11px] lg:text-xs font-semibold text-gray-800 dark:text-gray-200 break-words whitespace-pre-wrap select-text">
										<div class="flex items-start gap-1">
											<span class="break-words whitespace-pre-wrap">{token}</span>
										</div>
									</div>
									<div class="lg:col-span-2">
										{#key token}
											<div class="flex flex-col gap-1">
												<div class="flex items-start gap-2">
													<input
														id={getInputId(token)}
														class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 ${((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? 'ring-1 ring-amber-400 border-amber-400 dark:ring-amber-500 dark:border-amber-500' : ''}`}
														type="text"
														placeholder={$i18n.t('Replacement value')}
														aria-label={$i18n.t('Replacement value')}
														aria-describedby={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? `${getInputId(token)}-draft` : undefined}
														value={values[token] ?? ''}
														on:focus={() => onPreviewTokenClick(i, token)}
														on:input={handleInput(token, `nh-token-${i + 1}`)}
														autocomplete="off"
													/>
													{#if isPreviewOpen}
														<button
															type="button"
															class="inline-flex items-center justify-center self-start h-7 w-7 mt-0.5 rounded border border-gray-300 dark:border-gray-700 text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
															on:click={() => openTokenOverlay(i, token)}
															aria-label={$i18n.t('Open token details')}
															title={$i18n.t('Open token details')}>
															<Eye class="h-4 w-4" />
														</button>
													{/if}
												</div>
												<div class="flex items-center gap-2">
													<label
														class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300 select-none">
      								<input
      									type="checkbox"
      									class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
      									checked={(values[token] ?? '') === ''}
      									disabled={(values[token] ?? '') === ''}
      									title={(values[token] ?? '') === '' ? $i18n.t('Enter a value to uncheck') : undefined}
      									on:change={handleClearTokenToggle(token, `nh-token-${i + 1}`)}
      								/>
      								<span>{$i18n.t('Clear')}</span>
													</label>
													{#if (values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()}
														<div id={`${getInputId(token)}-draft`}
																 class="text-[10px] inline-flex items-center gap-1 text-amber-700 dark:text-amber-300">
													<span
														class="inline-block px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-700">{$i18n.t('Draft')}</span>
															<span
																class="sr-only">{$i18n.t('Value differs from the last saved value and is not yet saved.')}</span>
														</div>
													{/if}
												</div>
											</div>
										{/key}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>

	<!-- Submit bar (sticky bottom) -->
	<div
		class="px-4 py-3 border-t border-gray-200 dark:border-gray-800 sticky bottom-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-20">
		<div class="flex items-center justify-between gap-3">
			<div class="text-xs text-gray-600 dark:text-gray-400">
				{#if isSubmitting}
					{$i18n.t('Submitting...')}
				{:else if submitSuccess}
          <span class="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
            {$i18n.t('🎉 Replacement values submitted!')}
          </span>
				{:else}
					{$i18n.t('Provide replacement values and submit when ready.')}
				{/if}
			</div>
			<div class="flex items-center gap-2">
				<button
					class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600 text-nowrap"
					disabled={isLoading || isSubmitting || tokens.length === 0 || draftCount === 0}
					on:click={() => (showConfirm = true)}
				>
					{$i18n.t('Submit')}
				</button>
			</div>
		</div>
		{#if submitError}
			<div class="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">{submitError}</div>
		{/if}
	</div>
</div>


<ConfirmDialog
	bind:show={showConfirm}
	title={$i18n.t('Confirm submission')}
	message={confirmMessage}
	cancelLabel={$i18n.t('Cancel')}
	confirmLabel={$i18n.t('Submit All')}
	onConfirm={handleSubmit}
/>

<ConfirmDialog
	bind:show={showGenerateConfirm}
	title={$i18n.t('Unsaved drafts detected')}
	message={`${$i18n.t('You have')} <b>${draftCount}</b> ${$i18n.t('unsaved draft value(s).')}<br><br>${$i18n.t('Would you like to save them before generating the document?')}`}
	cancelLabel={$i18n.t('No, Generate')}
	confirmLabel={$i18n.t('Save and Generate')}
	on:confirm={confirmSaveThenGenerate}
	on:cancel={proceedGenerateWithoutSaving}
/>
