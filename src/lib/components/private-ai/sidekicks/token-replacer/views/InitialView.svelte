<script lang="ts">
import Select from 'svelte-select';
import Tooltip from '$lib/components/common/Tooltip.svelte';
import Eye from '$lib/components/icons/Eye.svelte';
import { getContext, onMount } from 'svelte';
import { appHooks } from '$lib/utils/hooks';
import { isChatStarted, chatId } from '$lib/stores';
import {
	ensureFilesFetched,
	tokenizedFiles,
	selectedTokenizedDocPath,
	selectedTokenizedDoc,
	filesLoading,
	currentTokenReplacerSubView
} from '../stores';
import { savePrivateAiSidekickState } from '$lib/private-ai/state';
import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
import { getTokenReplacerFileHealth, type TokenReplacerFileHealth } from '$lib/apis/private-ai/sidekicks/token-replacer';

const i18n = getContext('i18n');

export let modelId: string | null = null;
$: void modelId;

let analyzing = false;
let analysisError: string | null = null;
let analysis: TokenReplacerFileHealth | null = null;

async function analyzeSelected() {
	analysisError = null;
	analysis = null;
	if (!$selectedTokenizedDocPath) return;
	analyzing = true;
	try {
		const res = await getTokenReplacerFileHealth($selectedTokenizedDocPath);
		analysis = res;
	} catch (e) {
		analysisError = e instanceof Error ? e.message : 'Failed to analyze document';
	} finally {
		analyzing = false;
	}
}

function openPreviewDialog() {
	const file = $selectedTokenizedDoc;
	if (file) {
		appHooks.callHook('chat.overlay', {
			action: 'open',
			title: `👀 ${$i18n.t('Preview')}`,
			component: TokenizedDocPreview,
			props: { file, previewType: 'docx' }
		});
	}
}

onMount(() => {
	ensureFilesFetched();
});
</script>


<div class="flex flex-col w-full px-2 py-2">
	<div class="text-xs text-gray-500 mb-2 text-left">
		<strong>Let's get started!</strong> To replace tokens in your document, select a tokenized document from the list
		below.
	</div>
	<div class="flex flex-col w-full h-full gap-2 items-center">
		<div class="flex items-center gap-2 w-full min-w-0">
			<Select
				items={$tokenizedFiles}
				value={$selectedTokenizedDoc}
				placeholder="Search or select a document"
				label="name"
				itemId="fullPath"
				clearable={true}
				class="w-full max-w-full rounded-md border border-gray-300 bg-white text-gray-900 shadow-sm hover:border-gray-400 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2 focus-within:ring-offset-white dark:!border-gray-700 dark:!bg-gray-900 dark:!text-gray-100 dark:!hover:border-gray-600 dark:!focus-within:ring-blue-400 dark:!focus-within:ring-offset-gray-900"
				showChevron
				loading={$filesLoading}
				on:select={(e) => {
          const v = e.detail;

          selectedTokenizedDocPath.set(String(v?.fullPath ?? ''));
        }}
				on:clear={() => {
          selectedTokenizedDocPath.set('');
        }}
			/>
			<Tooltip content="Preview Document" placement="top">
				<button
					class="p-1 rounded bg-white dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed {$selectedTokenizedDocPath === '' ? 'border-gray-200 dark:border-gray-800 cursor-not-allowed' : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900'}"
					disabled={$selectedTokenizedDocPath === ""}
					aria-label="Preview Document"
					on:click={() => openPreviewDialog()}
				>
					<div class="h-5 w-5">👀</div>
