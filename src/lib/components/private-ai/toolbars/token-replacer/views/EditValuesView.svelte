<script lang="ts">
import { getContext, onMount } from 'svelte';
import { currentTokenReplacerSubView } from '../stores';
import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

const i18n = getContext('i18n');

// Stubbed data types
type Token = string;
type ReplacementValues = Record<string, string>;

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
$: confirmMessage = `${$i18n.t('You are about to submit all token/value pairs for the selected document.')}\n\n` +
  `- ${$i18n.t('Tokens total')}: ${totalTokens}\n` +
  `- ${$i18n.t('Replacement values provided')}: ${providedCount}\n` +
  `- ${$i18n.t('Replacement values empty')}: ${emptyCount}\n\n` +
  `${$i18n.t('All tokens will be submitted, including those not currently visible due to search filters.')}\n\n` +
  `${$i18n.t('Do you want to continue?')}`;

// Fake loader simulating future REST API
async function loadTokensAndValues(): Promise<{ tokens: Token[]; values: ReplacementValues }> {
	// Simulate network latency
	await new Promise((r) => setTimeout(r, 200));
	const fakeTokens: Token[] = [
		'{{FIRST_NAME}}',
		'{{LAST_NAME}}',
		'{{EMAIL}}',
		'{{COMPANY}}',
		'{{JOB_TITLE}}',
		'{{ADDRESS_LINE_1}}',
		'{{ADDRESS_LINE_2}}',
		'{{CITY}}',
		'{{STATE}}',
		'{{POSTAL_CODE}}',
		'{{COUNTRY}}',
		'{{LONG_SENTENCE_TOKEN_THAT_COULD_BE_VERY_LONG_SO_WRAP_PROPERLY}}'
	];

	const fakeValues: ReplacementValues = {
		'{{FIRST_NAME}}': '',
		'{{LAST_NAME}}': '',
		'{{EMAIL}}': '',
		'{{COMPANY}}': 'My Company',
		'{{JOB_TITLE}}': '',
		'{{ADDRESS_LINE_1}}': '',
		'{{ADDRESS_LINE_2}}': '',
		'{{CITY}}': '',
		'{{STATE}}': '',
		'{{POSTAL_CODE}}': '',
		'{{COUNTRY}}': '',
		'{{LONG_SENTENCE_TOKEN_THAT_COULD_BE_VERY_LONG_SO_WRAP_PROPERLY}}': ''
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

// Derived filtered tokens
$: query = searchQuery.trim().toLowerCase();
$: filteredTokens = query
	? tokens.filter((t) => t.toLowerCase().includes(query))
	: tokens;

function updateValue(token: string, value: string) {
	values = { ...values, [token]: value };
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

async function handleSubmit() {
	submitError = null;
	submitSuccess = false;
	isSubmitting = true;
	try {
		// Build payload from ALL tokens, not only filtered ones
		const payload = tokens.map((t) => ({ token: t, value: values[t] ?? '' }));
		await submitReplacementValues(payload);
		submitSuccess = true;
	} catch (e) {
		console.error(e);
		submitError = $i18n.t('Failed to submit replacement values.');
	} finally {
		isSubmitting = false;
	}
}

onMount(async () => {
	isLoading = true;
	loadError = null;
	try {
		const { tokens: tk, values: vals } = await loadTokensAndValues();
		tokens = tk;
		values = vals;
	} catch (e) {
		console.error(e);
		loadError = $i18n.t('Failed to load tokens.');
	} finally {
		isLoading = false;
	}
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
			<SelectedDocumentSummary />
		</div>
		<label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1" for="token-search">
			{$i18n.t('Search tokens')}
		</label>
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
				<div class="text-sm text-gray-600 dark:text-gray-300">{$i18n.t('No tokens match your search.')}</div>
			{:else}
				<div class="space-y-4">
					{#each filteredTokens as token}
						<div class="grid grid-cols-1 lg:grid-cols-3 gap-2 lg:gap-4 items-start">
							<div
								class="lg:col-span-1 text-xs lg:text-sm text-gray-700 dark:text-gray-300 break-words whitespace-pre-wrap select-text">
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
				class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600"
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
