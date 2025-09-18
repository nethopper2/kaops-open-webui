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

  type PreviewMode = 'original' | 'values';
  let previewMode: PreviewMode = 'original';
  type TokenState = 'draft' | 'saved' | 'none';

  let previewHtml: string = '';
  let previewLoading = false;
  let previewError = '';
  let previewContainer: HTMLDivElement | null = null;
  // Pending IDs to mark once DOM is available
  let pendingDraftIds: Set<string> = new Set();
  let pendingSavedIds: Set<string> = new Set();
  let pendingNoneIds: Set<string> = new Set();
  // Pending scroll/selection to apply after (re)load
  let pendingScroll: { id: string; state: 'draft' | 'saved' } | null = null;

  // Replacement values per token occurrence id
  let replacementsById: Map<string, { draft?: string; saved?: string }> = new Map();

  function applyValuesText() {
    if (!previewContainer) return;
    const tokens = Array.from(previewContainer.querySelectorAll<HTMLElement>('.token[id]'));
    for (const el of tokens) {
      const id = el.id;
      // Preserve original text once
      if (!el.dataset.originalText) {
        el.dataset.originalText = el.textContent ?? '';
      }
      const rep = replacementsById.get(id);
      const draft = (rep?.draft ?? '').trim();
      const saved = (rep?.saved ?? '').trim();
      let text = '';
      if (draft && saved && draft !== saved) text = `${draft} • ${saved}`;
      else text = draft || saved || (el.dataset.originalText ?? '');
      // Only update when different to avoid cursor jumps
      if ((el.textContent ?? '') !== text) {
        el.textContent = text;
      }
    }
  }
  function restoreOriginalText() {
    if (!previewContainer) return;
    const tokens = Array.from(previewContainer.querySelectorAll<HTMLElement>('.token[id]'));
    for (const el of tokens) {
      const orig = el.dataset.originalText;
      if (orig !== undefined && (el.textContent ?? '') !== orig) {
        el.textContent = orig;
      }
    }
  }

  function applyDraftMarkers() {
    if (previewMode === 'original') return; // In Original mode, do not show draft coloring
    if (!previewContainer || pendingDraftIds.size === 0) return;
    const toDelete: string[] = [];
    pendingDraftIds.forEach((id) => {
      try {
        const safeId = (window as any).CSS?.escape ? (window as any).CSS.escape(id) : id.replace(/[^\w-]/g, '_');
        const el = previewContainer!.querySelector(`#${safeId}`) as HTMLElement | null;
        if (el) {
          if (!el.classList.contains('token-selected-draft') && !el.classList.contains('token-selected-saved') && !el.classList.contains('token-selected')) {
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

  function applySavedMarkers() {
    if (previewMode === 'original') return;
    if (!previewContainer || pendingSavedIds.size === 0) return;
    const toDelete: string[] = [];
    pendingSavedIds.forEach((id) => {
      try {
        const safeId = (window as any).CSS?.escape ? (window as any).CSS.escape(id) : id.replace(/[^\w-]/g, '_');
        const el = previewContainer!.querySelector(`#${safeId}`) as HTMLElement | null;
        if (el) {
          if (!el.classList.contains('token-selected-draft') && !el.classList.contains('token-selected-saved') && !el.classList.contains('token-selected')) {
            el.classList.add('token-saved');
            el.dataset.tokenState = 'saved';
          }
          toDelete.push(id);
        }
      } catch {}
    });
    toDelete.forEach((id) => pendingSavedIds.delete(id));
  }

  function applyNoneMarkers() {
    if (previewMode === 'original') return;
    if (!previewContainer || pendingNoneIds.size === 0) return;
    const toDelete: string[] = [];
    pendingNoneIds.forEach((id) => {
      try {
        const safeId = (window as any).CSS?.escape ? (window as any).CSS.escape(id) : id.replace(/[^\w-]/g, '_');
        const el = previewContainer!.querySelector(`#${safeId}`) as HTMLElement | null;
        if (el) {
          // No class for 'none' in +Values; rely on base .token styling. Persist state only.
          if (!el.classList.contains('token-selected-draft') && !el.classList.contains('token-selected-saved') && !el.classList.contains('token-selected')) {
            el.dataset.tokenState = 'none';
          }
          toDelete.push(id);
        }
      } catch {}
    });
    toDelete.forEach((id) => pendingNoneIds.delete(id));
  }

  function applyStatusMarkers() {
    // Only in values mode do we show persistent state tints
    if (previewMode !== 'values') return;
    applyDraftMarkers();
    applySavedMarkers();
    applyNoneMarkers();
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

  function applyModeStyles() {
    if (!previewContainer) return;
    const tokens = Array.from(previewContainer.querySelectorAll<HTMLElement>('.token'));
    if (previewMode === 'original') {
      // Restore original text and ensure unselected tokens have Incomplete styling
      restoreOriginalText();
      tokens.forEach((el) => {
        clearStateTint(el);
        const wasSavedSel = el.classList.contains('token-selected-saved');
        const wasDraftSel = el.classList.contains('token-selected-draft');
        const wasIncompleteSel = el.classList.contains('token-selected');
        el.classList.remove('token-selected-saved');
        el.classList.remove('token-selected-draft');
        el.classList.remove('token-selected');
        if (wasSavedSel || wasDraftSel || wasIncompleteSel) {
          el.classList.add('token-selected-original');
        } else {
          // Unselected tokens use base 'token' styling in Original mode (incomplete palette via .mode-original .token)
        }
      });
    } else {
      // Values mode: show replacement values and set unselected tokens to Incomplete styling
      applyValuesText();
      tokens.forEach((el) => {
        if (el.classList.contains('token-selected-original')) {
          el.classList.remove('token-selected-original');
          const st = (el.dataset?.tokenState as TokenState | undefined) ?? 'saved';
          if (st === 'draft') el.classList.add('token-selected-draft');
          else if (st === 'none') el.classList.add('token-selected');
          else el.classList.add('token-selected-saved');
        }
        if (!el.classList.contains('token-selected-draft') && !el.classList.contains('token-selected-saved') && !el.classList.contains('token-selected')) {
          clearStateTint(el);
          const st = (el.dataset?.tokenState as TokenState | undefined);
          if (st === 'draft') el.classList.add('token-draft');
          else if (st === 'saved') el.classList.add('token-saved');
          // if none or unknown, leave base .token which uses incomplete palette in values mode
        }
      });
    }
  }

  // After HTML updates, try to apply any pending draft markers and pending scroll, then mode styles
  $: if (previewHtml) {
    setTimeout(() => {
      applyStatusMarkers();
      if (pendingScroll) {
        try {
          selectAndScroll(pendingScroll.id, pendingScroll.state);
        } finally {
          pendingScroll = null;
        }
      }
      applyModeStyles();
    }, 0);
  }

  // When mode changes, re-apply styles on next tick
  // Include previewMode in the dependency so toggling modes re-applies text/value swaps and styles
  $: if (previewContainer && previewMode) {
    setTimeout(() => applyModeStyles(), 0);
  }

  function clearStateTint(el: HTMLElement) {
    el.classList.remove('token-draft');
    el.classList.remove('token-saved');
    el.classList.remove('token-none');
  }

  let removeHook: (() => void) | null = null;

  function clearSelection() {
    if (!previewContainer) return;
    const prevSel = previewContainer.querySelector('.token.token-selected-draft, .token.token-selected-saved, .token.token-selected, .token.token-selected-original') as HTMLElement | null;
    if (prevSel) {
      // Determine the token's persisted state if available
      const savedState: TokenState = (prevSel.dataset?.tokenState as TokenState | undefined)
        ?? (prevSel.classList.contains('token-draft') ? 'draft' : prevSel.classList.contains('token-saved') ? 'saved' : 'none');
      // Remove selected state classes
      prevSel.classList.remove('token-selected-draft');
      prevSel.classList.remove('token-selected-saved');
      prevSel.classList.remove('token-selected');
      prevSel.classList.remove('token-selected-original');
      // Restore unselected state based on mode and tokenState
      clearStateTint(prevSel);
      if (previewMode === 'values') {
        const st = (prevSel.dataset?.tokenState as TokenState | undefined) ?? savedState;
        if (st === 'draft') prevSel.classList.add('token-draft');
        else if (st === 'saved') prevSel.classList.add('token-saved');
        // if none, leave base .token to get Incomplete styling in values mode
      } else {
        // Original mode uses base .token with incomplete palette via .mode-original .token
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
        // Determine none-state from existing class if present
        const isNone = el.classList.contains('token-none') || (el.dataset?.tokenState as TokenState | undefined) === 'none';
        // Persist token state on the element so we can restore unselected class correctly later
        el.dataset.tokenState = isNone ? 'none' : (state as TokenState);
        // Remove any unselected state classes before applying selected state (Original hides state tints; Values overrides)
        clearStateTint(el);
        if (previewMode === 'original') {
          el.classList.add('token-selected-original');
        } else {
          if (isNone) el.classList.add('token-selected');
          else el.classList.add(state === 'draft' ? 'token-selected-draft' : 'token-selected-saved');
        }
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

    const setStatuses = (params: { draftIds?: string[]; savedIds?: string[]; noneIds?: string[] }) => {
      try {
        (params.draftIds || []).forEach((id) => pendingDraftIds.add(id));
        (params.savedIds || []).forEach((id) => pendingSavedIds.add(id));
        (params.noneIds || []).forEach((id) => pendingNoneIds.add(id));
        applyStatusMarkers();
      } catch {}
    };
    appHooks.hook('private-ai.token-replacer.preview.set-status-ids', setStatuses);

    const setValues = (params: { byId: Record<string, { draft?: string; saved?: string }> }) => {
      try {
        replacementsById = new Map(Object.entries(params.byId || {}));
        if (previewMode === 'values') applyValuesText();
      } catch {}
    };
    appHooks.hook('private-ai.token-replacer.preview.set-values', setValues);

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
      try { appHooks.removeHook('private-ai.token-replacer.preview.set-status-ids', setStatuses); } catch {}
      try { appHooks.removeHook('private-ai.token-replacer.preview.set-values', setValues); } catch {}
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
  <!-- Header: Single row with Document on left and mode buttons on right -->
  <div class="px-3 py-2 text-xs border-b border-gray-200 dark:border-gray-800 text-gray-700 dark:text-gray-200">
    <div class="flex items-start gap-2 justify-between">
      <div class="min-w-0 flex-1">
        {#if file}
          <span class="ml-1 break-all line-clamp-2 align-top inline-block max-w-full" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;">{file.name}</span>
        {:else}
          {$i18n.t('No document selected')}
        {/if}
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button
          type="button"
          class="toggle-btn {previewMode === 'original' ? 'toggle-btn-active' : 'toggle-btn-inactive'}"
          on:click={() => (previewMode = 'original')}
          aria-pressed={previewMode === 'original'}
        >{$i18n.t('Original')}</button>
        <button
          type="button"
          class="toggle-btn {previewMode === 'values' ? 'toggle-btn-active' : 'toggle-btn-inactive'}"
          on:click={() => (previewMode = 'values')}
          aria-pressed={previewMode === 'values'}
        >+{$i18n.t('Values')}</button>
      </div>
    </div>
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
        <div class="preview-html prose prose-sm max-w-none dark:prose-invert" class:mode-original={previewMode==='original'} class:mode-values={previewMode==='values'} bind:this={previewContainer} style="min-height:80px; text-align: left;">
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

  /* Toggle buttons — neutral, legible */
  .toggle-btn {
    font-size: 0.75rem; /* text-xs */
    line-height: 1rem;
    padding: 0.25rem 0.5rem; /* px-2 py-1 */
    border-radius: 0.375rem; /* rounded-md */
    color: #374151; /* gray-700 */
    background: #f3f4f6; /* gray-100 */
    border: 1px solid rgba(107,114,128,0.35); /* gray-500/35 */
    font-weight: 600;
    transition: background-color 120ms ease, color 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
  }
  .toggle-btn:hover { background: #e5e7eb; /* gray-200 */ }
  .toggle-btn:focus { outline: none; box-shadow: 0 0 0 2px rgba(156,163,175,0.45); }
  .toggle-btn-active {
    color: #111827; /* gray-900 */
    background: #e5e7eb; /* gray-200 */
    border-color: rgba(55,65,81,0.45); /* gray-700/45 */
  }
  .toggle-btn-inactive {
    opacity: 0.85;
    color: #4b5563; /* gray-600 */
    background: #f8fafc; /* gray-50 */
    border-color: rgba(156,163,175,0.3);
  }
  @media (prefers-color-scheme: dark) {
    .toggle-btn { color: #e5e7eb; background: #111827; border-color: rgba(156,163,175,0.25); }
    .toggle-btn:hover { background: #1f2937; }
    .toggle-btn:focus { box-shadow: 0 0 0 2px rgba(156,163,175,0.35); }
    .toggle-btn-active { color: #f9fafb; background: #1f2937; border-color: rgba(229,231,235,0.2); }
    .toggle-btn-inactive { opacity: 0.8; color: #9ca3af; background: #0b1220; border-color: rgba(156,163,175,0.2); }
  }

	/* token class name is provided from server preview  */
  :global(.preview-html .token) {
    background: transparent;
    color: inherit;
    border-radius: 0.25em;
    padding: 0.15em 0.35em; /* legible */
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 0.95em; /* slightly larger */
    font-weight: 600; /* improve readability */
    border: 1px solid rgba(107,114,128,0.25); /* gray-500/25 */
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token) { border-color: rgba(156,163,175,0.25); }
  }

  /* Original mode base look: Unselected uses Incomplete styling (same as token-none) */
  :global(.preview-html.mode-original .token) {
    background: rgba(234, 179, 8, 0.20); /* yellow-500/20 */
    color: #854d0e; /* amber-800 */
    border-color: rgba(234, 179, 8, 0.35);
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html.mode-original .token) {
      background: rgba(202, 138, 4, 0.35); /* amber-600/35 */
      color: #fde68a; /* yellow-200 */
      border-color: rgba(245, 158, 11, 0.45);
    }
  }

  /* +Values mode base and unselected state tints */
  :global(.preview-html.mode-values .token) {
    background: rgba(234, 179, 8, 0.20); /* warning: yellow-500/20 */
    color: #854d0e; /* yellow-800 */
    border-color: rgba(234, 179, 8, 0.35);
  }
  :global(.preview-html .token.token-saved) {
    background: rgba(34, 197, 94, 0.20); /* success: green-500/20 */
    color: #166534; /* green-800 */
    border-color: rgba(34, 197, 94, 0.35);
  }
  :global(.preview-html .token.token-draft) {
    background: rgba(59, 130, 246, 0.20); /* info: blue-500/20 */
    color: #1d4ed8; /* blue-700 */
    border-color: rgba(59, 130, 246, 0.35);
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html.mode-values .token) {
      background: rgba(202, 138, 4, 0.35); /* amber-600/35 */
      color: #fde68a; /* yellow-200 */
      border-color: rgba(245, 158, 11, 0.45);
    }
    :global(.preview-html .token.token-saved) {
      background: rgba(22, 101, 52, 0.45); /* green-800/45 */
      color: #86efac; /* green-300 */
      border-color: rgba(22, 163, 74, 0.50);
    }
    :global(.preview-html .token.token-draft) {
      background: rgba(29, 78, 216, 0.45); /* blue-700/45 */
      color: #bfdbfe; /* blue-200 */
      border-color: rgba(59, 130, 246, 0.45);
    }
  }

  /* Selected states */
  :global(.preview-html .token.token-selected-saved) {
    background: #dcfce7 !important; /* green-100 */
    color: #166534 !important; /* green-800 */
    border: 2px solid rgba(134, 239, 172, 0.9) !important; /* stronger green-300 */
    box-shadow: 0 0 0 2px rgba(134, 239, 172, 0.35) !important; /* subtle halo for readability */
  }
  :global(.preview-html .token.token-selected-draft) {
    background: rgba(59, 130, 246, 0.20) !important; /* blue-500/20 similar to badge */
    color: #1e3a8a !important; /* blue-900 for contrast */
    font-weight: 700 !important;
    border: 2px solid rgba(59, 130, 246, 0.9) !important; /* blue-500 strong */
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.35) !important;
  }
  :global(.preview-html .token.token-selected) {
    background: #fef9c3 !important; /* yellow-100 */
    color: #854d0e !important; /* amber-800 */
    border: 2px solid rgba(250, 204, 21, 0.9) !important; /* yellow-400 */
    box-shadow: 0 0 0 2px rgba(250, 204, 21, 0.35) !important; /* subtle halo */
    font-weight: 700 !important;
  }
  :global(.preview-html .token.token-selected-original) {
    background: #fef9c3 !important; /* align with lighter warning */
    color: #854d0e !important; /* amber-800 */
    border: 2px solid rgba(250, 204, 21, 0.9) !important;
    box-shadow: 0 0 0 2px rgba(250, 204, 21, 0.35) !important;
    font-weight: 700 !important;
  }
  @media (prefers-color-scheme: dark) {
    :global(.preview-html .token.token-selected-saved) {
      background: rgba(20, 83, 45, 0.45) !important; /* green-900/45 */
      color: #86efac !important; /* green-300 */
      border: 2px solid rgba(55, 86, 67, 0.85) !important; /* approx green-700 stronger */
      box-shadow: 0 0 0 2px rgba(20, 83, 45, 0.4) !important;
    }
    :global(.preview-html .token.token-selected-draft) {
      background: rgba(29, 78, 216, 0.45) !important; /* blue-700/45 */
      color: #bfdbfe !important; /* blue-200 */
      font-weight: 700 !important;
      border: 2px solid rgba(59, 130, 246, 0.85) !important; /* blue-500 */
      box-shadow: 0 0 0 2px rgba(29, 78, 216, 0.4) !important;
    }
    :global(.preview-html .token.token-selected) {
      background: rgba(202, 138, 4, 0.45) !important; /* amber-600/45 */
      color: #fde68a !important; /* yellow-200 */
      border: 2px solid rgba(245, 158, 11, 0.85) !important; /* amber-500-600 */
      box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.4) !important;
    }
    :global(.preview-html .token.token-selected-original) {
      background: rgba(202, 138, 4, 0.45) !important; /* amber-600/45 */
      color: #fde68a !important; /* yellow-200 */
      border: 2px solid rgba(245, 158, 11, 0.85) !important;
      box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.4) !important;
    }
  }
</style>
