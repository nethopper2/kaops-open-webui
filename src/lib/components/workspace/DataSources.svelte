<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME } from '$lib/stores';
	import Search from '../icons/Search.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Google from '../icons/Google.svelte';
	import Microsoft from '../icons/Microsoft.svelte';
	import Slack from '../icons/Slack.svelte';
	import type { DataSource } from '$lib/types';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import {
		getDataSources,
		initializeDataSync,
		manualDataSync,
		disconnectDataSync
	} from '$lib/apis/data';

	const i18n: any = getContext('i18n');

	let loaded = false;
	let query = '';

	let dataSources: Array<DataSource> = [];

	let filteredItems = [];

	$: filteredItems = dataSources.filter(
		(ds) =>
			query === '' ||
			ds.name.toLowerCase().includes(query.toLowerCase()) ||
			ds.id.toLowerCase().includes(query.toLowerCase())
	);

	const formatDate = (dateString: string) => {
		const dateInMilliseconds = parseInt(dateString) * 1000;
		const date = new Date(dateInMilliseconds);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / (1000 * 60));
		const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
		const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

		if (diffMins < 1) return 'Just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;

		return date.toLocaleDateString();
	};

	const getSyncStatusColor = (status: string) => {
		switch (status) {
			case 'synced':
				return 'bg-green-500/20 text-green-700 dark:text-green-200';
			case 'syncing':
				return 'bg-blue-500/20 text-blue-700 dark:text-blue-200';
			case 'error':
				return 'bg-red-500/20 text-red-700 dark:text-red-200';
			case 'unsynced':
				return 'bg-yellow-500/20 text-yellow-700 dark:text-yellow-200';
			default:
				return 'bg-gray-500/20 text-gray-700 dark:text-gray-200';
		}
	};

	const getIconComponent = (iconName: string) => {
		const iconMap = {
			Google: Google,
			Microsoft: Microsoft,
			Slack: Slack
		} as const;
		return iconMap[iconName as keyof typeof iconMap];
	};

	const handleSync = (dataSource: DataSource) => {
		console.log('Syncing:', dataSource.name);

		switch ((dataSource.sync_status as string).toLowerCase()) {
			case 'synced':
				return updateSync(dataSource.action as string);
			case 'error':
				return updateSync(dataSource.action as string);
			case 'unsynced':
				return initializeSync(dataSource.action as string);
		}
	};

	const initializeSync = async (action: string) => {
		console.log('Initializing sync for:', action);

		let syncDetails = await initializeDataSync(localStorage.token, action);

		if (syncDetails.url) {
			window.open(syncDetails.url, '_blank');
		}

		dataSources = await getDataSources(localStorage.token);
	};

	const updateSync = async (action: string) => {
		console.log('Manual sync initiated for:', action);

		await manualDataSync(localStorage.token, action);

		dataSources = await getDataSources(localStorage.token);
	};

	const handleDelete = async (dataSource: DataSource) => {
		const action = dataSource.action;

		console.log('Disconnecting sync for:', action);

		await disconnectDataSync(localStorage.token, action as string);

		dataSources = await getDataSources(localStorage.token);
	};

	const getSyncStatusText = (status: string) => {
		switch (status) {
			case 'synced':
				return 'Synced';
			case 'syncing':
				return 'Syncing...';
			case 'error':
				return 'Error';
			case 'unsynced':
				return 'Unsynced';
			default:
				return 'Unknown';
		}
	};

	export const getBackendConfig = async () => {
		let error = null;

		const res = await fetch(`${WEBUI_BASE_URL}/api/config`, {
			method: 'GET',
			credentials: 'include',
			headers: {
				'Content-Type': 'application/json'
			}
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				console.log(err);
				error = err;
				return null;
			});

		if (error) {
			throw error;
		}

		return res;
	};

	onMount(async () => {
		// Initialize your data here
		dataSources = await getDataSources(localStorage.token);
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Data Sources')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div class="flex flex-col gap-1 my-1.5">
		<div class="flex justify-between items-center">
			<div class="flex md:self-center text-xl font-medium px-0.5 items-center">
				{$i18n.t('Data Sources')}
				<div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
				<span class="text-lg font-medium text-gray-500 dark:text-gray-300">
					{filteredItems.length}
				</span>
			</div>
		</div>

		<div class="flex w-full space-x-2">
			<div class="flex flex-1">
				<div class="self-center ml-1 mr-3">
					<Search className="size-3.5" />
				</div>
				<input
					class="w-full text-sm pr-4 py-1 rounded-r-xl outline-none bg-transparent"
					bind:value={query}
					placeholder={$i18n.t('Search Data Sources')}
				/>
			</div>
		</div>
	</div>

	<div class="mb-5">
		{#if filteredItems.length > 0}
			<div class="overflow-x-auto">
				<table class="w-full">
					<thead>
						<tr class="border-b border-gray-200 dark:border-gray-700">
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Name')}
							</th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Sync Status')}
							</th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Last Sync')}
							</th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Actions')}
							</th>
						</tr>
					</thead>
					<tbody>
						{#each filteredItems as dataSource}
							<tr
								class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
							>
								<td class="py-3 px-4">
									<div class="flex items-center gap-3">
										<div
											class="flex-shrink-0 w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center"
										>
											<svelte:component
												this={getIconComponent(dataSource.icon)}
												className="size-5"
											/>
										</div>
										<div class="flex flex-col">
											<div class="font-semibold text-gray-900 dark:text-gray-100">
												{dataSource.name}
											</div>
											<div class="text-xs text-gray-500 dark:text-gray-400">
												{dataSource.context}
											</div>
										</div>
									</div>
								</td>
								<td class="py-3 px-4">
									<div class="flex items-center gap-2">
										<span
											class="text-xs font-bold px-2 py-1 rounded-full uppercase {getSyncStatusColor(
												dataSource.sync_status
											)}"
										>
											{getSyncStatusText(dataSource.sync_status)}
										</span>
										{#if dataSource.sync_status === 'syncing'}
											<div class="w-3 h-3">
												<Spinner className="w-3 h-3" />
											</div>
										{/if}
									</div>
								</td>
								<td class="py-3 px-4">
									<div class="text-sm text-gray-700 dark:text-gray-300">
										{dataSource.last_sync ? formatDate(dataSource.last_sync) : 'Never'}
									</div>
								</td>
								<td class="py-3 px-4">
									<div class="flex items-center gap-2">
										<button
											class="px-2 py-1.5 text-xs font-medium rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:hover:bg-blue-900/30 dark:text-blue-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
											disabled={dataSource.sync_status === 'syncing'}
											on:click={() => handleSync(dataSource)}
										>
											{dataSource.sync_status === 'syncing' ? 'Syncing...' : 'Sync'}
										</button>
										<button
											class="px-2 py-1.5 text-xs font-medium rounded-lg bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-900/20 dark:hover:bg-red-900/30 dark:text-red-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
											disabled={dataSource.sync_status !== 'synced'}
											on:click={() => handleDelete(dataSource)}
										>
											Delete
										</button>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<div class="text-center py-8 text-gray-500 dark:text-gray-400">
				{query
					? $i18n.t('No data sources found matching your search.')
					: $i18n.t('No data sources available.')}
			</div>
		{/if}
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner />
	</div>
{/if}
