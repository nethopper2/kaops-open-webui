<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import GlobeIcon from '$lib/components/icons/GlobeAltSolid.svelte';
  import { settings } from '$lib/stores';

  const dispatch = createEventDispatcher();

  let webSearchEnabled = false;

  function toggleWebSearch() {
    webSearchEnabled = !webSearchEnabled;
    dispatch('toggle', { enabled: webSearchEnabled });
  }
</script>

<Tooltip
  content={webSearchEnabled ? 'Turn off web search' : 'Turn on web search'}
  placement="top"
>
  <button
    type="button"
    on:click={toggleWebSearch}
    class="px-2 @xl:px-2.5 py-2 flex gap-1.5 items-center text-sm rounded-full 
           transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden 
           hover:bg-gray-50 dark:hover:bg-gray-800
           {webSearchEnabled
              ? ' text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
              : 'bg-transparent text-gray-600 dark:text-gray-300'}"
  >
    <GlobeIcon class="size-4" strokeWidth="1.75" />
  </button>
</Tooltip>
