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
  // Pending draft IDs to mark once DOM is available
  let pendingDraftIds: Set<string> = new Set();
  // Pending scroll/selection to apply after (re)load
  let pendingScroll: { id: string; state: 'draft' | 'saved' } | null = null;

  function applyDraftMarkers() {
    if (!previewContainer || pendingDraftIds.size === 0) return;
    const toDelete: string[] = [];
    pendingDraftIds.forEach((id) => {
      try {
        const safeId = (window as any).CSS?.escape ? (window as any).CSS.escape(id) : id.replace(/[^\w-]/g, '_');
        const el = previewContainer!.querySelector(`#${safeId}`) as HTMLElement | null;
        if (el) {
          if (!el.classList.contains('token-selected-draft') && !el.classList.contains('token-selected-saved')) {
            el.classList.add('token-draft');
            el.dataset.tokenState = 'draft';
          }
          toDelete.push(id);
        }
      } catch {
        // ignore
      }
    });
    toDelete.forEach((id) => pendingDraftIds.delete(id));
  }

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

  // After HTML updates, try to apply any pending draft markers and pending scroll
  $: if (previewHtml) {
    setTimeout(() => {
      applyDraftMarkers();
      if (pendingScroll) {
        try {
          selectAndScroll(pendingScroll.id, pendingScroll.state);
        } finally {
          pendingScroll = null;
        }
      }
    }, 0);
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
      // For unselected state: if draft, ensure token-draft is present; otherwise ensure it's removed (base .token remains)
      if (savedState === 'draft') {
        prevSel.classList.add('token-draft');
      } else {
        prevSel.classList.remove('token-draft');
      }
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
        // Remove any unselected draft class before applying selected state
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

    const setDrafts = (params: { ids: string[] }) => {
      try {
        (params.ids || []).forEach((id) => pendingDraftIds.add(id));
        applyDraftMarkers();
      } catch {}
    };
    appHooks.hook('private-ai.token-replacer.preview.set-draft-ids', setDrafts);

    const reloadPreview = (params: { id: string; state: 'draft' | 'saved' }) => {
      try {
        pendingScroll = { id: params.id, state: params.state };
        // Always reload fresh from server
        void load();
      } catch {}
    };
    appHooks.hook('private-ai.token-replacer.preview.reload', reloadPreview);

    removeHook = () => {
      try { appHooks.removeHook('private-ai.token-replacer.preview.select-token', h); } catch {}
      try { appHooks.removeHook('private-ai.token-replacer.preview.set-draft-ids', setDrafts); } catch {}
      try { appHooks.removeHook('private-ai.token-replacer.preview.reload', reloadPreview); } catch {}
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
	/* TODO: Set up a css file for all the token-replacer related styles and ensure @apply can be used  */
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
  :global(.preview-html .token.token-draft) {
    background: #dbeafe; /* blue-100 */
    color: #1e40af; /* blue-800 */
    border-color: rgba(59, 130, 246, 0.35); /* blue-500/35 */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token.token-draft) {
      background: rgba(30, 64, 175, 0.25); /* blue-800/25 */
      color: #93c5fd; /* blue-300 */
      border-color: rgba(59, 130, 246, 0.35); /* blue-500/35 */
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
    background: #dbeafe !important; /* blue-100 */
    color: #1e3a8a !important; /* blue-900 for higher contrast */
    font-weight: 700 !important; /* increase emphasis for readability */
    border: 2px solid rgba(147, 197, 253, 0.9) !important; /* stronger blue-300 */
    box-shadow: 0 0 0 2px rgba(147, 197, 253, 0.35) !important; /* subtle halo */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token.token-selected-saved) {
      background: rgba(20, 83, 45, 0.45) !important; /* green-900/45 for stronger contrast */
      color: #86efac !important; /* green-300 */
      border: 2px solid rgba(55, 86, 67, 0.85) !important; /* approx green-700 stronger */
      box-shadow: 0 0 0 2px rgba(20, 83, 45, 0.4) !important;
    }
    :global(.preview-html .token.token-selected-draft) {
      background: rgba(30, 58, 138, 0.45) !important; /* blue-900/45 */
      color: #dbeafe !important; /* blue-100 for higher contrast on dark */
      font-weight: 700 !important; /* increase emphasis for readability */
      border: 2px solid rgba(29, 78, 216, 0.85) !important; /* approx blue-700 stronger */
      box-shadow: 0 0 0 2px rgba(30, 58, 138, 0.4) !important;
    }
  }
</style>
