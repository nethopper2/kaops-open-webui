<script lang="ts">
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { getContext, onMount } from 'svelte';
import { WEBUI_NAME } from '$lib/stores';
import Spinner from '../common/Spinner.svelte';
import Link from '$lib/components/icons/Link.svelte';
import Info from '$lib/components/icons/Info.svelte';
import Modal from '$lib/components/common/Modal.svelte';

dayjs.extend(relativeTime);

let TRefFileMgr: unknown;

const i18n = getContext('i18n');

let loaded = false;
let showInfo = false;

onMount(async () => {
	// knowledgeBases = await getKnowledgeBaseList(localStorage.token);
	// TODO: Possibly load data here?
	loaded = true;
});
</script>

<svelte:head>
	<title>
		{$i18n.t('Knowledge')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div class="flex flex-col h-full pb-4">
		<div class="flex flex-col gap-1 my-1.5">
			<div class="flex justify-between items-center">
				<div class="flex items-center">
					<div class="flex md:self-center text-xl font-medium px-0.5 items-center">
						{$i18n.t('Knowledge')}
						<div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
					</div>

					<div class="relative inline-block">
						<!-- Info Icon Button -->
						<button
							on:click={() => showInfo = !showInfo}
							class="p-1 rounded-full focus:outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
							aria-label="Show more information"
							type="button"
						>
							<Info/>
						</button>
					</div>

					<Modal bind:show={showInfo}>
						<!-- Popover Info Box -->
						<div class="flex flex-col gap-2 p-4 dark:text-white">
							<div class="text-xl font-medium">{$i18n.t('Knowledge')}</div>
							<div class="text-pretty">
								<p>{$i18n.t('Data automatically populates collections based on their sources, using SSO credentials and group information. This setup supports cross-service searching and AI-driven insight, while enforcing access controls through SSO authentication and maintaining privacy safeguards with role-based permissions.')}</p>
								<p>{$i18n.t('Currently, only Google Drive supports data import for the Knowledge collections. To change the content that the AI uses, update or modify the files stored in your Google Drive. The system will then reflect those changes in the corresponding collection, ensuring the AI works with your latest documents.')}</p>
							</div>
						</div>
					</Modal>
				</div>
				<div>
					<a
						href="https://drive.google.com"
						target="_blank"
						rel="noopener noreferrer"
						class="inline-flex items-center gap-1 px-3.5 py-2 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
						aria-label={$i18n.t('Open Google Drive')}
					>
						<Link />
						{$i18n.t('Open Google Drive')}
					</a>
				</div>
			</div>
		</div>



		<div class="grow flex flex-col gap-3">
			<file-manager class="grow" i18n={$i18n} bind:this={TRefFileMgr} />
		</div>
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner />
	</div>
{/if}
