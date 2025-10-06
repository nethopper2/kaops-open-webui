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
import { downloadProxyResource } from '$lib/utils/privateAi';

const props = defineProps(['i18n']);
const svelteHost = useHost();

const i18nRef = ref<any>(null);
const i18nReady = computed(() => !!(i18nRef.value && typeof i18nRef.value.t === 'function'));

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

async function handleContextMenuItemClick(e: ContextMenuItemClickEvent) {
	if (e.itemData.options.action === 'editMetadata') {
		currentFileItem.value = e.fileSystemItem;
		showEditMetadataPopup.value = true;
	} else if (e.itemData.options.action === 'viewFile') {
		try {
			const backendConfig = await getBackendConfig();
			if (!backendConfig || !backendConfig.private_ai || !backendConfig.private_ai.nh_data_service_url) {
				console.warn('Missing private_ai.nh_data_service_url in backend config', backendConfig);
				// Nothing more we can do here
				return;
			}

			// Build a proxy-download URL for the selected file.
			// DevExtreme file system items commonly expose a `path` (relative path) or `name`.
			const path = e.fileSystemItem?.path ?? e.fileSystemItem?.name ?? '';
			// Encode each path segment
			const encodedPath = path.split('/').map(encodeURIComponent).join('/');
			const base = backendConfig.private_ai.nh_data_service_url.replace(/\/$/, '');
			const target = new URL(`${base}/files/${encodedPath}/proxy-download`);

			// Use the shared util. Bypass allowlist because FileManager is a trusted UI flow.
			await downloadProxyResource(target, backendConfig, { bypassAllowlist: true });
		} catch (err) {
			console.error('Failed to open file', err);
		}
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

	fileSystemProvider = new RemoteFileSystemProvider({
		endpointUrl: `${backendConfig.private_ai.nh_data_service_url}/files/devextreme`,
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
		:root-folder-name="i18nRef?.t?.('Knowledge Data') ?? 'Knowledge Data'"
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
			<dx-item
				:text="i18nRef?.t?.('Edit Metadata') ?? 'Edit Metadata'"
				:options="{ action: 'editMetadata' }"
			/>
			<dx-item
				:text="i18nRef?.t?.('View File') ?? 'View File'"
				:options="{ action: 'viewFile' }"
			/>
		</dx-context-menu>

		<dx-item-view>
			<dx-details>
				<dx-column data-field="thumbnail" />
				<dx-column data-field="name" />
				<dx-column
					data-field="dateModified"
					dataType="datetime"
					:caption="i18nRef?.t?.('Date Modified') ?? 'Date Modified'"
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
		:i18n="i18nRef || props.i18n"
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
