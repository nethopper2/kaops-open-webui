<script lang="ts">
  import { createEventDispatcher, getContext } from 'svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import Eye from '$lib/components/icons/Eye.svelte';
  import { selectedTokenizedDoc, selectedTokenizedDocId } from '../stores';

  const i18n = getContext('i18n');

  // Strip query string and keep origin+pathname (+hash if present)
  function stripQuery(url: string | undefined | null): string {
    if (!url) return '';
    try {
      const u = new URL(url, window.location.origin);
      const base = `${u.origin}${u.pathname}`;
      return u.hash ? `${base}${u.hash}` : base;
    } catch {
      const [left] = String(url).split('?');
      return left;
    }
  }

  // Truncate long text with middle ellipsis
  function middleTruncate(text: string, max: number): string {
    if (!text) return '';
    if (text.length <= max) return text;
    const half = Math.floor((max - 1) / 2);
    const head = text.slice(0, half);
    const tail = text.slice(-half);
    return `${head}\u2026${tail}`;
  }
  const dispatch = createEventDispatcher<{ preview: void }>();
</script>

{#if $selectedTokenizedDocId !== '' && $selectedTokenizedDoc}
  <div class="w-full max-w-sm mb-4 px-4 mx-auto">
    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{$i18n.t('Selected document')}</div>
    <div class="rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="text-sm font-medium text-gray-800 dark:text-gray-200 line-clamp-1">{$selectedTokenizedDoc.name ?? 'Untitled'}</div>
          <div class="text-xs text-gray-500 dark:text-gray-400">
            <Tooltip content={stripQuery($selectedTokenizedDoc.url)} placement="top">
              <span class="inline-block max-w-full align-top" aria-label={stripQuery($selectedTokenizedDoc.url)}>
                {middleTruncate(stripQuery($selectedTokenizedDoc.url), 80)}
              </span>
            </Tooltip>
          </div>
        </div>
        <div class="shrink-0 self-start">
          <Tooltip content="Preview Document" placement="top">
            <button
              class="p-1 rounded border bg-white dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900"
              aria-label="Preview Document"
              on:click={() => dispatch('preview')}
            >
              <Eye className="w-5 h-5" />
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
  </div>
{/if}
