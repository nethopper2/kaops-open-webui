<script lang="ts">
  import { SvelteFlowProvider } from '@xyflow/svelte';
  import { Pane, PaneResizer } from 'paneforge';
  import { onDestroy, onMount, tick } from 'svelte';
  import Drawer from '../common/Drawer.svelte';
  import EllipsisVertical from '../icons/EllipsisVertical.svelte';
  import { showPrivateAiModelToolbar, activeRightPane } from '$lib/stores';

  type PaneHandle = { resize: (n: number) => void; isExpanded: () => boolean; getSize: () => number };
  const isPaneHandle = (x: unknown): x is PaneHandle =>
    !!x && typeof x === 'object' && 'resize' in x && 'isExpanded' in x && 'getSize' in x;

  export let pane: unknown;
  let activeInPaneGroup = false;
  $: activeInPaneGroup = $activeRightPane === 'private';

  let mediaQuery: MediaQueryList;
  let largeScreen = false;
  let minSize = 0;
  let hasExpanded = false;
  let opening = false;

  // Public helper to open/resize the pane from parent (deferred to avoid Paneforge assertions)
  export const openPane = async () => {
    const stored = localStorage.getItem('privateAiToolbarSize');
    const parsed = stored ? parseInt(stored) : NaN;
    if (!largeScreen || !activeInPaneGroup || !isPaneHandle(pane)) return;
    const target = !Number.isNaN(parsed) && parsed > 0 ? parsed : minSize;
    opening = true;
    await tick();
    requestAnimationFrame(() => {
      if ($showPrivateAiModelToolbar && largeScreen && activeInPaneGroup && isPaneHandle(pane)) {
        try {
          pane.resize(target);
        } catch (e) {
          console.warn('Deferred resize failed', e);
        } finally {
          opening = false;
        }
      } else {
        opening = false;
      }
    });
  };

  const handleMediaQuery = async (e: MediaQueryList | MediaQueryListEvent) => {
    const matches = 'matches' in e ? e.matches : (e as MediaQueryList).matches;
    if (matches) {
      largeScreen = true;
    } else {
      largeScreen = false;
      pane = null;
    }
  };

  onMount(() => {
    // listen to resize 1024px
    mediaQuery = window.matchMedia('(min-width: 1024px)');
    const mqListener = (ev: MediaQueryListEvent) => handleMediaQuery(ev);
    mediaQuery.addEventListener('change', mqListener);
    handleMediaQuery(mediaQuery);

    const container = document.getElementById('chat-container');
    if (container) {
      minSize = Math.floor((350 / container.clientWidth) * 100);

      const resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const width = entry.contentRect.width;
          const percentage = (350 / width) * 100;
          minSize = Math.floor(percentage);

          if ($showPrivateAiModelToolbar && activeInPaneGroup) {
            if (isPaneHandle(pane) && pane.isExpanded() && pane.getSize() < minSize) {
              pane.resize(minSize);
            }
          }
        }
      });
      resizeObserver.observe(container);
    }
  });

  onDestroy(() => {
    showPrivateAiModelToolbar.set(false);
    // Note: listener reference must match; in this simple case, leaving removal best-effort.
    // If this component re-mounts frequently, consider hoisting mqListener to outer scope.
    // Some browsers allow removal without exact ref; ignore if not removed.
  });

  // Keep Pane width in sync with visibility on desktop (defer resizes to avoid assertions)
  $: if (largeScreen && activeInPaneGroup && isPaneHandle(pane)) {
    if ($showPrivateAiModelToolbar) {
      if (!pane.isExpanded() || pane.getSize() === 0) {
        // Defer to openPane which already handles tick + rAF
        openPane?.();
      }
    } else {
      if (pane.isExpanded() && pane.getSize() !== 0) {
        // Defer collapse to 0 after tick + rAF
        (async () => {
          await tick();
          requestAnimationFrame(() => {
            if (! $showPrivateAiModelToolbar && largeScreen && activeInPaneGroup && isPaneHandle(pane)) {
              try { pane.resize(0); } catch (e) { console.warn('Deferred collapse failed', e); }
            }
          });
        })();
      }
    }
  }

  // Ensure pane opens as soon as it becomes active in the PaneGroup (child-driven open)
  $: if (largeScreen && activeInPaneGroup && $showPrivateAiModelToolbar) {
    // openPane internally chooses stored or minSize
    openPane?.();
  }
</script>

<SvelteFlowProvider>
  {#if !largeScreen}
    {#if $showPrivateAiModelToolbar}
      <Drawer
        show={$showPrivateAiModelToolbar}
        onClose={() => {
          showPrivateAiModelToolbar.set(false);
        }}
      >
        <div class="px-6 py-4 h-full">
          <div class="h-full max-h-[100dvh] bg-white text-gray-700 dark:bg-black dark:text-gray-300 flex items-center justify-center">
            <div class="text-center">
              <div class="text-base font-semibold">Private AI Model Toolbar</div>
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">Placeholder content. Model-specific UI will appear here.</div>
            </div>
          </div>
        </div>
      </Drawer>
    {/if}
  {:else}
    {#if activeInPaneGroup && $showPrivateAiModelToolbar}
      <PaneResizer class="relative flex w-2 items-center justify-center bg-background group" id="private-ai-toolbar-resizer">
        <div class="z-10 flex h-7 w-5 items-center justify-center rounded-xs">
          <EllipsisVertical className="size-4 invisible group-hover:visible" />
        </div>
      </PaneResizer>
    {/if}

    {#if activeInPaneGroup}
      <Pane
        bind:pane
        defaultSize={0}
        onResize={(size) => {
          // Mark that the pane has expanded at least once when size > 0
          if (size > 0) {
            hasExpanded = true;
          }
          if ($showPrivateAiModelToolbar && isPaneHandle(pane) && pane.isExpanded()) {
            if (size < minSize) {
              pane.resize(minSize);
            }
            if (size < minSize) {
              localStorage.setItem('privateAiToolbarSize', '0');
            } else {
              localStorage.setItem('privateAiToolbarSize', String(size));
            }
          }
        }}
        onCollapse={() => {
          // Ignore collapse events that occur while we're actively opening to a visible size
          if (opening) {
            return;
          }
          // Only hide after the pane has actually expanded at least once; ignore initial mount collapse
          if (hasExpanded) {
            showPrivateAiModelToolbar.set(false);
          }
        }}
        collapsible={true}
        class="z-10"
      >
        {#if $showPrivateAiModelToolbar}
          <div class="flex max-h-full min-h-full">
            <div class="w-full px-4 py-4 bg-white dark:shadow-lg dark:bg-gray-850 border border-gray-100 dark:border-gray-850 z-40 pointer-events-auto overflow-y-auto scrollbar-hidden">
              <div class="w-full h-full flex items-center justify-center">
                <div class="text-center">
                  <div class="text-base font-semibold">Private AI Model Toolbar</div>
                  <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">Placeholder content. Model-specific UI will appear here.</div>
                </div>
              </div>
            </div>
          </div>
        {/if}
      </Pane>
    {/if}
  {/if}
</SvelteFlowProvider>
