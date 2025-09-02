<script lang="ts">
import { createEventDispatcher, onMount, onDestroy } from 'svelte';
import DOMPurify from 'dompurify';
import XMark from '../../icons/XMark.svelte';
import { fetchFilePreview } from '$lib/apis/tokenizedFiles';
import DocumentChartBar from '../../icons/DocumentChartBar.svelte';

export let show = false;
export let file: any = null;
export let previewType: 'docx' | 'csv' = 'docx';

const dispatch = createEventDispatcher();

let previewHtml: string | any[] = '';
let previewLoading = false;
let previewError = '';
let metadata: any = null;
let tokenSummary: any = null;
// Helper to merge metadata and file for display
$: info = metadata ? { ...file, ...metadata } : file;
let showMore = false;
let activeTab = 'info'; // 'info' or 'tokens'

async function fetchPreviewHtml() {
	if (!file || !file.path || !previewType) {
		previewHtml = '';
		previewError = 'No preview available.';
        metadata = null;
        tokenSummary = null;
		return;
	}
	previewLoading = true;
	previewError = '';
	previewHtml = '';
    metadata = null;
    tokenSummary = null;
	try {
		if (previewType === 'docx') {
            const res = await fetchFilePreview('docx', file.path);
            previewHtml = res.preview;
            metadata = res.metadata;
            tokenSummary = res.tokenSummary;
		} else {
            const res = await fetchFilePreview(previewType, file.path);
            previewHtml = res.preview;
            metadata = res.metadata;
            tokenSummary = res.tokenSummary;
		}
	} catch (e) {
		previewError = 'Failed to load preview.';
	} finally {
		previewLoading = false;
	}
}

