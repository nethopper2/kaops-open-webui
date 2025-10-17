<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	export let sync_start_time: number = 0;
	export let files_processed: number = 0;
	export let files_total: number = 0;

	// Real-time elapsed time calculation
	let current_time = Date.now();
	let timer: ReturnType<typeof setInterval>;

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

<!-- Time Info -->
<div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-500 pt-1">
	<span>Elapsed: {elapsed_formatted}</span>
	<span>ETA: {eta_formatted}</span>
</div>
