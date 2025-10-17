<script lang="ts">
	import { formatBytes } from '$lib/utils/format';
	import DataSyncTimeInfo from './DataSyncTimeInfo.svelte';
	import DataSyncDiscoveryInfo from './DataSyncDiscoveryInfo.svelte';

	export let files_processed: number = 0;
	export let files_total: number = 0;
	export let mb_processed: number = 0;
	export let mb_total: number = 0;
	export let sync_start_time: number = 0;
	export let bar_width: string = '12rem'; // Configurable progress bar width
	
	// Discovery information
	export let folders_found: number = 0;
	export let files_found: number = 0;
	export let total_size: number = 0;
	
	// Phase information
	export let phase: string = '';

	$: files_percentage = files_total > 0 ? Math.round((files_processed / files_total) * 100) : 0;
	$: mb_percentage = mb_total > 0 ? Math.round((mb_processed / mb_total) * 100) : 0;
	
</script>

<div class="flex flex-col h-full">
	{#if phase === 'starting' || phase === 'discovery'}
		<!-- During initialization phase: show discovery info only -->
		<div class="flex-1">
			<DataSyncDiscoveryInfo 
				{folders_found}
				{files_found}
				{total_size}
				{phase}
			/>
		</div>
		
		<!-- Time Info (always show, pegged to bottom) -->
		<div class="mt-auto">
			<DataSyncTimeInfo 
				{sync_start_time} 
				{files_processed} 
				{files_total}
			/>
		</div>
	{:else}
		<!-- During processing phase: show progress bars -->
		<div class="flex-1 space-y-0">
			<!-- Files Progress -->
			<div class="flex items-center">
				<span class="text-sm text-gray-600 dark:text-gray-400 pr-2 whitespace-nowrap">Files</span>
				<div class="ml-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2" style="width: {bar_width}">
					<div 
						class="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out" 
						style="width: {files_percentage}%"
					></div>
				</div>
				<span class="ml-2 text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap">
					{files_processed}/{files_total} ({files_percentage}%)
				</span>
			</div>

			<!-- Data Progress -->
			<div class="flex items-center">
				<span class="text-sm text-gray-600 dark:text-gray-400 pr-2 whitespace-nowrap">Data</span>
				<div class="ml-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2" style="width: {bar_width}">
					<div 
						class="bg-green-600 h-2 rounded-full transition-all duration-300 ease-out" 
						style="width: {mb_percentage}%"
					></div>
				</div>
				<span class="ml-2 text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap">
					{formatBytes(mb_processed)}/{formatBytes(mb_total)} ({mb_percentage}%)
				</span>
			</div>
		</div>

		<!-- Time Info (pegged to bottom) -->
		<div class="mt-auto">
			<DataSyncTimeInfo 
				{sync_start_time} 
				{files_processed} 
				{files_total}
			/>
		</div>
	{/if}
</div>
