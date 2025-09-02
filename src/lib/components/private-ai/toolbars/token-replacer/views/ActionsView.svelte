<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import FilePreviewDialog from '$lib/components/chat/MessageInput/FilePreviewDialog.svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import { ensureFilesFetched, selectedTokenizedDoc, selectedTokenizedDocId, currentTokenReplacerSubView } from '../stores';
  import type { TokenFile } from '../stores';

  const i18n = getContext('i18n');

  let showPreviewDialog = false;
  let previewFile: TokenFile | null = null;

  function stripQuery(url: string | undefined | null): string {
    if (!url) return '';
    try {
      // Use URL parsing when possible to robustly drop query and keep pathname+hash
      const u = new URL(url, window.location.origin);
      const base = `${u.origin}${u.pathname}`;
      return u.hash ? `${base}${u.hash}` : base;
    } catch {
      // Fallback: simple split on '?' and keep potential hash on the left part
      const [left] = String(url).split('?');
      return left;
    }
  }

  function middleTruncate(text: string, max: number): string {
    if (!text) return '';
    if (text.length <= max) return text;
    const half = Math.floor((max - 1) / 2);
    const head = text.slice(0, half);
    const tail = text.slice(-half);
    return `${head}\u2026${tail}`; // ellipsis
  }

  function openPreviewDialog() {
    previewFile = $selectedTokenizedDoc;
    if (previewFile) {
      showPreviewDialog = true;
    }
  }
  function closePreviewDialog() {
    showPreviewDialog = false;
    previewFile = null;
  }

  onMount(() => {
    ensureFilesFetched();
  });
</script>

{#if showPreviewDialog}
  <FilePreviewDialog
    show={showPreviewDialog}
    file={previewFile}
    previewType="docx"
    on:close={closePreviewDialog}
  />
{/if}

<div class="flex flex-col w-full h-full items-stretch justify-start py-4">
  <div class="text-sm text-gray-600 dark:text-gray-300 mb-3 text-center px-4">
    {$i18n.t('Token replacement session is active. Choose an action to continue.')}
  </div>

  {#if $selectedTokenizedDocId !== '' && $selectedTokenizedDoc}
    <div class="w-full max-w-sm mb-4 px-4">
      <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{$i18n.t('Selected document')}</div>
      <div class="rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2">
        <div class="text-sm font-medium text-gray-800 dark:text-gray-200 line-clamp-1">{$selectedTokenizedDoc.name ?? 'Untitled'}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">
          <Tooltip content={stripQuery($selectedTokenizedDoc.url)} placement="top">
            <span class="inline-block max-w-full align-top" aria-label={stripQuery($selectedTokenizedDoc.url)}>
              {middleTruncate(stripQuery($selectedTokenizedDoc.url), 80)}
            </span>
          </Tooltip>
        </div>
      </div>
    </div>
  {/if}

  {#if $selectedTokenizedDocId === ''}
    <div class="w-full max-w-sm mb-4 px-4 text-center">
      <div class="text-sm text-gray-600 dark:text-gray-300 mb-2">{$i18n.t('No document selected')}</div>
      <div class="text-xs text-gray-500 dark:text-gray-400 mb-3">{$i18n.t('Please select a tokenized document to proceed with token replacement actions.')}</div>
      <button
        class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
        on:click={() => currentTokenReplacerSubView.set('initial')}
      >
        {$i18n.t('Select a document')}
      </button>
    </div>
  {/if}

  {#if $selectedTokenizedDocId !== ''}
  <div class="grid grid-cols-1 gap-3 w-full max-w-sm">
    <button class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600">
      {$i18n.t('Edit Replacement Values')}
    </button>
    <button class="px-4 py-2 rounded bg-gray-700 text-white hover:bg-gray-800 dark:bg-gray-700 dark:hover:bg-gray-800">
      {$i18n.t('Generate Token Replacement Document')}
    </button>
    <button
      class="px-4 py-2 rounded bg-white border border-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:border-gray-700 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200"
      on:click={() => openPreviewDialog()}
    >
      {$i18n.t('View document preview')}
    </button>
  </div>
  {/if}
</div>
