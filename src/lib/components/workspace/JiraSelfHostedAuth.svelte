<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import Spinner from '../common/Spinner.svelte';
	import type { DataSource } from '$lib/types';
	import { atlassianSelfHostedAuth } from '$lib/apis/data';
	import Jira from '../icons/Jira.svelte';
	import Confluence from '../icons/Confluence.svelte';

	export let show = false;
	export let dataSource: DataSource | null = null;

	const dispatch = createEventDispatcher();

	let pat = '';
	let loading = false;
	let error = '';

	const getIconComponent = (iconName: string) => {
		const iconMap = {
			JIRA: Jira,
			Confluence: Confluence
		} as const;
		return iconMap[iconName as keyof typeof iconMap];
	};

	const handleSubmit = async () => {
		if (!pat || !dataSource) return;

		error = '';
		loading = true;

		try {
			const response = await atlassianSelfHostedAuth(pat, dataSource.layer || 'jira');

			if (response.ok) {
				const result = await response.json();
				console.log('Self-hosted Jira auth successful:', result);

				// Reset form
				pat = '';
				show = false;

				// Notify parent component
				dispatch('authSuccess', { dataSource });
			} else {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Authentication failed');
			}
		} catch (err) {
			const errorMessage = err instanceof Error ? err.message : 'An error occurred';

			// Provide user-friendly error messages
			if (errorMessage.includes('401') || errorMessage.includes('Authentication failed')) {
				error = 'Invalid username or password. Please try again.';
			} else if (errorMessage.includes('connection') || errorMessage.includes('fetch')) {
				error = 'Cannot connect to Jira server. Please check your connection.';
			} else {
				error = errorMessage;
			}
		} finally {
			loading = false;
		}
	};

	const handleClose = () => {
		pat = '';
		error = '';
		show = false;
		dispatch('close');
	};

	const handleKeydown = (e: KeyboardEvent) => {
		if (e.key === 'Escape') {
			handleClose();
		}
	};
</script>

<svelte:window on:keydown={handleKeydown} />

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		on:click={handleClose}
		role="presentation"
	>
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<dialog
			class="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden"
			on:click|stopPropagation
			open
			aria-labelledby="dialog-title"
		>
			<!-- Header -->
			<div class="border-b border-gray-200 dark:border-gray-700 px-6 py-4">
				<h2
					id="dialog-title"
					class="text-xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2"
				>
					<svelte:component this={getIconComponent(dataSource.icon)} className="size-5" />
					Connect to {dataSource?.layer}
				</h2>
				<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
					Enter your {dataSource?.layer} credentials to sync issues
				</p>
			</div>

			<!-- Form -->
			<form on:submit|preventDefault={handleSubmit} class="p-6 space-y-4">
				<!-- Username -->
				<div>
					<label
						for="jira-username"
						class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
					>
						Personal Access Token
					</label>
					<input
						id="jira-pat"
						type="text"
						bind:value={pat}
						required
						disabled={loading}
						class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
						       focus:ring-2 focus:ring-blue-500 focus:border-blue-500
						       bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100
						       disabled:opacity-50 disabled:cursor-not-allowed
						       transition-colors"
						placeholder="your.pat"
						autocomplete="Personal Access Token"
					/>
				</div>

				<!-- Error Message -->
				{#if error}
					<div
						class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800
						       rounded-lg p-3 text-sm text-red-700 dark:text-red-400"
						role="alert"
					>
						{error}
					</div>
				{/if}

				<!-- Buttons -->
				<div class="flex gap-3 pt-2">
					<button
						type="button"
						on:click={handleClose}
						disabled={loading}
						class="flex-1 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300
						       bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600
						       rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={loading || !pat}
						class="flex-1 px-4 py-2.5 text-sm font-medium text-white
						       bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors
						       disabled:opacity-50 disabled:cursor-not-allowed
						       flex items-center justify-center gap-2"
					>
						{#if loading}
							<Spinner className="w-4 h-4" />
							<span>Connecting...</span>
						{:else}
							<span>Connect</span>
						{/if}
					</button>
				</div>
			</form>
		</dialog>
	</div>
{/if}
