<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import CalendarIcon from '../icons/CalendarSolid.svelte';

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

<div class="max-w-full shadow-lg border rounded border-gray-50 dark:border-gray-850">
  <label class="block text-xs ml-1" on:click|stopPropagation>From:</label>
  <div class="flex items-center border rounded mt-0.5 ml-1 mr-1 px-2 py-1 max-w-full text-sm"
    on:click|stopPropagation>
    <input type="text" bind:value={customFrom} placeholder="mm/dd/yy" class="flex-1 border-none outline-none bg-transparent"/>
    <button type="button">
      <CalendarIcon/>
    </button>
  </div>

  <label class="block mt-2 ml-1 text-xs" on:click|stopPropagation>To:</label>
  <div class="flex items-center border rounded mt-0.5 ml-1 mr-1 px-2 py-1 max-w-full text-sm"
    on:click|stopPropagation>
    <input type="text" bind:value={customTo} placeholder="mm/dd/yy" class="flex-1 border-none outline-none bg-transparent"/>
    <button type="button">
      <CalendarIcon/>
    </button>
  </div>

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
