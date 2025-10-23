<script lang="ts">
	import { formatBytes } from '$lib/utils/format';

	export let dataSource: any; // DataSource type
	export let embeddingStatus: any = null; // Shared embedding status from parent

	// Exit criteria configuration
	const EXIT_CRITERIA = {
		MAX_ACTIVE: 0,
		MAX_WAITING: 1
	};

	// Get the matching source data from shared embedding status
	$: matchingSource = embeddingStatus?.[0]?.sources?.find((source: any) => {
		// Match by data_source field - format is "Google/Gmail"
		const expectedDataSource = `${dataSource.action}/${dataSource.layer}`;
		return source.data_source.toLowerCase() === expectedDataSource.toLowerCase();
	});
	

	$: sourceStatus = matchingSource ? {
		counts: matchingSource.counts,
		totalSize: 0, // New API structure doesn't include totalSize
		lastUpdated: new Date().toISOString()
	} : {
		counts: { waiting: 0, active: 0, completed: 0, failed: 0, delayed: 0, prioritized: 0, paused: 0, "waiting-children": 0 },
		totalSize: 0,
		lastUpdated: new Date().toISOString()
	};

	// Calculate progress percentages for each state
	$: totalJobs = sourceStatus?.counts ? 
		Object.values(sourceStatus.counts).reduce((sum: number, count: any) => sum + count, 0) : 0;
	
	$: waitingPercentage = totalJobs > 0 ? (sourceStatus?.counts?.waiting || 0) / totalJobs * 100 : 0;
	$: activePercentage = totalJobs > 0 ? (sourceStatus?.counts?.active || 0) / totalJobs * 100 : 0;
	$: completedPercentage = totalJobs > 0 ? (sourceStatus?.counts?.completed || 0) / totalJobs * 100 : 0;
	$: failedPercentage = totalJobs > 0 ? (sourceStatus?.counts?.failed || 0) / totalJobs * 100 : 0;
	$: delayedPercentage = totalJobs > 0 ? (sourceStatus?.counts?.delayed || 0) / totalJobs * 100 : 0;
	
</script>

<div class="text-xs text-gray-500 dark:text-gray-400">
	<div class="space-y-2">
		{#if sourceStatus}
			<!-- Segmented Progress Bar -->
			<div class="space-y-1">
				<!-- Color Legend with Numbers -->
				<div class="flex gap-4 text-xs whitespace-nowrap w-full">
					<span class="text-blue-600 dark:text-blue-400 whitespace-nowrap">
						{sourceStatus.counts.waiting} waiting
					</span>
					<span class="text-purple-600 dark:text-purple-400 whitespace-nowrap">
						{sourceStatus.counts.active} active
					</span>
					<span class="text-yellow-600 dark:text-yellow-400 whitespace-nowrap">
						{sourceStatus.counts.delayed} delayed
					</span>
					<span class="text-green-600 dark:text-green-400 whitespace-nowrap">
						{sourceStatus.counts.completed} completed
					</span>
					<span class="text-red-600 dark:text-red-400 whitespace-nowrap">
						{sourceStatus.counts.failed} failed
					</span>
				</div>
				
				<!-- Progress Bar -->
				<div class="flex items-center gap-2">
					<div class="flex h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden" style="width: min(85%, 400px);">
						{#if waitingPercentage > 0}
							<div 
								class="bg-blue-500 h-full transition-all duration-300"
								style="width: {waitingPercentage}%"
								title="Waiting: {sourceStatus.counts.waiting}"
							></div>
						{/if}
						{#if activePercentage > 0}
							<div 
								class="bg-purple-500 h-full transition-all duration-300"
								style="width: {activePercentage}%"
								title="Active: {sourceStatus.counts.active}"
							></div>
						{/if}
						{#if delayedPercentage > 0}
							<div 
								class="bg-yellow-500 h-full transition-all duration-300"
								style="width: {delayedPercentage}%"
								title="Delayed: {sourceStatus.counts.delayed}"
							></div>
						{/if}
						{#if completedPercentage > 0}
							<div 
								class="bg-green-500 h-full transition-all duration-300"
								style="width: {completedPercentage}%"
								title="Completed: {sourceStatus.counts.completed}"
							></div>
						{/if}
						{#if failedPercentage > 0}
							<div 
								class="bg-red-500 h-full transition-all duration-300"
								style="width: {failedPercentage}%"
								title="Failed: {sourceStatus.counts.failed}"
							></div>
						{/if}
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
						{totalJobs} files
					</div>
				</div>

			</div>

			<!-- Additional Info -->
			{#if sourceStatus.totalSize}
				<div class="text-xs text-gray-500 dark:text-gray-400">
					Total size: {formatBytes(sourceStatus.totalSize)}
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