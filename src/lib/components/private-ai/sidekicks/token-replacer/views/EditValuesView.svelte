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
	}
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

function handleInput(token: string) {
	return (e: Event) => {
		const target = e.currentTarget as HTMLInputElement;
		updateValue(token, target.value);
	};
}

function handleIgnoreToggle(token: string) {
	return (e: Event) => {
		const target = e.currentTarget as HTMLInputElement;
		if (target.checked) {
			// Clearing the value marks it as ignored. We still submit an empty string.
			updateValue(token, '');
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
	// Persist the latest state when the component is destroyed (e.g., panel closes)
	void persistDraftNow();
});
</script>

<div class="flex flex-col w-full items-stretch justify-start">
	<!-- Header -->
	<div
		bind:this={headerEl}
		class="px-4 py-2 sticky top-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-20">
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
	<div>
		<!-- Selected document summary (non-sticky) -->
		<div class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
			<SelectedDocumentSummary on:preview={openPreviewPanel} />
		</div>

		<!-- Search and filtering (sticky within scroll container) -->
		<div
			class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 sticky bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-10 shadow"
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
					on:click={handleGenerate}
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
			<!-- Small-screen stats under search -->
			<div class="mt-1 sm:hidden flex flex-wrap items-center gap-1 text-[11px] text-gray-700 dark:text-gray-300">
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

		<!-- Content area -->
		<div class="px-4 py-2 pb-24 space-y-3">
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
						{#each filteredTokens as token}
							<div class="grid grid-cols-1 lg:grid-cols-3 gap-2 lg:gap-4 items-start">
								<div
									class="lg:col-span-1 text-[11px] lg:text-xs font-semibold text-gray-800 dark:text-gray-200 break-words whitespace-pre-wrap select-text">
									{token}
								</div>
								<div class="lg:col-span-2">
									{#key token}
										<div class="flex flex-col gap-1">
											<input
												id={getInputId(token)}
												class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 ${((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? 'ring-1 ring-amber-400 border-amber-400 dark:ring-amber-500 dark:border-amber-500' : ''}`}
												type="text"
												placeholder={$i18n.t('Replacement value')}
												aria-label={$i18n.t('Replacement value')}
												aria-describedby={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? `${getInputId(token)}-draft` : undefined}
												value={values[token] ?? ''}
												on:input={handleInput(token)}
												autocomplete="off"
											/>
											<div class="flex items-center gap-2">
												<label
													class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300 select-none">
													<input
														type="checkbox"
														class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
														checked={(values[token] ?? '') === ''}
														on:change={handleIgnoreToggle(token)}
													/>
													<span>{$i18n.t('Ignore')}</span>
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
					disabled={isLoading || isSubmitting || tokens.length === 0}
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
