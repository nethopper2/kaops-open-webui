<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import { ensureFilesFetched, selectedTokenizedDoc, selectedTokenizedDocId, currentTokenReplacerSubView } from '../stores';
  import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
  import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
  import { appHooks } from '$lib/utils/hooks';

  const i18n = getContext('i18n');

  function openPreviewDialog() {
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
  onMount(() => {
    ensureFilesFetched();
  });
</script>


<div class="flex flex-col w-full h-full items-stretch justify-start px-4 py-4">
  <div class="text-sm text-gray-600 dark:text-gray-300 mb-3 text-center px-4">
    {$i18n.t('Choose an action to continue.')}
  </div>

  <SelectedDocumentSummary on:preview={() => openPreviewDialog()} />

  {#if $selectedTokenizedDocId === ''}
    <div class="w-full max-w-sm mb-4 px-4 text-center mx-auto">
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
  <div class="grid grid-cols-1 gap-3 w-full max-w-sm mx-auto">
    <button class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600" on:click={() => currentTokenReplacerSubView.set('editValues')}>
      {$i18n.t('Edit Replacement Values')}
    </button>
    <button class="px-4 py-2 rounded bg-gray-700 text-white hover:bg-gray-800 dark:bg-gray-700 dark:hover:bg-gray-800">
      {$i18n.t('Generate Token Replacement Document')}
    </button>
  </div>
  {/if}
</div>
