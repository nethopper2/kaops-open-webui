<script lang="ts">
	import { formatBytes } from '$lib/utils/format';

	export let folders_found: number = 0;
	export let files_found: number = 0;
	export let total_size: number = 0;
	export let phase: string = '';
</script>

<!-- Discovery Info (show during starting phase or when we have discovery data) -->
{#if phase === 'starting' || folders_found > 0 || files_found > 0}
	<div class="text-xs text-gray-500 dark:text-gray-400 pb-1">
		<div>
			<span class="text-blue-600 dark:text-blue-400">{files_found}</span> files, 
			<span class="text-blue-600 dark:text-blue-400">{folders_found}</span> folders
		</div>
		<div>
			<span class="text-green-600 dark:text-green-400">{formatBytes(total_size).split(' ')[0]}</span> {formatBytes(total_size).split(' ')[1]} total size
		</div>
	</div>
{/if}
