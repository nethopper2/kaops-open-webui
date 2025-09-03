<script lang="ts">
  import DOMPurify from 'dompurify';
  import { getContext } from 'svelte';
  import { fetchFilePreview } from '$lib/apis/tokenizedFiles';
  import type { TokenFile } from '../stores';
	import Spinner from '$lib/components/common/Spinner.svelte';

  export let file: TokenFile | null = null;
  export let previewType: 'docx' | 'csv' = 'docx';

  const i18n = getContext('i18n');

  let previewHtml: string = '';
  let previewLoading = false;
  let previewError = '';

  async function load() {
    previewLoading = true;
    previewError = '';
    previewHtml = '';
    try {
      if (!file) {
        previewError = $i18n.t('No file selected.');
        return;
      }
      const res = await fetchFilePreview(previewType, (file as any).path ?? file.url);
      previewHtml = res.preview ?? '';
    } catch (e) {
      previewError = $i18n.t('Failed to load preview.');
    } finally {
      previewLoading = false;
    }
  }

  $: if (file) {
    (async () => { await load(); })();
  } else {
    previewHtml = '';
  }
</script>

<div class="flex flex-col h-full">
  <div class="px-3 py-2 text-xs text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-800">
    {#if file}
      <span class="font-medium">{$i18n.t('Document')}:</span>
      <span class="ml-1">{file.name ?? file.url}</span>
    {:else}
      {$i18n.t('No document selected')}
    {/if}
  </div>
  <div class="flex-1 overflow-auto">
    {#if previewLoading}
      <div class="flex items-center gap-1 p-4 text-sm text-gray-500 dark:text-gray-400">
				<Spinner/>
				{$i18n.t('Loading...')}
			</div>
    {:else if previewError}
      <div class="p-4 text-sm text-red-600 dark:text-red-400">{previewError}</div>
    {:else if previewHtml}
      <div class="p-4">
        <div class="preview-html prose prose-sm max-w-none dark:prose-invert" style="min-height:80px; text-align: left;">
          {@html DOMPurify.sanitize(previewHtml)}
        </div>
      </div>
    {:else}
      <div class="p-4 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('No preview available.')}</div>
    {/if}
  </div>
</div>

<style>
  .preview-html { font-size: 0.75em; }
  :global(.preview-html p) { margin: 0 0 1em 0; }
  :global(.preview-html .token) {
    background: #fffbe6;
    color: #b26a00;
    border-radius: 0.25em;
    padding: 0.1em 0.3em;
    font-family: monospace;
    font-size: 0.9em;
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token) {
      background: rgba(250, 204, 21, 0.15); /* amber-400/15 */
      color: #fbbf24; /* amber-400 */
    }
  }
</style>