<!--					<Eye className="w-5 h-5" />-->
				</button>
			</Tooltip>
		</div>

		{#if $selectedTokenizedDocPath !== ""}
			<div class="flex w-full flex-col items-center justify-center mt-6 gap-3">
				<div class="text-sm text-gray-600 dark:text-gray-300 text-center px-2">
					Ready to start replacing tokens in your selected document.
				</div>
				<div class="flex items-center gap-2">
					<button
						class="px-4 py-2 rounded-md text-sm font-medium bg-gray-100 text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white disabled:opacity-50 disabled:cursor-not-allowed dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700 dark:focus:ring-offset-gray-900"
						disabled={$selectedTokenizedDocPath === "" || analyzing}
						aria-label="Analyze Document"
						on:click={analyzeSelected}
					>
						{analyzing ? 'Analyzing…' : 'Analyze'}
					</button>
					<button
						class="px-6 py-3 rounded-md text-base font-medium bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600"
						disabled={$selectedTokenizedDocPath === ""}
						aria-label={$isChatStarted ? "Continue Token Replacement" : "Begin Token Replacement"}
						on:click={() => {
							const file = $selectedTokenizedDoc;
							const fullPath = $selectedTokenizedDocPath;
							// Build directive envelope as a JSON string
							const directive = {
								_kind: 'openwebui.directive',
								version: 1,
								name: 'token_replacer.begin',
								assistant_only: true,
								payload: {
									file_path: String(fullPath || '')
								}
							};
							const prompt = JSON.stringify(directive);
							const title = `🔁 ${String(file?.name ?? '').trim()}`;
							appHooks.callHook('chat.submit', { prompt, title });
							// Switch to the edit values sub-view after the beginning
							currentTokenReplacerSubView.set('editValues');
							// Persist sidekick UI state (selected document) for this chat+sidekick
							;(async () => {
								try {
									const tId = modelId;
									if (!tId) return;
									const cNow = $chatId;
									const doSave = async (cid) => {
										await savePrivateAiSidekickState(cid, tId, { tokenizedDocPath: $selectedTokenizedDocPath });
									};
									if (cNow) {
										await doSave(cNow);
									} else {
										// Chat id not yet assigned (new chat). Save once chatId becomes available.
										const unsub = chatId.subscribe(async (cid) => {
											if (cid) {
												try { await doSave(cid); } finally { unsub(); }
											}
										});
									}
								} catch {
									// ignore persistence errors
								}
							})();
						}}
					>
						{$isChatStarted ? 'Continue' : 'Begin'}
					</button>
				</div>

				{#if analyzing}
					<div class="text-xs text-gray-500 dark:text-gray-400">Running analysis…</div>
				{:else if analysisError}
					<div class="text-xs text-red-600 dark:text-red-400">{analysisError}</div>
				{:else if analysis}
					<div class="w-full max-w-2xl text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded-md p-3">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<div class="flex flex-wrap gap-x-4 gap-y-2">
								<div><span class="text-gray-500">Tokens:</span> {analysis.stats.tokensFound} (<span title="unique">{analysis.stats.uniqueTokens} unique</span>)</div>
								<div><span class="text-gray-500">Depth:</span> {analysis.stats.nestedDepthMax}</div>
								<div><span class="text-gray-500">Extract:</span> {analysis.stats.extractionMs} ms</div>
								<div><span class="text-gray-500">Cache:</span> {analysis.stats.cache}</div>
							</div>
							<div class="text-[11px] text-gray-500 truncate max-w-[50%]" title={analysis.filePath}>{analysis.filePath}</div>
						</div>

						<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1">
							<div class="{analysis.unbalanced.hasIssues ? 'text-amber-600 dark:text-amber-400' : 'text-green-600 dark:text-green-400'}">
								{analysis.unbalanced.hasIssues ? `Unbalanced: ${analysis.unbalanced.unmatchedStarts.length + analysis.unbalanced.unmatchedEnds.length}` : 'Balanced'}
							</div>
							{#if analysis.duplicates?.length}
								<div class="text-amber-600 dark:text-amber-400">Duplicates: {analysis.duplicates.length}</div>
							{/if}
							{#if analysis.entityAnomalies?.length}
								<div class="text-amber-600 dark:text-amber-400">Entity anomalies: {analysis.entityAnomalies.length}</div>
							{/if}
							{#if analysis.styleMarkers?.detected}
								<div class="text-blue-600 dark:text-blue-400" title={analysis.styleMarkers.notes || ''}>Style markers</div>
							{/if}
						</div>

						{#if analysis.unbalanced.hasIssues}
							<div class="mt-3">
								<div class="text-xs font-medium text-gray-700 dark:text-gray-300">Unbalanced markers</div>
								{#if analysis.unbalanced.unmatchedStarts.length}
									<div class="mt-1 text-[11px] text-gray-600 dark:text-gray-400">Unmatched starts (first 3):</div>
									<ul class="mt-1 pl-4 list-disc space-y-1 text-xs">
										{#each analysis.unbalanced.unmatchedStarts.slice(0,3) as u}
											<li>
												<span class="text-gray-500">idx {u.occurrenceIndex} @ {u.charOffset}:</span>
												<code class="ml-1 rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{u.contextBefore}</code>
												<span class="opacity-60"> | </span>
												<code class="rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{u.contextAfter}</code>
											</li>
										{/each}
										{#if analysis.unbalanced.unmatchedStarts.length > 3}
											<div class="pl-4 text-[11px] opacity-70">+{analysis.unbalanced.unmatchedStarts.length - 3} more…</div>
										{/if}
									</ul>
								{/if}
								{#if analysis.unbalanced.unmatchedEnds.length}
									<div class="mt-2 text-[11px] text-gray-600 dark:text-gray-400">Unmatched ends (first 3):</div>
									<ul class="mt-1 pl-4 list-disc space-y-1 text-xs">
										{#each analysis.unbalanced.unmatchedEnds.slice(0,3) as u}
											<li>
												<span class="text-gray-500">idx {u.occurrenceIndex} @ {u.charOffset}:</span>
												<code class="ml-1 rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{u.contextBefore}</code>
												<span class="opacity-60"> | </span>
												<code class="rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{u.contextAfter}</code>
											</li>
										{/each}
										{#if analysis.unbalanced.unmatchedEnds.length > 3}
											<div class="pl-4 text-[11px] opacity-70">+{analysis.unbalanced.unmatchedEnds.length - 3} more…</div>
										{/if}
									</ul>
								{/if}
							</div>
						{/if}

						{#if analysis.duplicates?.length}
							<div class="mt-3">
								<div class="text-xs font-medium text-gray-700 dark:text-gray-300">Duplicate tokens</div>
								<ul class="mt-1 pl-4 list-disc space-y-1 text-xs">
									{#each analysis.duplicates.slice(0,5) as d}
										<li><code class="rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{d.token}</code> <span class="text-gray-500">× {d.count}</span></li>
									{/each}
									{#if analysis.duplicates.length > 5}
										<div class="pl-4 text-[11px] opacity-70">+{analysis.duplicates.length - 5} more…</div>
									{/if}
								</ul>
							</div>
						{/if}

						{#if analysis.entityAnomalies?.length}
							<div class="mt-3">
								<div class="text-xs font-medium text-gray-700 dark:text-gray-300">Entity anomalies</div>
								<ul class="mt-1 pl-4 list-disc space-y-1 text-xs">
									{#each analysis.entityAnomalies.slice(0,3) as e}
										<li>
											<code class="rounded bg-gray-100 dark:bg-gray-800 px-1 py-[1px] font-mono text-[11px]">{e.token}</code>
											<span class="ml-1 text-gray-500">→ {e.entities.join(', ')}</span>
										</li>
									{/each}
									{#if analysis.entityAnomalies.length > 3}
										<div class="pl-4 text-[11px] opacity-70">+{analysis.entityAnomalies.length - 3} more…</div>
									{/if}
								</ul>
							</div>
						{/if}

						{#if analysis.styleMarkers?.detected}
							<div class="mt-3 text-xs">
								<span class="font-medium text-gray-700 dark:text-gray-300">Style markers:</span>
								<span class="text-gray-600 dark:text-gray-400">{analysis.styleMarkers.notes || 'Detected'}</span>
							</div>
						{/if}

						{#if analysis.anomalySummary?.length}
							<div class="mt-3 text-xs text-gray-700 dark:text-gray-300">
								<div class="font-medium">Anomaly summary</div>
								<div class="mt-1">
									{#each analysis.anomalySummary.slice(0,5) as a}
										<div>• {a.message} <span class="text-[11px] opacity-70">({a.type}, {a.severity}, {a.count})</span></div>
									{/each}
									{#if analysis.anomalySummary.length > 5}
										<div class="opacity-70">+{analysis.anomalySummary.length - 5} more…</div>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>
