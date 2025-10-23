<script lang="ts">
	import type { DataSource } from '$lib/types';

	export let dataSource: DataSource;
	export let isError: boolean = false;

	// Helper function to safely access metadata
	function getMetadata(syncResults: any, key: string) {
		return syncResults && syncResults[key] ? syncResults[key] : null;
	}

	function formatBytes(bytes: number): string {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	function formatDuration(milliseconds: number): string {
		const totalSeconds = Math.floor(milliseconds / 1000);
		const hours = Math.floor(totalSeconds / 3600);
		const minutes = Math.floor((totalSeconds % 3600) / 60);
		const seconds = totalSeconds % 60;
		
		if (hours > 0) {
			return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
		} else {
			return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
		}
	}
</script>

<div class="text-xs text-gray-500 dark:text-gray-400">
	<div class="grid grid-cols-2 gap-2">
		<!-- Left Column: Last Ingest -->
		<div>
			<div class="font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1">
				Last Ingest
				{#if dataSource.sync_results?.latest_sync?.runtime_ms}
					<span class="text-xs text-gray-500 dark:text-gray-400 ml-1 font-normal">
						{formatDuration(dataSource.sync_results.latest_sync.runtime_ms)}
					</span>
				{/if}
				{#if dataSource.sync_results?.latest_sync}
					{@const latest = dataSource.sync_results.latest_sync}
					<div class="relative group ml-2">
						<svg class="w-3 h-3 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 cursor-help" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
						</svg>
						<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
							<div class="space-y-1">
								<div>📊 Files processed: {latest.added + latest.updated + latest.removed + latest.skipped}</div>
								{#if latest.skip_reasons && Object.keys(latest.skip_reasons).length > 0}
									<div class="mt-2 pt-2 border-t border-gray-600">
										<div class="font-medium">Skip Reasons:</div>
										{#each Object.entries(latest.skip_reasons) as [reason, count]}
											<div class="text-gray-300">• {reason}: {count}</div>
										{/each}
									</div>
								{/if}
							</div>
							<div class="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
						</div>
					</div>
				{/if}
			</div>
			{#if dataSource.sync_results?.latest_sync}
				{@const latest = dataSource.sync_results.latest_sync}
				<div class="space-y-1">
					<!-- First line: new and removed files -->
					<div class="flex gap-2 whitespace-nowrap">
						<span class="text-green-600 dark:text-green-400">+{latest.added} new</span>
						<span class="text-red-600 dark:text-red-400">-{latest.removed} removed</span>
					</div>
					<!-- Second line: updated and skipped files -->
					<div class="flex gap-2 whitespace-nowrap">
						<span class="text-blue-600 dark:text-blue-400">^{latest.updated} updated</span>
						<span class="text-yellow-600 dark:text-yellow-400">{latest.skipped} skipped</span>
					</div>
				</div>
			{:else}
				<div class="text-gray-500 dark:text-gray-400">No sync data</div>
			{/if}
		</div>

		<!-- Right Column: Source Summary -->
		<div>
			<div class="font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1">
				Source Summary
				{#if getMetadata(dataSource.sync_results, 'metadata')}
					{@const meta = getMetadata(dataSource.sync_results, 'metadata')}
					<div class="relative group">
						<svg class="w-3 h-3 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 cursor-help" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
						</svg>
						<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
							<div class="font-medium mb-1">Gmail Sync Details</div>
							<div class="space-y-1">
								<div>📧 {meta.emails_processed || 0} emails processed</div>
								{#if meta.newest_email_date}
									<div>🆕 Newest: {meta.newest_email_date} ({meta.newest_email_age_days || 0} days ago)</div>
								{/if}
								{#if meta.oldest_email_date}
									<div>📅 Oldest: {meta.oldest_email_date} ({meta.oldest_email_age_days || 0} days ago)</div>
								{/if}
								{#if meta.email_range_days}
									<div>📊 Time span: {meta.email_range_days} days</div>
								{/if}
							</div>
							<div class="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
						</div>
					</div>
				{:else if getMetadata(dataSource.sync_results, 'drive_metadata')}
					{@const driveMeta = getMetadata(dataSource.sync_results, 'drive_metadata')}
					<div class="relative group">
						<svg class="w-3 h-3 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 cursor-help" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
						</svg>
						<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
							<div class="font-medium mb-1">Google Drive Sync Details</div>
							<div class="space-y-1">
								<div>📁 {driveMeta.folders_processed || 0} folders</div>
								<div>📄 {driveMeta.files_processed || 0} files</div>
								{#if driveMeta.sync_range}
									<div class="text-gray-300">{driveMeta.sync_range}</div>
								{/if}
							</div>
							<div class="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
						</div>
					</div>
				{/if}
			</div>
			{#if dataSource.sync_results?.overall_profile}
				{@const profile = dataSource.sync_results.overall_profile}
				<div class="space-y-1">
					<div>{profile.total_files} files</div>
					<div>{formatBytes(profile.total_size_bytes)}</div>
					{#if profile.folders_count > 0}
						<div>{profile.folders_count} folders</div>
					{/if}
				</div>
			{:else if dataSource.files_total && dataSource.files_total > 0}
				<div class="space-y-1">
					<div>{dataSource.files_total} files</div>
					<div>{formatBytes(dataSource.mb_total || 0)}</div>
				</div>
			{:else}
				<div class="text-gray-500 dark:text-gray-400">
					No profile data
				</div>
			{/if}
		</div>
	</div>
</div>