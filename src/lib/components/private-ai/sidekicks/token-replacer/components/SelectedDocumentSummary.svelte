<script lang="ts">
  import { createEventDispatcher, getContext } from 'svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import Eye from '$lib/components/icons/Eye.svelte';
  import { selectedTokenizedDoc, selectedTokenizedDocPath } from '../stores';
	import Document from '$lib/components/icons/Document.svelte';

  const i18n = getContext('i18n');

  // Strip query string and keep origin+pathname (+hash if present)
  function stripQuery(url: string | undefined | null): string {
    if (!url) return '';
    try {
      const u = new URL(url);
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

{#if $selectedTokenizedDocPath !== '' && $selectedTokenizedDoc}
  <div class="mb-2">
<!--    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{$i18n.t('Selected document')}</div>-->
    <!-- whole card is a clickable preview button. Tooltip on filename shows full path. -->
    <button
      type="button"
      class="w-full text-left rounded-md bg-transparent dark:bg-transparent p-2 hover:bg-gray-100/60 dark:hover:bg-white/5 shadow-none hover:shadow-sm transition-shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-gray-900"
      aria-label={$i18n.t('Preview Document')}
      on:click={() => dispatch('preview')}
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <Tooltip content={stripQuery($selectedTokenizedDoc.fullPath)} placement="top">
            <div class="flex items-center gap-1 text-sm font-medium text-gray-800 dark:text-gray-200 line-clamp-1" aria-label={stripQuery($selectedTokenizedDoc.url)}>
							<Document/>
              {middleTruncate($selectedTokenizedDoc.name ?? 'Untitled', 80)}
            </div>
          </Tooltip>
        </div>
        <div class="shrink-0 self-start text-gray-500 dark:text-gray-400" aria-hidden="true">
          <Tooltip content={$i18n.t('Preview Document')} placement="top">
            <span class="inline-flex items-center">
              <Eye className="w-5 h-5" />
            </span>
          </Tooltip>
        </div>
      </div>
    </button>
  </div>
{/if}
