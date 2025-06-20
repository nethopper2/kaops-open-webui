import { onUnmounted, useHost } from 'vue';
import { appHooks } from '$lib/utils/hooks';

/**
 * Composable for handling theme switching in Vue components that need to
 * inject stylesheets into both document.head and shadowRoot.
 *
 * @returns Theme-related methods: loadTheme, loadDarkTheme, loadLightTheme, unloadCurrentTheme
 */
export function useTheme(options?: {
	themeChangedCallback?: (mode: string) => void,
	svelteHost?: ReturnType<typeof useHost>
}) {
	const svelteHost = options?.svelteHost || useHost();
	let unregisterHooks: () => void;

	/**
	 * Loads a stylesheet by creating link elements in both document head and shadowRoot
	 * @param href Path to the stylesheet
	 */
	function loadTheme(href: string) {
		unloadCurrentTheme();

		const linkHead = document.createElement('link');
		linkHead.setAttribute('rel', 'stylesheet');
		linkHead.setAttribute('href', href);
		linkHead.setAttribute('data-loaded-theme-head', 'true'); // easier removal later
		document.head.appendChild(linkHead);

		const link = document.createElement('link');
		link.setAttribute('rel', 'stylesheet');
		link.setAttribute('href', href);
		link.setAttribute('data-loaded-theme', 'true'); // easier removal later
		svelteHost?.shadowRoot?.appendChild?.(link);
	}

	/**
	 * Loads the dark theme stylesheet
	 */
	function loadDarkTheme() {
		// REMINDER: If the devextreme dependency is upgraded, you may need to
		// re-copy the styles from `devextreme/dist/css`
		loadTheme('/themes/vendor/dx.dark.css');
		console.log('loaded dark theme');
		if (typeof options?.themeChangedCallback === 'function') {
			options.themeChangedCallback('dark');
		}
	}

	/**
	 * Loads the light theme stylesheet
	 */
	function loadLightTheme() {
		// REMINDER: If the devextreme dependency is upgraded, you may need to
		// re-copy the styles from `devextreme/dist/css`
		loadTheme('/themes/vendor/dx.light.css');
		console.log('loaded light theme');
		if (typeof options?.themeChangedCallback === 'function') {
			options.themeChangedCallback('light');
		}
	}

	/**
	 * Removes any previously loaded theme stylesheets
	 */
	function unloadCurrentTheme() {
		const linkHead = document.head.querySelector('link[data-loaded-theme-head="true"]');
		if (linkHead) {
			console.log('removed theme from head');
			linkHead.remove();
		}

		const link = svelteHost?.shadowRoot?.querySelector?.('link[data-loaded-theme="true"]');
		if (link) {
			console.log('removed theme from shadowRoot');
			link.remove();
		}
	}

	/**
	 * Sets up theme based on current document state and registers hook for theme changes
	 * @returns Function to unregister hooks on component unmount
	 */
	function setupTheme() {
		// load the proper theme based on the host
		if (document.documentElement.classList.contains('dark')) {
			loadDarkTheme();
		} else {
			loadLightTheme();
		}

		unregisterHooks = appHooks.hook('theme.changed', ({ mode }) => {
			if (mode === 'dark') {
				loadDarkTheme();
			} else {
				loadLightTheme();
			}
		});

		return unregisterHooks;
	}

	onUnmounted(() => {
		unregisterHooks();
	});

	return {
		loadTheme,
		loadDarkTheme,
		loadLightTheme,
		unloadCurrentTheme,
		setupTheme
	};
}
