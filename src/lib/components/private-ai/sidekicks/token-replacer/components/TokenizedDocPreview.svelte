<script lang="ts">
  import DOMPurify from 'dompurify';
  import { getContext, onDestroy, onMount } from 'svelte';
  import { getFilePreview } from '$lib/apis/private-ai/sidekicks/token-replacer';
  import type { TokenFile } from '../stores';
	import Spinner from '$lib/components/common/Spinner.svelte';
  import { appHooks } from '$lib/utils/hooks';
	import { showSidebar } from '$lib/stores';

  export let file: TokenFile | null = null;
  export let previewType: 'docx' | 'csv' = 'docx';

  const i18n = getContext('i18n');

  let previewHtml: string = '';
  let previewLoading = false;
  let previewError = '';
  let previewContainer: HTMLDivElement | null = null;

  async function load() {
    previewLoading = true;
    previewError = '';
    previewHtml = '';
    try {
      if (!file) {
        previewError = $i18n.t('No file selected.');
        return;
      }
      const res = await getFilePreview(previewType, file.fullPath);
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

  let removeHook: (() => void) | null = null;

  function clearSelection() {
    if (!previewContainer) return;
    const prevSel = previewContainer.querySelector('.token.token-selected-draft, .token.token-selected-saved') as HTMLElement | null;
    if (prevSel) {
      // Determine the token's persisted state if available
      const savedState = (prevSel.dataset?.tokenState as 'draft' | 'saved' | undefined) ?? (prevSel.classList.contains('token-draft') ? 'draft' : 'saved');
      // Remove selected state classes
      prevSel.classList.remove('token-selected-draft');
      prevSel.classList.remove('token-selected-saved');
      // Normalize unselected classes: ensure only the correct one is present
      prevSel.classList.remove('token-saved');
      prevSel.classList.remove('token-draft');
      prevSel.classList.add(savedState === 'draft' ? 'token-draft' : 'token-saved');
    }
  }

  function selectAndScroll(id: string, state: 'draft' | 'saved') {
    if (!previewContainer) return;
    clearSelection();
    try {
      // Use CSS.escape for safety when available
      const safeId = (window as any).CSS?.escape ? (window as any).CSS.escape(id) : id.replace(/[^\w-]/g, '_');
      const el = previewContainer.querySelector(`#${safeId}`) as HTMLElement | null;
      if (el) {
        // Persist token state on the element so we can restore unselected class correctly later
        el.dataset.tokenState = state;
        // Remove any unselected classes before applying selected state
        el.classList.remove('token-saved');
        el.classList.remove('token-draft');
        el.classList.add(state === 'draft' ? 'token-selected-draft' : 'token-selected-saved');
        // Scroll into view centered within the scrollable container
        el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
      }
    } catch {
      // no-op
    }
  }

  onMount(() => {
    const h = (params: { id: string; state: 'draft' | 'saved' }) => {
      selectAndScroll(params.id, params.state);
    };
    appHooks.hook('private-ai.token-replacer.preview.select-token', h);
    removeHook = () => {
      try { appHooks.removeHook('private-ai.token-replacer.preview.select-token', h); } catch {}
    };
		appHooks.callHook('private-ai.token-replacer.preview.opened');
		showSidebar.set(false);
  });

  onDestroy(() => {
    try { removeHook && removeHook(); } catch {}
    try { appHooks.callHook('private-ai.token-replacer.preview.closed'); } catch {}
  });
</script>

<div class="flex flex-col h-full">
  <div class="px-3 py-2 text-xs text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-800">
    {#if file}
      <span class="font-medium">{$i18n.t('Document')}:</span>
      <span class="ml-1">{file.name}</span>
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
        <div class="preview-html prose prose-sm max-w-none dark:prose-invert" bind:this={previewContainer} style="min-height:80px; text-align: left;">
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
	/* token class name is provided from server preview  */
  :global(.preview-html .token) {
    background: #eef2ff; /* indigo-50 */
    color: #1f2937; /* gray-800 for stronger contrast */
    border-radius: 0.25em;
    padding: 0.15em 0.35em; /* a bit more padding for legibility */
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 0.95em; /* slightly larger */
    font-weight: 600; /* improve readability */
    border: 1px solid rgba(99,102,241,0.45); /* indigo-500/45 for more definition */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token) {
      background: rgba(99, 102, 241, 0.15); /* indigo-500/15 */
      color: #a5b4fc; /* indigo-300 */
      border-color: rgba(99,102,241,0.35);
    }
  }
  /* Unselected token state styles */
  :global(.preview-html .token.token-saved) {
    background: #eefdf3; /* subtle green tint */
    color: #14532d; /* green-900 */
    border-color: rgba(16, 185, 129, 0.35); /* emerald-500/35 */
  }
  :global(.preview-html .token.token-draft) {
    background: #fff7ed; /* orange-50 */
    color: #7c2d12; /* orange-900 */
    border-color: rgba(249, 115, 22, 0.35); /* orange-500/35 */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token.token-saved) {
      background: rgba(22, 101, 52, 0.2); /* green-700/20 */
      color: #86efac; /* green-300 */
      border-color: rgba(34, 197, 94, 0.35); /* green-500/35 */
    }
    :global(.preview-html .token.token-draft) {
      background: rgba(124, 45, 18, 0.2); /* orange-800/20 */
      color: #fdba74; /* orange-300 */
      border-color: rgba(249, 115, 22, 0.35); /* orange-500/35 */
    }
  }

  /* Selected states (explicit CSS to avoid reliance on Tailwind @apply in component styles) */
  :global(.preview-html .token.token-selected-saved) {
    background: #dcfce7 !important; /* green-100 */
    color: #166534 !important; /* green-800 */
    border: 2px solid rgba(134, 239, 172, 0.9) !important; /* stronger green-300 */
    box-shadow: 0 0 0 2px rgba(134, 239, 172, 0.35) !important; /* subtle halo for readability */
  }
  :global(.preview-html .token.token-selected-draft) {
    background: #fef3c7 !important; /* amber-100 */
    color: #92400e !important; /* amber-800 */
    border: 2px solid rgba(253, 230, 138, 0.9) !important; /* stronger amber-300 */
    box-shadow: 0 0 0 2px rgba(253, 230, 138, 0.35) !important; /* subtle halo */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token.token-selected-saved) {
      background: rgba(20, 83, 45, 0.45) !important; /* green-900/45 for stronger contrast */
      color: #86efac !important; /* green-300 */
      border: 2px solid rgba(55, 86, 67, 0.85) !important; /* approx green-700 stronger */
      box-shadow: 0 0 0 2px rgba(20, 83, 45, 0.4) !important;
    }
    :global(.preview-html .token.token-selected-draft) {
      background: rgba(120, 53, 15, 0.45) !important; /* amber-900/45 */
      color: #fcd34d !important; /* amber-300 */
      border: 2px solid rgba(146, 64, 14, 0.85) !important; /* approx amber-700 stronger */
      box-shadow: 0 0 0 2px rgba(120, 53, 15, 0.4) !important;
    }
  }
</style>