function closeDialog() {
	dispatch('close');
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  if (isNaN(d as any)) return dateStr;
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

// Only fetch when show or file changes
$: if (show && file) {
	(async () => { await fetchPreviewHtml(); })();
}
function portal(node: HTMLElement, target: HTMLElement | null = null) {
  if (typeof document === 'undefined') return {} as any;
  const t = target ?? document.body;
  if (!t) return {} as any;
  t.appendChild(node);
  return {
    destroy() {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    }
  };
}
</script>

<svelte:window on:keydown={(e) => { if (show && (e.key === 'Escape' || e.key === 'Esc')) closeDialog(); }} />

{#if show}
  <div use:portal>
   <!-- Backdrop -->
   <div class="fixed inset-0 bg-black/30 z-[1000]" on:click={closeDialog} aria-hidden="true"></div>
   <!-- Right-anchored dialog -->
	<div class="fixed right-0 w-full max-w-md z-[1001] flex flex-col bg-white dark:bg-gray-850 shadow-lg rounded-l-xl transition-transform duration-200" style="top:0; bottom:0; margin-top:8px; margin-bottom:8px; height:auto; max-height:calc(100vh - 16px); transform: translateX(0);">
		<!-- Prominent top-right close button -->
		<button class="absolute top-2 right-2 p-2  rounded-full bg-white text-gray-700 shadow border border-gray-200 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-700 dark:hover:bg-gray-700" on:click={closeDialog} aria-label="Close" title="Close">
			<XMark className="w-5 h-5" />
		</button>
		<div class="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
			<div class="text-base truncate">
				{#if previewType === 'csv'}
					<span class="font-semibold">Values: </span>
					<span class="ml-1 text-gray-800 dark:text-gray-100">{file?.name ?? ''}</span>
				{:else}
					<span class="font-semibold">Document: </span>
					<span class="ml-1 text-gray-800 dark:text-gray-100">{file?.name ?? ''}</span>
				{/if}
			</div>
			<button class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800" on:click={closeDialog} aria-label="Close Preview">
				<XMark className="w-5 h-5" />
			</button>
		</div>
		<!-- Preview HTML section -->
		<div class="overflow-auto max-h-[65vh] min-h-[120px] border-b border-gray-100 dark:border-gray-800 px-4 py-3">
			{#if previewLoading}
				<div class="flex items-center justify-center text-gray-400">Loading preview...</div>
			{:else if previewError}
				<div class="text-red-500 text-sm">{previewError}</div>
			{:else if previewHtml}
				<div class="preview-html border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800 p-3 mb-3" style="min-height:80px; text-align: left; overflow-x: auto;">
					{#if typeof previewHtml === 'string'}
						<div class="preview-html" style="min-height:80px; text-align: left;">
							{@html DOMPurify.sanitize(previewHtml)}
						</div>
					{:else if Array.isArray(previewHtml) && previewHtml.length > 0}
						<table class="text-xs w-full border border-gray-200 dark:border-gray-700">
							<tbody>
								{#each Object.entries(previewHtml[0]) as [key, value], i}
									<tr>
										<td class="px-2 py-1 border-b border-gray-100 dark:border-gray-700 font-semibold text-right whitespace-nowrap bg-gray-100 dark:bg-gray-850 {i === 0 ? 'border-t border-gray-200 dark:border-gray-700' : ''}">{key}</td>
										<td class="px-2 py-1 border-b border-gray-100 dark:border-gray-700 border-l border-gray-200 dark:border-gray-700 {i === 0 ? 'border-t border-gray-200 dark:border-gray-700' : ''}">{value}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{:else}
						No preview available.
					{/if}
				</div>
			{/if}
		</div>
		<!-- Tabbed info/token section -->
		<div class="flex flex-row gap-2 mt-2 mb-1 px-4">
			<button class="text-xs px-2 py-1 rounded-t border-b-2 focus:outline-none transition-colors duration-150 {activeTab === 'info' ? 'border-sky-500 text-sky-700 dark:text-sky-300 font-semibold' : 'border-transparent text-gray-500 dark:text-gray-400'}" on:click={() => activeTab = 'info'}>File Info</button>
			{#if tokenSummary}
				<button class="text-xs px-2 py-1 rounded-t border-b-2 focus:outline-none transition-colors duration-150 {activeTab === 'tokens' ? 'border-sky-500 text-sky-700 dark:text-sky-300 font-semibold' : 'border-transparent text-gray-500 dark:text-gray-400'}" on:click={() => activeTab = 'tokens'}>Token Info</button>
			{/if}
		</div>
		<div class="flex-1 overflow-y-auto px-4 py-3">
			{#if activeTab === 'info'}
				{#if file}
					<div class="mb-2 text-sm text-gray-700 dark:text-gray-200 text-left">
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Size</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">
								{#if info.size === 0 || info.size == null}
									-
								{:else if info.size < 1024}
									{info.size} Bytes
								{:else}
									{Math.round(info.size/1024)} KB
								{/if}
							</span>
						</div>
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Updated</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.updated ? formatDate(info.updated) : (info.updated_at ? formatDate(info.updated_at) : '-')}</span>
						</div>
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Created</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.timeCreated ? formatDate(info.timeCreated) : (info.created ? formatDate(info.created) : (info.created_at ? formatDate(info.created_at) : '-'))}</span>
						</div>
						{#if file.url}
							<div class="flex items-baseline mb-1">
								<span class="w-24 font-semibold text-right mr-2">Preview</span>
								<span class="flex-1 text-gray-600 dark:text-gray-300">
									{#if info.id && (info.contentType === 'application/pdf' || info.contentType === 'text/plain' || info.contentType === 'text/csv' || info.name?.toLowerCase().endsWith('.pdf') || info.name?.toLowerCase().endsWith('.csv') || info.name?.toLowerCase().endsWith('.txt'))}
										<a href={`/api/files/${info.id}/content?attachment=false`} target="_blank" rel="noopener noreferrer" class="inline-block px-2 py-0.5 text-xs border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 text-sky-700 dark:text-sky-300 rounded transition-colors duration-150">Open in new tab</a>
									{:else}
										<a href={file.url} target="_blank" rel="noopener noreferrer" class="inline-block px-2 py-0.5 text-xs border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 text-sky-700 dark:text-sky-300 rounded transition-colors duration-150">Open in new tab</a>
									{/if}
								</span>
							</div>
						{/if}
						<button class="text-xs text-sky-700 dark:text-sky-300 mt-1 mb-0 ml-1 underline hover:no-underline focus:outline-none" on:click={() => showMore = !showMore} type="button">{showMore ? 'Hide' : 'More'}...</button>
						{#if showMore}
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Path</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.path ?? '-'}</span>
						</div>
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Content Type</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.contentType ?? info.type ?? '-'}</span>
						</div>
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">Encoding</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.contentEncoding ?? '-'}</span>
						</div>
						<div class="flex items-baseline mb-1">
							<span class="w-24 font-semibold text-right mr-2">ID</span>
							<span class="flex-1 text-gray-600 dark:text-gray-300">{info.id ?? '-'}</span>
						</div>
						{/if}
					</div>
				{/if}
			{:else if activeTab === 'tokens' && tokenSummary}
				<div class="mb-2 p-2 rounded border border-gray-200 dark:border-gray-800 text-xs text-left bg-transparent">
					<div class="flex flex-wrap gap-4 mb-1">
						<span>Total tokens: <span class="font-mono">{tokenSummary.total_tokens}</span></span>
						<span>Unique tokens: <span class="font-mono">{tokenSummary.unique_tokens}</span></span>
					</div>
					{#if tokenSummary.top_tokens && tokenSummary.top_tokens.length > 0}
						<table class="text-xs border border-gray-200 dark:border-gray-700 w-full mb-1">
							<thead>
								<tr>
									<th class="px-2 py-1 border-b border-gray-100 dark:border-gray-700 text-left">Top Tokens</th>
									<th class="px-2 py-1 border-b border-gray-100 dark:border-gray-700 text-left" style="white-space:nowrap; min-width:3.5em; max-width:4.5em;">Count</th>
								</tr>
							</thead>
							<tbody>
								{#each tokenSummary.top_tokens as t}
									<tr>
										<td class="px-2 py-1 border-b border-gray-100 dark:border-gray-700 font-mono break-words">{t.token}</td>
										<td class="px-2 py-1 border-b border-gray-100 dark:border-gray-700" style="white-space:nowrap; min-width:3.5em; max-width:4.5em; text-align:left;">{t.count}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{/if}
				</div>
			{/if}
		</div>
	</div>
  </div>
{/if} 

<style>
.preview-html {
  font-size: 0.75em;
}
:global(.preview-html p) {
  margin: 0 0 1em 0;
}
:global(.preview-html .token) {
  background: #fffbe6;
  color: #b26a00;
  border-radius: 0.25em;
  padding: 0.1em 0.3em;
  font-family: monospace;
  font-size: 0.9em;
}
</style> 