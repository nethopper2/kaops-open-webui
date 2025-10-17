<script lang="ts">
	import { formatBytes } from '$lib/utils/format';
	import { onMount, onDestroy } from 'svelte';

	export let files_processed: number = 0;
	export let files_total: number = 0;
	export let mb_processed: number = 0;
	export let mb_total: number = 0;
	export let sync_start_time: number = 0;
	export let bar_width: string = '12rem'; // Configurable progress bar width

	$: files_percentage = files_total > 0 ? Math.round((files_processed / files_total) * 100) : 0;
	$: mb_percentage = mb_total > 0 ? Math.round((mb_processed / mb_total) * 100) : 0;
	
	// Real-time elapsed time calculation
	let current_time = Date.now();
	let timer: number;

	onMount(() => {
		// Update current_time every second for real-time elapsed calculation
		timer = setInterval(() => {
			current_time = Date.now();
		}, 1000);
	});

	onDestroy(() => {
		if (timer) {
			clearInterval(timer);
		}
	});

	// Calculate elapsed time - ensure we have valid sync_start_time
	$: elapsed_time = sync_start_time > 0 ? Math.max(0, Math.floor((current_time / 1000) - sync_start_time)) : 0;
	$: elapsed_minutes = Math.floor(elapsed_time / 60);
	$: elapsed_seconds = elapsed_time % 60;
	$: elapsed_formatted = sync_start_time > 0 ? 
		`${elapsed_minutes}:${elapsed_seconds.toString().padStart(2, '0')}` : '--:--';

	// Calculate ETA - only show when we have processed at least 1 file and valid elapsed time
	$: eta_seconds = files_processed > 0 && files_total > files_processed && elapsed_time > 0 ? 
		Math.round((elapsed_time * (files_total - files_processed)) / files_processed) : 0;
	$: eta_minutes = Math.floor(eta_seconds / 60);
	$: eta_seconds_remainder = eta_seconds % 60;
	$: eta_formatted = files_processed > 0 && eta_seconds > 0 ? 
		`${eta_minutes}:${eta_seconds_remainder.toString().padStart(2, '0')}` : '--:--';
</script>

<div class="space-y-0">
	<!-- Files Progress -->
	<div class="flex items-center">
		<span class="text-sm text-gray-600 dark:text-gray-400 pr-2">Files</span>
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
		<span class="text-sm text-gray-600 dark:text-gray-400 pr-2">Data</span>
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

	<!-- Time Info -->
	<div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-500 pt-1">
		<span>Elapsed: {elapsed_formatted}</span>
		<span>ETA: {eta_formatted}</span>
	</div>
</div>
