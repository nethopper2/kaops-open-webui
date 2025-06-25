<script lang="ts">
import { models, showSettings, settings, user, mobile, config, isPublicModelChosen, type Model } from '$lib/stores';
import { onMount, tick, getContext, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Selector from './ModelSelector/Selector.svelte';
	import Tooltip from '../common/Tooltip.svelte';

	import { updateUserSettings } from '$lib/apis/users';
	import { isPrivateAiModel } from '$lib/utils/privateAi';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
import { appHooks } from '$lib/utils/hooks';
	const i18n = getContext('i18n');

	export let selectedModels = [''];
	export let disabled = false;

	export let showSetDefault = true;

	const saveDefaultModel = async () => {
		const hasEmptyModel = selectedModels.filter((it) => it === '');
		if (hasEmptyModel.length) {
			toast.error($i18n.t('Choose a model before saving...'));
			return;
		}
		settings.set({ ...$settings, models: selectedModels });
		await updateUserSettings(localStorage.token, { ui: $settings });

		toast.success($i18n.t('Default model updated'));
	};

	const pinModelHandler = async (modelId) => {
		let pinnedModels = $settings?.pinnedModels ?? [];

		if (pinnedModels.includes(modelId)) {
			pinnedModels = pinnedModels.filter((id) => id !== modelId);
		} else {
			pinnedModels = [...new Set([...pinnedModels, modelId])];
		}

		settings.set({ ...$settings, pinnedModels: pinnedModels });
		await updateUserSettings(localStorage.token, { ui: $settings });
	};

	$: if (selectedModels.length > 0 && $models.length > 0) {
		selectedModels = selectedModels.map((model) =>
			$models.map((m) => m.id).includes(model) ? model : ''
		);
	}


	// ============================================================================
	// NOTE: For now we are only handling setting isPublicModelChosen from here
	//       which will only occur from the chat area (the only area that
	//       currently cares since the user is making chat content choices from there)
	//       We can move to a more global way of handlig this later if needed.
	// ============================================================================
	// Handle ongoing changes
	$: updatePublicModelStatus(selectedModels, $models);

	let unregisterHooks: () => void;

	// Handle the initial load
	onMount(() => {
		unregisterHooks = appHooks.hook('models.select.privateOnly', () => {
			clearPublicModelSelection()
		})
		updatePublicModelStatus(selectedModels, $models);
	});

	onDestroy(() => {
		unregisterHooks();
	})

	function clearPublicModelSelection() {
		if (!selectedModels || !Array.isArray(selectedModels) || selectedModels.length === 0) {
			return;
		}

		if (!$models || !Array.isArray($models) || $models.length === 0) {
			return;
		}

		// Filter out public models, keeping only private models
		const privateModelsOnly = selectedModels.filter(modelId => {
			// Skip empty model IDs
			if (!modelId || modelId === '') {
				return false;
			}

			const model = $models.find(m => m.id === modelId);
			if (!model) {
				return false;
			}

			// Keep only private models (remove public ones)
			return isPrivateAiModel(model);
		});

		// If we have private models remaining, use those
		if (privateModelsOnly.length > 0) {
			selectedModels = privateModelsOnly;
			console.log('Cleared public models, remaining private models:', privateModelsOnly);
			return;
		}

		// If no private models remain, find and select the first available private model
		const availablePrivateModels = $models.filter(model => isPrivateAiModel(model));

		if (availablePrivateModels.length > 0) {
			// Select the first available private model
			selectedModels = [availablePrivateModels[0].id];
			console.log('No private models in selection, auto-selected first private model:', availablePrivateModels[0].id);
		} else {
			// No private models available at all, fallback to empty selection
			selectedModels = [''];
			console.log('No private models available, cleared selection');
		}
	}

	function updatePublicModelStatus(selectedModels: string[], modelsArray: Model[]) {
		if (!selectedModels) {
			isPublicModelChosen.set(true);
			return;
		}

		if (!Array.isArray(modelsArray)) {
			isPublicModelChosen.set(true);
			return;
		}

		if (selectedModels.length === 0) {
			isPublicModelChosen.set(true);
			return;
		}

		// Check if ANY selected model is public (not private)
		const hasPublicModel = selectedModels.some(modelId => {
			// Skip empty model IDs
			if (!modelId || modelId === '') {
				return false;
			}

			const model = modelsArray.find((m: Model) => m.id === modelId);
			const isPrivate = model ? isPrivateAiModel(model) : false;
			const isPublic = !isPrivate;
			return isPublic;
		});

		isPublicModelChosen.set(hasPublicModel);
	}
</script>

<div class="flex flex-col w-full items-start">
	{#each selectedModels as selectedModel, selectedModelIdx}
		<div class="flex w-full max-w-fit">
			<div class="overflow-hidden w-full">
				<div class="mr-1 max-w-full">
					<Selector
						id={`${selectedModelIdx}`}
						placeholder={$i18n.t('Select a model')}
						items={$models.map((model) => ({
							value: model.id,
							label: model.name,
							model: model
						}))}
						showTemporaryChatControl={$user?.role === 'user'
							? ($user?.permissions?.chat?.temporary ?? true) &&
								!($user?.permissions?.chat?.temporary_enforced ?? false)
							: true}
						{pinModelHandler}
						bind:value={selectedModel}
					/>
				</div>
			</div>

			{#if isPrivateAiModel($models.find((model) => model.id === selectedModel))}
				<Tooltip
					content={$i18n.t('Private AI Model')}
					placement="top"
					className=" flex items-center mr-1"
				>
					<LockClosed/>
				</Tooltip>
			{/if}

			{#if $user?.role === 'admin' || ($user?.permissions?.chat?.multiple_models ?? true)}
				{#if selectedModelIdx === 0}
					<div
						class="  self-center mx-1 disabled:text-gray-600 disabled:hover:text-gray-600 -translate-y-[0.5px]"
					>
						<Tooltip content={$i18n.t('Add Model')}>
							<button
								class=" "
								{disabled}
								on:click={() => {
									selectedModels = [...selectedModels, ''];
								}}
								aria-label="Add Model"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="2"
									stroke="currentColor"
									class="size-3.5"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
								</svg>
							</button>
						</Tooltip>
					</div>
				{:else}
					<div
						class="  self-center mx-1 disabled:text-gray-600 disabled:hover:text-gray-600 -translate-y-[0.5px]"
					>
						<Tooltip content={$i18n.t('Remove Model')}>
							<button
								{disabled}
								on:click={() => {
									selectedModels.splice(selectedModelIdx, 1);
									selectedModels = selectedModels;
								}}
								aria-label="Remove Model"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="2"
									stroke="currentColor"
									class="size-3"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 12h-15" />
								</svg>
							</button>
						</Tooltip>
					</div>
				{/if}
			{/if}
		</div>
	{/each}
</div>

{#if showSetDefault}
	<div
		class="absolute text-left mt-[1px] ml-1 text-[0.7rem] text-gray-600 dark:text-gray-400 font-primary"
	>
		<button on:click={saveDefaultModel}> {$i18n.t('Set as default')}</button>
	</div>
{/if}
