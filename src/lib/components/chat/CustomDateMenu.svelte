<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import CalendarIcon from '../icons/CalendarSolid.svelte';

  let customFrom = '';
  let customTo = '';

  let fromError = '';
  let toError = '';
  let checkdateError = '';

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

      if (to < from) {
        checkdateError = "End date must be on or after start date."
        valid = false
      } else {
        checkdateError = "";
      }
    }

    if (!valid) return;

    dispatch('apply', { from: customFrom, to: customTo });
  }

  function cancel() {
    dispatch('cancel');
  }
</script>

<div class="max-w-full shadow-lg border rounded border-gray-50 dark:border-gray-850">
  <label class="block text-xs ml-1" on:click|stopPropagation>From:</label>
  <div class="flex items-center border rounded mt-0.5 ml-1 mr-1 px-2 py-1 max-w-full text-sm"
    on:click|stopPropagation>
    <input type="date" bind:value={customFrom} bind:this={fromdateInput} class="flex-1 border-none outline-none bg-transparent"/>
    <button type="button" on:click={() => fromdateInput.showPicker()}>
      <CalendarIcon/>
    </button>
  </div>
  
  {#if fromError}
    <p class="text-red-500 text-xs mt-1 ml-1">{fromError}</p>
  {/if}

  <label class="block mt-2 ml-1 text-xs" on:click|stopPropagation>To:</label>
  <div class="flex items-center border rounded mt-0.5 ml-1 mr-1 px-2 py-1 max-w-full text-sm"
    on:click|stopPropagation>
    <input type="date" bind:value={customTo} bind:this={todateInput} class="flex-1 border-none outline-none bg-transparent"/>
    <button type="button" on:click={() => todateInput.showPicker()}>
      <CalendarIcon/>
    </button>
  </div>

  {#if toError}
    <p class="text-red-500 text-xs mt-1 ml-1">{toError}</p>
  {/if}

  {#if checkdateError}
    <p class="text-red-500 text-xs mt-1 ml-1">{checkdateError}</p>
  {/if}

  <div class="flex justify-left text-sm mt-2 mb-0.5 ml-1 gap-53"
    on:click|stopPropagation>
    <button
      class="max-w-full text-sm font-small rounded px-1 py-1 hover:bg-gray-700 cursor-pointer"
      on:click={cancel}>
      Cancel
    </button>
    <button
      class="max-w-full  text-sm font-small rounded px-1 py-1 hover:bg-gray-700 cursor-pointer"
      on:click={apply}> 
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
