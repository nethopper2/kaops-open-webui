<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import Spinner from '../common/Spinner.svelte';
	import Search from '../icons/Search.svelte';

	export let show = false;

	const dispatch = createEventDispatcher();

	interface JiraProject {
		id: string;
		key: string;
		name: string;
		description: string;
		avatarUrl: string;
		site_url: string;
		cloud_id: string;
	}

	let projects: JiraProject[] = [];
	let selectedProjects = new Set<string>();
	let loading = false;
	let syncing = false;
	let error = '';
	let searchQuery = '';

	$: filteredProjects = projects.filter(
		(p) =>
			searchQuery === '' ||
			p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
			p.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
			p.description.toLowerCase().includes(searchQuery.toLowerCase())
	);

	$: selectAll =
		filteredProjects.length > 0 && filteredProjects.every((p) => selectedProjects.has(p.key));

	$: selectNone = filteredProjects.every((p) => !selectedProjects.has(p.key));

	const loadProjects = async () => {
		loading = true;
		error = '';

		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/data/atlassian/projects`, {
				method: 'GET',
				headers: {
					Authorization: `Bearer ${localStorage.getItem('token')}`
				}
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to load projects');
			}

			const data = await response.json();
			projects = data.projects || [];
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load projects';
			console.error('Error loading projects:', err);
		} finally {
			loading = false;
		}
	};

	const toggleProject = (projectKey: string) => {
		if (selectedProjects.has(projectKey)) {
			selectedProjects.delete(projectKey);
		} else {
			selectedProjects.add(projectKey);
		}
		selectedProjects = selectedProjects; // Trigger reactivity
	};

	const toggleSelectAll = () => {
		if (selectAll) {
			// Deselect all filtered
			filteredProjects.forEach((p) => selectedProjects.delete(p.key));
		} else {
			// Select all filtered
			filteredProjects.forEach((p) => selectedProjects.add(p.key));
		}
		selectedProjects = selectedProjects;
	};

	const syncSelectedProjects = async () => {
		if (selectedProjects.size === 0) {
			error = 'Please select at least one project';
			return;
		}

		syncing = true;
		error = '';

		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/data/atlassian/sync-selected`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${localStorage.getItem('token')}`
				},
				body: JSON.stringify({
					project_keys: Array.from(selectedProjects),
					layer: 'jira'
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to start sync');
			}

			const data = await response.json();
			console.log('Sync started:', data);

			// Close modal and refresh parent
			dispatch('syncStarted', { projectCount: selectedProjects.size });
			closeModal();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to start sync';
			console.error('Error syncing projects:', err);
		} finally {
			syncing = false;
		}
	};

	const closeModal = () => {
		show = false;
		dispatch('close');
	};

	onMount(() => {
		if (show) {
			loadProjects();
		}
	});

	$: if (show) {
		loadProjects();
	}
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		on:click={closeModal}
		on:keydown={(e) => e.key === 'Escape' && closeModal()}
	>
		<div
			class="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col mx-4"
			on:click|stopPropagation
			on:keydown|stopPropagation
		>
			<!-- Header -->
			<div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
				<div class="flex items-center justify-between">
					<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
						Select Jira Projects to Sync
					</h2>
					<button
						class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
						on:click={closeModal}
					>
						<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M6 18L18 6M6 6l12 12"
							/>
						</svg>
					</button>
				</div>
				<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
					{selectedProjects.size} of {projects.length} projects selected
				</p>
			</div>

			<!-- Search and Select All -->
			<div class="px-6 py-3 border-b border-gray-200 dark:border-gray-700 space-y-3">
				<div class="flex items-center gap-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-3 py-2">
					<Search className="size-4 text-gray-400" />
					<input
						type="text"
						bind:value={searchQuery}
						placeholder="Search projects by name, key, or description..."
						class="flex-1 bg-transparent border-none outline-none text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400"
					/>
				</div>

				<div class="flex items-center justify-between">
					<button
						class="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
						on:click={toggleSelectAll}
					>
						{selectAll ? 'Deselect All' : 'Select All'}
						{searchQuery ? '(Filtered)' : ''}
					</button>
					<div class="text-xs text-gray-500 dark:text-gray-400">
						Showing {filteredProjects.length} of {projects.length} projects
					</div>
				</div>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto px-6 py-4">
				{#if loading}
					<div class="flex items-center justify-center py-12">
						<Spinner />
						<span class="ml-3 text-gray-600 dark:text-gray-400">Loading projects...</span>
					</div>
				{:else if error}
					<div
						class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4"
					>
						<div class="flex items-start gap-3">
							<svg
								class="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5"
								fill="currentColor"
								viewBox="0 0 20 20"
							>
								<path
									fill-rule="evenodd"
									d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
									clip-rule="evenodd"
								/>
							</svg>
							<div>
								<h3 class="text-sm font-medium text-red-800 dark:text-red-200">Error</h3>
								<p class="text-sm text-red-700 dark:text-red-300 mt-1">{error}</p>
							</div>
						</div>
					</div>
				{:else if filteredProjects.length === 0}
					<div class="text-center py-12">
						<svg
							class="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
							/>
						</svg>
						<p class="mt-4 text-gray-500 dark:text-gray-400">
							{searchQuery ? 'No projects match your search' : 'No projects available'}
						</p>
					</div>
				{:else}
					<div class="space-y-2">
						{#each filteredProjects as project}
							<button
								class="w-full flex items-center gap-4 p-4 rounded-lg border transition-all hover:shadow-md
									{selectedProjects.has(project.key)
									? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
									: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}"
								on:click={() => toggleProject(project.key)}
							>
								<div class="flex-shrink-0">
									<div
										class="w-10 h-10 rounded-lg flex items-center justify-center
										{selectedProjects.has(project.key) ? 'bg-blue-500' : 'bg-gray-200 dark:bg-gray-700'}"
									>
										{#if selectedProjects.has(project.key)}
											<svg
												class="w-6 h-6 text-white"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M5 13l4 4L19 7"
												/>
											</svg>
										{:else if project.avatarUrl}
											<img
												src={project.avatarUrl}
												alt={project.name}
												class="w-full h-full rounded-lg"
											/>
										{:else}
											<span class="text-gray-600 dark:text-gray-400 font-semibold text-sm">
												{project.key.substring(0, 2)}
											</span>
										{/if}
									</div>
								</div>

								<div class="flex-1 text-left min-w-0">
									<div class="flex items-center gap-2">
										<h3 class="font-semibold text-gray-900 dark:text-gray-100 truncate">
											{project.name}
										</h3>
										<span
											class="text-xs font-mono bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-gray-600 dark:text-gray-400 flex-shrink-0"
										>
											{project.key}
										</span>
									</div>
									{#if project.description}
										<p class="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
											{project.description}
										</p>
									{/if}
									<p class="text-xs text-gray-500 dark:text-gray-500 mt-1 truncate">
										{project.site_url}
									</p>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Footer -->
			<div class="px-6 py-4 border-t border-gray-200 dark:border-gray-700">
				<div class="flex items-center justify-between gap-4">
					<button
						class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
						on:click={closeModal}
						disabled={syncing}
					>
						Cancel
					</button>

					<button
						class="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
						on:click={syncSelectedProjects}
						disabled={syncing || selectedProjects.size === 0}
					>
						{#if syncing}
							<Spinner className="w-4 h-4" />
							<span>Starting Sync...</span>
						{:else}
							<span
								>Sync {selectedProjects.size} Project{selectedProjects.size !== 1 ? 's' : ''}</span
							>
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.line-clamp-2 {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
</style>
