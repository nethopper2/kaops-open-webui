<script lang="ts">
import { getContext } from 'svelte';

const i18n = getContext('i18n');

// Placeholder for future action choices UI after chat has started
</script>

<div class="flex flex-col w-full h-full items-center justify-center py-8">
	<div class="text-sm text-gray-600 dark:text-gray-300 mb-3 text-center px-4">
		{$i18n.t('Token replacement session is active. Choose an action to continue.')}
	</div>
	<div class="grid grid-cols-1 gap-3 w-full max-w-sm">
		<button class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600">
			{$i18n.t('Edit Replacement Values')}
		</button>
		<button class="px-4 py-2 rounded bg-gray-700 text-white hover:bg-gray-800 dark:bg-gray-700 dark:hover:bg-gray-800">
			{$i18n.t('Generate Token Replacement Document')}
		</button>
		<button
			class="px-4 py-2 rounded bg-white border border-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:border-gray-700 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200">
			{$i18n.t('View document preview')}
		</button>
	</div>
</div>
