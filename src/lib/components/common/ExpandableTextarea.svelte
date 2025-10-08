<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';

  export let id: string | undefined = undefined;
  export let value: string = '';
  export let placeholder: string | undefined = undefined;
  export let ariaLabel: string | undefined = undefined;
  export let ariaDescribedby: string | undefined = undefined;
  // Optional text for the element referenced by ariaDescribedby (accessibility)
  export let describedByText: string | undefined = undefined;
  export let disabled: boolean = false;
  // Additional classes applied to the textarea element
  export let textareaClass: string = '';
  // When true, show a highlighted ring around the textarea (e.g., for Draft state)
  export let highlight: boolean = false;
  // Optional badge text shown in the top-right; hidden if empty/undefined
  export let badgeText: string | undefined = undefined;
  // Minimum height in em units (align with existing usage min-h-[4em])
  export let minHeightEm: number = 4;
  // Fullscreen strategy: viewport-fixed overlay (default) or container expansion
  export let fullscreenStrategy: 'viewport' | 'container' = 'viewport';

  const dispatch = createEventDispatcher();

  let isFullscreen = false;
  let previouslyFocused: HTMLElement | null = null;
  let fullscreenContainer: HTMLDivElement | null = null;

  function openFullscreen() {
    if (isFullscreen) return;
    previouslyFocused = (document.activeElement as HTMLElement) ?? null;
    isFullscreen = true;
    // Prevent background scroll only for viewport overlay
    if (fullscreenStrategy === 'viewport') {
      document.documentElement.style.overflow = 'hidden';
    }
  }

  function closeFullscreen() {
    if (!isFullscreen) return;
    isFullscreen = false;
    if (fullscreenStrategy === 'viewport') {
      document.documentElement.style.overflow = '';
    }
    if (previouslyFocused) previouslyFocused.focus();
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && isFullscreen) {
      e.stopPropagation();
      closeFullscreen();
    }
  }

  onMount(() => {
    document.addEventListener('keydown', onKeydown, { capture: true });
  });
  onDestroy(() => {
    document.removeEventListener('keydown', onKeydown, { capture: true } as any);
    document.documentElement.style.overflow = '';
  });

  function handleInput(event: Event) {
    const v = (event.target as HTMLTextAreaElement)?.value ?? '';
    dispatch('input', { value: v, originalEvent: event });
  }

  function handleFocus(event: FocusEvent) {
    dispatch('focus', event);
  }
</script>

<!-- Base styles mirror existing textareas; avoid dynamic Tailwind where possible -->
<div class={`relative w-full ${isFullscreen && fullscreenStrategy === 'container' ? 'min-h-[60vh]' : ''}`}>
  <!-- Optional badge (top-right, padded to not conflict with fullscreen button) -->
  {#if badgeText && !isFullscreen}
    <div class="pointer-events-none absolute -top-2 right-4 text-[9px] inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
      <span class="inline-block px-1 py-0 rounded bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700 shadow-sm">{badgeText}</span>
    </div>
  {/if}
  {#if ariaDescribedby && describedByText}
    <span id={ariaDescribedby} class="sr-only">{describedByText}</span>
  {/if}

  {#if !isFullscreen}
    <!-- Fullscreen toggle button -->
    <button
      type="button"
      class="absolute top-0 right-0 inline-flex items-center justify-center h-4 w-4 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
      aria-label="Fullscreen"
      on:click={openFullscreen}
    >
      <span aria-hidden="true">⤢</span>
    </button>
  {/if}

  {#if !isFullscreen}
    <textarea
      {id}
      class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 resize-y text-xs min-h-[${minHeightEm}em] ${highlight ? 'ring-1 ring-blue-400 border-blue-400 dark:ring-blue-500 dark:border-blue-500' : ''} ${textareaClass}`}
      {placeholder}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedby}
      {disabled}
      value={value}
      on:input={handleInput}
      on:focus={handleFocus}
      autocomplete="off"
      spellcheck={false}
    />
  {/if}

  {#if isFullscreen && fullscreenStrategy === 'container'}
    <!-- Container-expanded overlay: fills this component's wrapper -->
    <div class="absolute inset-0 z-[300] bg-white/95 dark:bg-black/90 backdrop-blur-sm rounded shadow-lg ring-1 ring-black/5 dark:ring-white/10">
      <div class="h-full w-full flex flex-col">
        <div class="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-800 bg-gray-50/90 dark:bg-gray-800/80">
          <div class="text-sm text-gray-700 dark:text-gray-300">{ariaLabel ?? 'Editor'}</div>
          <div class="flex items-center gap-2">
            {#if badgeText}
              <div class="text-[10px] inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
                <span class="inline-block px-1 py-0.5 rounded bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700 shadow-sm">{badgeText}</span>
              </div>
            {/if}
            <button
              type="button"
              class="inline-flex items-center justify-center h-8 px-2 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
              aria-label="Close fullscreen"
              on:click={closeFullscreen}
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        </div>
        <div class="flex-1 p-3">
          <textarea
            class={`w-full h-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 resize-none text-sm ${highlight ? 'ring-1 ring-blue-400 border-blue-400 dark:ring-blue-500 dark:border-blue-500' : ''}`}
            {placeholder}
            aria-label={ariaLabel}
            aria-describedby={ariaDescribedby}
            {disabled}
            value={value}
            on:input={handleInput}
            on:focus={handleFocus}
            autocomplete="off"
            spellcheck={false}
          />
        </div>
      </div>
    </div>
  {/if}
</div>

{#if isFullscreen && fullscreenStrategy === 'viewport'}
  <!-- Simple fullscreen overlay using fixed positioning; high z-index to overlay app UI -->
  <div bind:this={fullscreenContainer} class="fixed inset-0 z-[5000] bg-white/95 dark:bg-black/90 backdrop-blur-sm">
    <div class="h-full w-full flex flex-col">
      <div class="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-800 bg-gray-50/90 dark:bg-gray-800/80">
        <div class="text-sm text-gray-700 dark:text-gray-300">{ariaLabel ?? 'Editor'}</div>
        <div class="flex items-center gap-2">
          {#if badgeText}
            <div class="text-[10px] inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
              <span class="inline-block px-1 py-0.5 rounded bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700 shadow-sm">{badgeText}</span>
            </div>
          {/if}
          <button
            type="button"
            class="inline-flex items-center justify-center h-8 px-2 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
            aria-label="Close fullscreen"
            on:click={closeFullscreen}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
      </div>
      <div class="flex-1 p-3">
        <textarea
          class={`w-full h-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 resize-none text-sm ${highlight ? 'ring-1 ring-blue-400 border-blue-400 dark:ring-blue-500 dark:border-blue-500' : ''}`}
          {placeholder}
          aria-label={ariaLabel}
          aria-describedby={ariaDescribedby}
          {disabled}
          value={value}
          on:input={handleInput}
          on:focus={handleFocus}
          autocomplete="off"
          spellcheck={false}
        />
      </div>
    </div>
  </div>
{/if}
