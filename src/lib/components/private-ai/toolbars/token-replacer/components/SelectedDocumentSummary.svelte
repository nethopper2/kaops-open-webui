<script lang="ts">
  import { getContext } from 'svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
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
</script>

{#if $selectedTokenizedDocId !== '' && $selectedTokenizedDoc}
  <div class="w-full max-w-sm mb-4 px-4 mx-auto">
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
