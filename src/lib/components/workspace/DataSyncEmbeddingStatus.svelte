<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { formatBytes } from '$lib/utils/format';
	import { WEBUI_BASE_URL } from '$lib/constants';

	export let dataSource: any; // DataSource type

	// Polling configuration
	const POLLING_INTERVAL_MS = 10000; // 10 seconds
	const MAX_POLLING_ATTEMPTS = 100; // 5 minutes max

	// State
	let embeddingStatus: any = null;
	let pollingTimer: ReturnType<typeof setInterval> | null = null;
	let pollingAttempts = 0;
	let isPolling = false;
	let hasError = false;
	let errorMessage = '';

	// Exit criteria configuration
	const EXIT_CRITERIA = {
		MAX_ACTIVE: 0,
		MAX_WAITING: 1
	};

	onMount(() => {
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});

	async function fetchEmbeddingStatus() {
		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/data/embedding/status`, {
				method: 'GET',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include'
			});

			if (!response.ok) {
				hasError = true;
				errorMessage = 'Error reaching the ingestion server.';
				return;
			}

			// Reset error state on successful response
			hasError = false;
			errorMessage = '';

			const responseData = await response.json();
			
			// Find the matching source for this data source
			const matchingSource = responseData.sources?.find((source: any) => {
				// Match by name and subSource (layer) - handle case differences
				const nameMatch = source.name?.toLowerCase() === dataSource.action?.toLowerCase();
				const layerMatch = source.subSource?.toLowerCase().replace(/\s+/g, '_') === dataSource.layer?.toLowerCase();
				return nameMatch && layerMatch;
			});
			
			if (matchingSource) {
				embeddingStatus = {
					counts: matchingSource.counts,
					totalSize: responseData.totalSize || 0,
					lastUpdated: new Date().toISOString()
				};
			} else {
				// No matching source found - might be no jobs for this source
				embeddingStatus = {
					counts: { waiting: 0, active: 0, completed: 0, failed: 0 },
					totalSize: 0,
					lastUpdated: new Date().toISOString()
				};
			}
			
			pollingAttempts++;

			// Check exit criteria
			if (shouldExitEmbedding()) {
				stopPolling();
				await transitionToSyncedState();
			}

		} catch (error) {
			console.error('Failed to fetch embedding status:', error);
			// Continue polling on error
		}
	}

	function shouldExitEmbedding(): boolean {
		if (!embeddingStatus?.counts) return false;
		
		const { active, waiting, completed, failed } = embeddingStatus.counts;
		
		// If all jobs are completed or failed, exit regardless of waiting
		if (active === 0 && (completed > 0 || failed > 0)) {
			return true;
		}
		
		// Original criteria for partial completion
		return active <= EXIT_CRITERIA.MAX_ACTIVE && 
		       waiting <= EXIT_CRITERIA.MAX_WAITING &&
		       (completed > 0 || failed > 0);
	}

	function startPolling() {
		if (isPolling) return;
		
		isPolling = true;
		pollingAttempts = 0;
		
		// Initial fetch
		fetchEmbeddingStatus();
		
		// Set up polling timer
		pollingTimer = setInterval(() => {
			if (pollingAttempts >= MAX_POLLING_ATTEMPTS) {
				console.warn('Max polling attempts reached - stopping');
				stopPolling();
				return;
			}
			fetchEmbeddingStatus();
		}, POLLING_INTERVAL_MS);
	}

	function stopPolling() {
		if (pollingTimer) {
			clearInterval(pollingTimer);
			pollingTimer = null;
		}
		isPolling = false;
	}

	async function transitionToSyncedState() {
		try {
			const token = localStorage.getItem('token') || localStorage.getItem('access_token');
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/data/source/${dataSource.id}/sync`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${token}`
				},
				body: JSON.stringify({
					sync_status: 'synced',
					last_sync: Math.floor(Date.now() / 1000)
				})
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}
		} catch (error) {
			console.error('Failed to transition to synced state:', error);
		}
	}

	// Calculate progress percentages for each state
	$: totalJobs = embeddingStatus?.counts ? 
		Object.values(embeddingStatus.counts).reduce((sum: number, count: any) => sum + count, 0) : 0;
	
	$: waitingPercentage = totalJobs > 0 ? (embeddingStatus?.counts?.waiting || 0) / totalJobs * 100 : 0;
	$: activePercentage = totalJobs > 0 ? (embeddingStatus?.counts?.active || 0) / totalJobs * 100 : 0;
	$: completedPercentage = totalJobs > 0 ? (embeddingStatus?.counts?.completed || 0) / totalJobs * 100 : 0;
	$: failedPercentage = totalJobs > 0 ? (embeddingStatus?.counts?.failed || 0) / totalJobs * 100 : 0;
	$: delayedPercentage = totalJobs > 0 ? (embeddingStatus?.counts?.delayed || 0) / totalJobs * 100 : 0;
</script>

<div class="text-xs text-gray-500 dark:text-gray-400">
	<div class="space-y-2">
		{#if hasError}
			<!-- Error State -->
			<div class="space-y-1">
				<div class="text-xs text-red-500 dark:text-red-400">
					{errorMessage}
				</div>
				<div class="flex items-center gap-2">
					<div class="flex h-4 bg-gray-300 dark:bg-gray-600 rounded-full overflow-hidden" style="width: min(85%, 400px);">
						<!-- Gray progress bar for error state -->
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
						Unable to load
					</div>
				</div>
			</div>
		{:else if embeddingStatus}
			<!-- Segmented Progress Bar -->
			<div class="space-y-1">
				<!-- Color Legend with Numbers -->
				<div class="flex gap-4 text-xs whitespace-nowrap w-full">
					<span class="text-blue-600 dark:text-blue-400 whitespace-nowrap">
						{embeddingStatus.counts.waiting} waiting
					</span>
					<span class="text-purple-600 dark:text-purple-400 whitespace-nowrap">
						{embeddingStatus.counts.active} active
					</span>
					<span class="text-yellow-600 dark:text-yellow-400 whitespace-nowrap">
						{embeddingStatus.counts.delayed} delayed
					</span>
					<span class="text-green-600 dark:text-green-400 whitespace-nowrap">
						{embeddingStatus.counts.completed} completed
					</span>
					<span class="text-red-600 dark:text-red-400 whitespace-nowrap">
						{embeddingStatus.counts.failed} failed
					</span>
				</div>
				
				<!-- Progress Bar -->
				<div class="flex items-center gap-2">
					<div class="flex h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden" style="width: min(85%, 400px);">
						{#if waitingPercentage > 0}
							<div 
								class="bg-blue-500 h-full transition-all duration-300"
								style="width: {waitingPercentage}%"
								title="Waiting: {embeddingStatus.counts.waiting}"
							></div>
						{/if}
						{#if activePercentage > 0}
							<div 
								class="bg-purple-500 h-full transition-all duration-300"
								style="width: {activePercentage}%"
								title="Active: {embeddingStatus.counts.active}"
							></div>
						{/if}
						{#if delayedPercentage > 0}
							<div 
								class="bg-yellow-500 h-full transition-all duration-300"
								style="width: {delayedPercentage}%"
								title="Delayed: {embeddingStatus.counts.delayed}"
							></div>
						{/if}
						{#if completedPercentage > 0}
							<div 
								class="bg-green-500 h-full transition-all duration-300"
								style="width: {completedPercentage}%"
								title="Completed: {embeddingStatus.counts.completed}"
							></div>
						{/if}
						{#if failedPercentage > 0}
							<div 
								class="bg-red-500 h-full transition-all duration-300"
								style="width: {failedPercentage}%"
								title="Failed: {embeddingStatus.counts.failed}"
							></div>
						{/if}
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
						{totalJobs} files
					</div>
				</div>

			</div>

			<!-- Additional Info -->
			{#if embeddingStatus.totalSize}
				<div class="text-xs text-gray-500 dark:text-gray-400">
					Total size: {formatBytes(embeddingStatus.totalSize)}
				</div>
			{/if}
		{:else}
			<!-- Loading State -->
			<div class="flex items-center gap-2">
				<div class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-500"></div>
				<span>Loading embedding status...</span>
			</div>
		{/if}
	</div>
</div>
