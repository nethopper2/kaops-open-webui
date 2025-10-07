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
			if (
				!backendConfig ||
				!backendConfig.private_ai ||
				!backendConfig.private_ai.nh_data_service_url
			) {
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

const originalContextMenuItems = ref(null);

function handleContextMenuShowing(e: ContextMenuShowingEvent) {
	// Prevent the context menu for root or empty paths
	if (!e.fileSystemItem?.path.length) {
		e.cancel = true; // Prevent the context menu from showing
		return;
	}

	// If the selected item is a directory, remove any "viewFile" entries from the menu items.
	// DevExtreme uses e.items to construct the menu; filtering that array is the most reliable way
	// to prevent a menu item from appearing.
	try {
		// Get current items
		let items = e.component.option('contextMenu.items');

		// Lazily capture unmodified original on first invocation
		if (!originalContextMenuItems.value) {
			originalContextMenuItems.value = JSON.parse(JSON.stringify(items));
		}

		// Always clone from original to avoid persistence
		let newItems = JSON.parse(JSON.stringify(originalContextMenuItems.value));

		// Conditionally modify only for directories
		if (e.fileSystemItem && e.fileSystemItem.isDirectory) {
			const modifyItemVisibility = (item) => {
				if (item?.options?.action === 'viewFile') {
					item.visible = false; // Hide for directories (or item.disabled = true; to gray out)
				}
				if (item.items && item.items.length > 0) {
					item.items.forEach(modifyItemVisibility);
				}
			};

			newItems.forEach(modifyItemVisibility);
		}

		// Set the context-specific version for this menu showing
		e.component.option('contextMenu.items', newItems);
	} catch (err) {
		// Be defensive: if anything goes wrong, don't block the menu entirely.
		console.warn('Error adjusting context menu visibility', err);
	}
	
	// Cancel context menu for directories
	if (e.fileSystemItem.isDirectory) {
		e.cancel = true;
		return;
	}
	
	// Store the current file item for files
	currentFileItem.value = e.fileSystemItem;
}

const showEditMetadataPopup = ref(false);

// Computed property for context menu items
const contextMenuItems = computed(() => {
	const items = [];
	
	// Add "Edit Metadata" for files
	if (currentFileItem.value && !currentFileItem.value.isDirectory) {
		items.push({
			text: i18nRef.value?.t?.('Edit Metadata') ?? 'Edit Metadata',
			options: { action: 'editMetadata' }
		});
	}
	items.push({
    text: 18nRef?.t?.('View File') ?? 'View File',
    options: { action: 'viewFile' } 
  })
	return items;
});

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

		<dx-context-menu
			:items="contextMenuItems"
		/>

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
