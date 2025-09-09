<script lang="ts">
import { getContext, onMount, onDestroy } from 'svelte';
import { toast } from 'svelte-sonner';
import { currentTokenReplacerSubView, selectedTokenizedDocPath, selectedTokenizedDoc } from '../stores';
import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
import { appHooks } from '$lib/utils/hooks';
import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
import { chatId } from '$lib/stores';
import { loadTokenReplacerDraft, saveTokenReplacerDraft, clearTokenReplacerDraft, type TokenReplacerDraft } from '../drafts';

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
let values: ReplacementValues = {};
let searchQuery = '';
let showConfirm = false;

// Derived counts for confirmation
$: totalTokens = tokens.length;
$: providedCount = tokens.reduce((acc, t) => (values[t]?.trim()?.length ? acc + 1 : acc), 0);
$: emptyCount = Math.max(0, totalTokens - providedCount);

// Build confirmation message (markdown supported by ConfirmDialog)
$: confirmMessage = `${$i18n.t('You are about to submit all token/value pairs for the selected document.')}<br><br>` +
  `${$i18n.t('Tokens total')}: <b>${totalTokens}</b><br>` +
  `${$i18n.t('Replacement values provided')}: <b>${providedCount}</b><br>` +
  `${$i18n.t('Replacement values empty')}: <b>${emptyCount}</b><br><br>` +
  `${$i18n.t('All tokens will be submitted, including those not currently visible due to search filters.')}<br><br>` +
  `${$i18n.t('Do you want to continue?')}`;

// Fake loader simulating future REST API
async function loadTokensAndValues(): Promise<{ tokens: Token[]; values: ReplacementValues }> {
	// Simulate network latency
	await new Promise((r) => setTimeout(r, 200));
	const fakeTokens: Token[] = [
		'[[FIRST_NAME]]',
		'[[LAST_NAME]]',
		'[[EMAIL]]',
		'[[COMPANY]]',
		'[[JOB_TITLE]]',
		'[[ADDRESS_LINE_1]]',
		'[[ADDRESS_LINE_2]]',
		'[[CITY]]',
		'[[STATE]]',
		'[[POSTAL_CODE]]',
		'[[COUNTRY]]',
		'[[LONG_SENTENCE_TOKEN_THAT_COULD_BE_VERY_LONG_SO_WRAP_PROPERLY]]'
	];

	const fakeValues: ReplacementValues = {
		'[[FIRST_NAME]]': '',
		'[[LAST_NAME]]': '',
		'[[EMAIL]]': '',
		'[[COMPANY]]': 'My Company',
		'[[JOB_TITLE]]': '',
		'[[ADDRESS_LINE_1]]': '',
		'[[ADDRESS_LINE_2]]': '',
		'[[CITY]]': '',
		'[[STATE]]': '',
		'[[POSTAL_CODE]]': '',
		'[[COUNTRY]]': '',
		'[[LONG_SENTENCE_TOKEN_THAT_COULD_BE_VERY_LONG_SO_WRAP_PROPERLY]]': ''
	};

	return { tokens: fakeTokens, values: fakeValues };
}

// Fake submitter simulating future REST API
async function submitReplacementValues(payload: { token: string; value: string }[]): Promise<void> {
	// Simulate network latency and success
	await new Promise((r) => setTimeout(r, 300));
	// For now, just log. Replace with real API when available.
	console.debug('Submitting replacement values (stub):', payload);
}

// Derived filtered tokens with optional "needs value" filter
let isOnlyNeedingValues = true;
$: query = searchQuery.trim().toLowerCase();
$: filteredTokens = tokens
  .filter((t) => (isOnlyNeedingValues ? !(typeof values[t] === 'string' && values[t].trim().length > 0) : true))
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
			try { dismiss(); } catch {}
		}
	}
}

onMount(async () => {
	isLoading = true;
	loadError = null;
	try {
		const { tokens: tk, values: vals } = await loadTokensAndValues();
		tokens = tk;
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
	// Persist the latest state when the component is destroyed (e.g., panel closes)
	void persistDraftNow();
});
</script>

<div class="flex flex-col w-full h-full items-stretch justify-start">
	<!-- Header -->
	<div
		class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 sticky top-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-10">
		<div class="text-base font-medium text-gray-800 dark:text-gray-100">{$i18n.t('Edit Replacement Values')}</div>
		<button
			class="px-3 py-1.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-750 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700"
			on:click={() => currentTokenReplacerSubView.set('actions')}
		>
			{$i18n.t('Back to actions')}
		</button>
	</div>

	<!-- Search and Selected document summary (sticky under header) -->
	<div
		class="p-2 py-2 border-b border-gray-200 dark:border-gray-800 sticky top-[48px] bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-10">
		<div class="mb-2">
   <SelectedDocumentSummary on:preview={openPreviewPanel} />
		</div>
		<div class="flex items-center justify-between gap-3 mb-1">
			<label class="block text-xs font-medium text-gray-700 dark:text-gray-300" for="token-search">
				{$i18n.t('Search tokens')}
			</label>
			<label class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300 select-none">
				<input
					type="checkbox"
					class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
					bind:checked={isOnlyNeedingValues}
				/>
				<span>{$i18n.t('Only show tokens needing a value')}</span>
			</label>
		</div>
		<input
			id="token-search"
			class="w-full px-3 py-2 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
			type="text"
			bind:value={searchQuery}
			placeholder={$i18n.t('Type to filter tokens...')}
			autocomplete="off"
			spellcheck={false}
		/>
	</div>

	<!-- Content area -->
	<div class="flex-1 px-4 py-2 pb-24 space-y-3">
		{#if isLoading}
			<div class="text-sm text-gray-600 dark:text-gray-300" aria-live="polite">{$i18n.t('Loading tokens...')}</div>
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
								<input
									id={getInputId(token)}
									class="w-full px-3 py-2 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
									type="text"
									placeholder={$i18n.t('Replacement value')}
									aria-label={$i18n.t('Replacement value')}
									value={values[token] ?? ''}
									on:input={handleInput(token)}
									autocomplete="off"
								/>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	</div>

	<!-- Submit bar (sticky bottom) -->
	<div
		class="px-4 py-3 border-t border-gray-200 dark:border-gray-800 sticky bottom-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-10">
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
			<button
				class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600 text-nowrap"
				disabled={isLoading || isSubmitting || tokens.length === 0}
				on:click={() => (showConfirm = true)}
			>
				{$i18n.t('Submit')}
			</button>
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
