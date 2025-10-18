<script lang="ts">
	import type { DataSource } from '$lib/types';

	export let dataSource: DataSource;

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
		<!-- Left Column: Latest Sync -->
		<div>
			<div class="font-medium text-gray-700 dark:text-gray-300 mb-1">
				Latest Sync
				{#if dataSource.sync_results?.latest_sync?.runtime_ms}
					<span class="text-xs text-gray-500 dark:text-gray-400 ml-2 font-normal">
						{formatDuration(dataSource.sync_results.latest_sync.runtime_ms)}
					</span>
				{/if}
			</div>
			{#if dataSource.sync_results?.latest_sync}
				{@const latest = dataSource.sync_results.latest_sync}
				<div class="space-y-1">
					<!-- First line: new and removed files -->
					<div class="flex gap-2">
						<span class="text-green-600 dark:text-green-400">+{latest.added} new</span>
						<span class="text-red-600 dark:text-red-400">-{latest.removed} removed</span>
					</div>
					<!-- Second line: updated and skipped files -->
					<div class="flex gap-2">
						<span class="text-blue-600 dark:text-blue-400">^{latest.updated} updated</span>
						<span class="text-yellow-600 dark:text-yellow-400">{latest.skipped} skipped</span>
					</div>
				</div>
			{:else}
				<div class="text-gray-500 dark:text-gray-400">No sync data</div>
			{/if}
		</div>

		<!-- Right Column: Overall Summary -->
		<div>
			<div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Overall Summary</div>
			{#if dataSource.sync_results?.overall_profile}
				{@const profile = dataSource.sync_results.overall_profile}
				<div class="space-y-1">
					<div>{profile.total_files} files</div>
					<div>{formatBytes(profile.total_size_bytes)}</div>
					{#if profile.folders_count > 0}
						<div>{profile.folders_count} folders</div>
					{/if}
				</div>
			{:else}
				<div class="text-gray-500 dark:text-gray-400">No profile data</div>
			{/if}
		</div>
	</div>
</div>