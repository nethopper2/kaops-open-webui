<script setup lang="ts">
import {
	DxColumn,
	DxContextMenu,
	DxDetails,
	DxFileManager,
	DxItem,
	DxItemView,
	DxPermissions,
	DxToolbar
} from 'devextreme-vue/file-manager';
import RemoteFileSystemProvider from 'devextreme/file_management/remote_provider';
import type {
	ContextMenuItemClickEvent,
	ContextMenuShowingEvent
} from 'devextreme/ui/file_manager';
import { computed, onBeforeMount, onMounted, ref, useHost, watch } from 'vue';
import { getBackendConfig } from '$lib/apis';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import PopupMetadataEdit from './PopupMetadataEdit.vue';
import { useTheme } from '../composables/useTheme';

const props = defineProps(['i18n']);
const svelteHost = useHost();

const i18nRef = ref<any>(null);
const i18nReady = computed(() => !!(i18nRef.value && typeof i18nRef.value.t === 'function'));
// Provide a safe fallback i18n so children always have a t() available
const safeI18n = computed(() => {
	const candidate = i18nRef.value ?? props.i18n;
	if (candidate && typeof candidate.t === 'function') return candidate;
	return { t: (s: string) => s };
});

// Sync when prop arrives (if the CE prop bridge ever sets it)
watch(
	() => props.i18n,
	(val) => {
		if (val && typeof (val as any).t === 'function') {
			i18nRef.value = val;
		}
	},
	{ immediate: true }
);

// Also read from the host DOM property until it’s usable
onMounted(() => {
	// Try immediate pick up
	const initial = (svelteHost as any)?.i18n;
	if (initial) i18nRef.value = initial;

	if (!i18nReady.value) {
		const interval = setInterval(() => {
			const candidate = (svelteHost as any)?.i18n;
			if (candidate && typeof candidate.t === 'function') {
				i18nRef.value = candidate;
				clearInterval(interval);
			}
		}, 50);
		// Optional: stop after some time to avoid infinite polling
		setTimeout(() => clearInterval(interval), 5000);
	}
});

// Left as a reminder on how to expose methods as a custom element.
// if (svelteHost) {
// 	svelteHost.customMethod = () => {
// 		console.log('customMethod called');
// 	};
// }

const TRefFileManager = ref();

const loading = ref(true);
const currentFileItem = ref<FileSystemItem>();

let fileSystemProvider: RemoteFileSystemProvider;

async function waitForI18nReady(timeoutMs = 800) {
	if (i18nReady.value) return;
	await new Promise<void>((resolve) => {
		const start = Date.now();
		const iv = setInterval(() => {
			if (i18nReady.value || Date.now() - start > timeoutMs) {
				clearInterval(iv);
				resolve();
			}
		}, 25);
	});
}

async function handleContextMenuItemClick(e: ContextMenuItemClickEvent) {
	if (e.itemData.options.action === 'editMetadata') {
		currentFileItem.value = e.fileSystemItem;
		// Wait briefly so translated strings are available before opening
		await waitForI18nReady();
		showEditMetadataPopup.value = true;
	}
}

function handleContextMenuShowing(e: ContextMenuShowingEvent) {
	if (!e.fileSystemItem?.path.length) {
		e.cancel = true; // Prevent the context menu from showing
	}
}

const showEditMetadataPopup = ref(false);

// Use the theme composable
const { loadTheme, loadDarkTheme, loadLightTheme, unloadCurrentTheme, setupTheme } = useTheme({
	themeChangedCallback: () => {
		// and tell the FileManager to redraw
		TRefFileManager.value?.instance?.repaint?.();
	}
});

onBeforeMount(() => {
	setupTheme();
});

onMounted(async () => {
	loading.value = true;

	const backendConfig = await getBackendConfig();

	// Check if we should use the new nh-pai-data-service
	const useNewService = localStorage.getItem('use_nh_data_service') === 'true';

	let endpointUrl;
	if (useNewService) {
		// Use nh-pai-data-service
		endpointUrl = `${backendConfig.nh_data_service.url}/api/v1/files/devextreme`;
	} else {
		// Use original private-ai-rest service
		endpointUrl = `${backendConfig.private_ai.rest_api_base_url}/api/storage/file-manager`;
	}

	fileSystemProvider = new RemoteFileSystemProvider({
		endpointUrl: endpointUrl,
		requestHeaders: {
			Authorization: 'Bearer ' + localStorage.getItem('token')
		}
	});

	loading.value = false;
});
</script>

<template>
	<dx-file-manager
		v-if="!loading"
		ref="TRefFileManager"
		:file-system-provider="fileSystemProvider"
		:on-context-menu-item-click="handleContextMenuItemClick"
		:on-context-menu-showing="handleContextMenuShowing"
		:root-folder-name="(safeI18n.t?.('Knowledge Data')) ?? 'Knowledge Data'"
		v-bind="$attrs"
	>
		<dx-permissions
			:create="false"
			:copy="false"
			:move="false"
			:delete="false"
			:rename="false"
			:upload="false"
			:download="false"
		/>

		<dx-context-menu>
			<dx-item :text="(safeI18n.t?.('Edit Metadata')) ?? 'Edit Metadata'" :options="{ action: 'editMetadata' }" />
		</dx-context-menu>

		<dx-item-view>
			<dx-details>
				<dx-column data-field="thumbnail" />
				<dx-column data-field="name" />
				<dx-column
					data-field="dateModified"
					dataType="datetime"
					:caption="(safeI18n.t?.('Date Modified')) ?? 'Date Modified'"
					width="auto"
				/>
				<dx-column data-field="size" />
			</dx-details>
		</dx-item-view>

		<dx-toolbar>
			<dx-item name="showNavPane" :visible="true" />
			<dx-item name="refresh" />
			<dx-item name="separator" location="after" />
			<dx-item name="switchView" />
		</dx-toolbar>
	</dx-file-manager>

	<popup-metadata-edit
		v-model:visible="showEditMetadataPopup"
		:file-item="currentFileItem as FileSystemItem"
		:i18n="safeI18n"
	/>
</template>

<style>
/**
 * The fonts were copied from the node_module to the static directory in
 * /themes/vendor/icons/
 * The dark & light stylesheets were also copied. This is needed since the shadowRoot
 * was unable to use the font-face from the injected stylesheet.
 */
@font-face {
	font-family: DXIcons;
	src:
		local('DevExtreme Generic Icons'),
		local('devextreme_generic_icons'),
		url('/themes/vendor/icons/dxicons.woff2') format('woff2'),
		url('/themes/vendor/icons/dxicons.woff') format('woff'),
		url('/themes/vendor/icons/dxicons.ttf') format('truetype');
	font-weight: 400;
	font-style: normal;
}

.dx-filemanager {
	height: 100% !important;
}

/* a work around for hiding the checkboxes since selection-mode="none" causes a build error and is a hack */
.dx-filemanager .dx-checkbox {
	display: none !important;
}
</style>