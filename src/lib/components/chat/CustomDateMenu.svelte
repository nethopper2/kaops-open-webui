<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  let customFrom = '';
  let customTo = '';
  
  const dispatch = createEventDispatcher();

  function apply() {
    dispatch('apply', { from: customFrom, to: customTo });
  }

  function cancel() {
    dispatch('cancel');
  }
</script>

<div class="w-full shadow-lg border border-gray-50 dark:border-gray-850 hover:border-gray-100 focus-within:border-gray-100 hover:dark:border-gray-800 focus-within:dark:border-gray-800 transition px-1 bg-white/90 dark:bg-gray-400/5 dark:text-gray-100">
  <label class="block text-xs">From:</label>
  <input type="date" bind:value={customFrom} class="w-full px-2 py-1 mt-1 text-sm border rounded" />

  <label class="block mt-2 text-xs">To:</label>
  <input type="date" bind:value={customTo} class="w-full px-2 py-1 mt-1 text-sm border rounded" />

  <div class="flex justify-left mt-2 gap-2">
    <button on:click={cancel}>Cancel</button>
    <button class="max-w-full bg-sky-500 text-white px-2 py-1 rounded" on:click={apply}>
      Apply
    </button>
  </div>
</div>
