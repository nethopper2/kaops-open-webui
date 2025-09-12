<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';

  type AnyProps = Record<string, unknown>;

  export let show: boolean = false;
  export let title: string = '';
  export let component: any = null;
  export let componentProps: AnyProps = {};

  const dispatch = createEventDispatcher<{ close: void }>();

  let isLargeScreen = false;
  let mediaQuery: MediaQueryList;

  function updateMedia(e: MediaQueryList | MediaQueryListEvent) {
    const matches = 'matches' in e ? e.matches : (e as MediaQueryList).matches;
    isLargeScreen = !!matches;
  }

  onMount(() => {
    mediaQuery = window.matchMedia('(min-width: 1024px)');
    const listener = (ev: MediaQueryListEvent) => updateMedia(ev);
    mediaQuery.addEventListener('change', listener);
    updateMedia(mediaQuery);
    return () => {
      mediaQuery.removeEventListener('change', listener);
    };
  });

  function handleClose() {
    dispatch('close');
  }

  function onKeydown(e: KeyboardEvent) {
    if (!show) return;
    if (e.key === 'Escape' || e.key === 'Esc') {
      handleClose();
    }
  }
</script>

<svelte:window on:keydown={onKeydown} />

{#if show}
  {#if !isLargeScreen}
    <!-- Full-screen semi-transparent blocker to cover left nav and main content on small screens only -->
    <div class="fixed inset-0 z-[99998] bg-black/30 dark:bg-black/50" on:click={handleClose} aria-hidden="true"></div>
  {/if}

  <!-- Chat overlay panel constrained to chat container -->
  <div class="absolute inset-0 z-[50] pointer-events-none">
    <div class="h-full bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 shadow-2xl shadow-gray-900/10 dark:shadow-black/40 pointer-events-auto flex flex-col" style="width: 100%;">
      <div class="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-800">
        <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{title}</div>
        <button type="button" class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800" on:click={handleClose} aria-label="Close overlay">
          <svg class="w-5 h-5 text-gray-700 dark:text-gray-200" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
        </button>
      </div>
      <div class="flex-1 overflow-auto">
        {#if component}
          <svelte:component this={component} {...componentProps} />
        {/if}
      </div>
    </div>
  </div>
{/if}
