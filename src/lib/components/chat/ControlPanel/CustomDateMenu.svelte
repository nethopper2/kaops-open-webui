<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import CalendarIcon from '$lib/components/icons/CalendarSolid.svelte';

  let customFrom = '';
  let customTo = '';

  let fromError = '';
  let toError = '';
  let checkdateError = '';
  let futuredateError = '';

  let fromdateInput;
  let todateInput;
  
  const dispatch = createEventDispatcher();

  function apply() {
    let valid = true;
    
    fromError = "";
    toError = "";
    checkdateError = "";
    
    if (!customFrom) {
      fromError = "Please select a start date.";
      valid = false
    } else {
      fromError = "";
    }

    if (!customTo) {
      toError = "Please select an end date.";
      valid = false
    } else {
      toError = "";
    }

    if (customFrom && customTo) {
      const from = new Date(customFrom);
      const to = new Date(customTo);
      const today = new Date();
        today.setHours(0,0,0,0);

      if (to < from) {
        checkdateError = "End date must be on or after start date."
        valid = false
      } else {
        checkdateError = "";
      }

      if (from>today || to>today) {
        futuredateError = "Date must be on or before today."
        valid = false
      } else {
        futuredateError = "";
      }
    }

    if (!valid) return;

    dispatch('apply', { from: customFrom, to: customTo });
  }

  function cancel() {
    dispatch('cancel');
  }
</script>

<div class="max-w-full shadow-lg border rounded-xl border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 text-sm text-gray-700 dark:text-gray-200">
  <label
    class="block text-xs ml-1 mt-1 text-gray-500 dark:text-gray-400"
    on:click|stopPropagation
  >
    From:
  </label>
  
  <div class="flex items-center border rounded-lg mt-1 ml-1 mr-1 px-2 py-1.5 text-sm border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 focus-within:ring-1 focus-within:ring-sky-500 transition"
    on:click|stopPropagation>
    <input 
      type="date" 
      bind:value={customFrom}
      bind:this={fromdateInput}
      class="flex-1 border-none outline-none bg-transparent text-gray-800 dark:text-gray-100"
    />
    <button
      type="button"
      on:click={() => fromdateInput.showPicker()}
      class="ml-1 text-gray-500 hover:text-sky-500 transition"
    >
      <CalendarIcon/>
    </button>
  </div>
  
  {#if fromError}
    <p class="text-red-500 text-xs mt-1 ml-1">{fromError}</p>
  {/if}

  {#if futuredateError}
    <p class="text-red-500 text-xs mt-1 ml-1">{futuredateError}</p>
  {/if}

  <label
    class="block mt-3 ml-1 text-xs text-gray-500 dark:text-gray-400"
    on:click|stopPropagation
  >
    To:
  </label>
  
  <div class="flex items-center border rounded-lg mt-1 ml-1 mr-1 px-2 py-1.5 text-sm border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 focus-within:ring-1 focus-within:ring-sky-500 transition"
    on:click|stopPropagation>
    <input
      type="date"
      bind:value={customTo}
      bind:this={todateInput}
      class="flex-1 border-none outline-none bg-transparent text-gray-800 dark:text-gray-100"
    />
    <button
      type="button"
      on:click={() => todateInput.showPicker()}
      class="ml-1 text-gray-500 hover:text-sky-500 transition"
    >
      <CalendarIcon/>
    </button>
  </div>

  {#if toError}
    <p class="text-red-500 text-xs mt-1 ml-1">{toError}</p>
  {/if}

  {#if checkdateError}
    <p class="text-red-500 text-xs mt-1 ml-1">{checkdateError}</p>
  {/if}

  {#if futuredateError}
    <p class="text-red-500 text-xs mt-1 ml-1">{futuredateError}</p>
  {/if}

  <div class="flex justify-end mt-4 gap-2"
    on:click|stopPropagation>
    <button
      class="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
      on:click={cancel}
    >
      Cancel
    </button>
    <button
      class="px-3 py-1.5 rounded-lg text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 transition"
      on:click={apply}
    > 
      Apply
    </button>
  </div>
</div>

<style>
  input[type="date"]::-webkit-calendar-picker-indicator {
    display: none;
    -webkit-appearance: none;
  }
</style>
