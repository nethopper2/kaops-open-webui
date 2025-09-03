<script lang="ts">
  import { getContext } from 'svelte';
  import { currentTokenReplacerSubView } from '../stores';
  import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';

  const i18n = getContext('i18n');
</script>

<div class="flex flex-col w-full h-full items-stretch justify-start py-4">
  <div class="flex items-center justify-between mb-3 px-4">
    <div class="text-base font-medium text-gray-800 dark:text-gray-100">{$i18n.t('Edit Replacement Values')}</div>
    <button
      class="px-3 py-1.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-750 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700"
      on:click={() => currentTokenReplacerSubView.set('actions')}
    >
      {$i18n.t('Back to actions')}
    </button>
  </div>

  <!-- Selected document summary -->
  <SelectedDocumentSummary />

  <div class="px-4 text-sm text-gray-600 dark:text-gray-300">
    <p class="mb-2">{$i18n.t('This is a placeholder for editing token replacement values.')}</p>
    <p class="mb-4">{$i18n.t('In a future update, you will be able to review detected tokens and set the replacement values here.')}</p>
  </div>
</div>
