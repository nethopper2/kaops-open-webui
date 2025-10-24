<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	export let sync_start_time: number = 0;
	export let files_processed: number = 0;
	export let files_total: number = 0;
	export let show_eta: boolean = true;

	// Configuration - centralized ETA update throttling
	const ETA_UPDATE_INTERVAL_MS = 5000; // 5 seconds

	// Real-time elapsed time calculation
	let current_time = Date.now();
	let timer: ReturnType<typeof setInterval>;

	// ETA throttling state
	let last_eta_update = 0;
	let throttled_eta_seconds = 0;
	let throttled_eta_formatted = '--:--';

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

	// Calculate ETA with throttling - only update every 5 seconds
	$: {
		const now = Date.now();
		const should_update_eta = (now - last_eta_update) >= ETA_UPDATE_INTERVAL_MS;
		
		if (should_update_eta && files_processed > 0 && files_total > files_processed && elapsed_time > 0) {
			// Calculate new ETA
			const new_eta_seconds = Math.round((elapsed_time * (files_total - files_processed)) / files_processed);
			const new_eta_minutes = Math.floor(new_eta_seconds / 60);
			const new_eta_seconds_remainder = new_eta_seconds % 60;
			
			// Update throttled values
			throttled_eta_seconds = new_eta_seconds;
			throttled_eta_formatted = `${new_eta_minutes}:${new_eta_seconds_remainder.toString().padStart(2, '0')}`;
			last_eta_update = now;
		}
	}

	// Use throttled ETA values - always show --:-- if show_eta is false
	$: eta_formatted = show_eta && files_processed > 0 && throttled_eta_seconds > 0 ? throttled_eta_formatted : '--:--';
</script>

<!-- Time Info -->
<div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-500 pt-1">
	<span>Elapsed: {elapsed_formatted}</span>
	<span>ETA: {eta_formatted}</span>
</div>
