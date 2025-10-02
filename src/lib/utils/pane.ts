import { writable, type Writable, get } from 'svelte/store';

export type PaneHandle = {
	resize: (n: number) => void;
	isExpanded: () => boolean;
	getSize: () => number;
};

export const isPaneHandle = (x: unknown): x is PaneHandle => {
	if (!x || typeof x !== 'object') return false;
	const o = x as Record<string, unknown>;
	return (
		typeof o.resize === 'function' &&
		typeof o.isExpanded === 'function' &&
		typeof o.getSize === 'function'
	);
};

// Shared store for the current right-hand pane size (percentage)
export const rightPaneSize = writable<number>(0);

// Compute min size percentage for a pixel width relative to the container width.
export function calcMinSize(container: HTMLElement, pixels = 350): number {
	const width = container.clientWidth || 1;
	return Math.floor((pixels / width) * 100);
}

// Shared behavior for right-hand panes (Controls and Private AI Model sidekick)
export function createPaneBehavior(params: {
	storageKey: string;
	showStore: Writable<boolean>;
	isActiveInPaneGroup: () => boolean;
	getMinSize: () => number;
}) {
	const { storageKey, showStore, isActiveInPaneGroup, getMinSize } = params;

	let opening = false;
	let clampScheduled = false;

	const openPane = async (pane: PaneHandle | null | undefined, largeScreen: boolean) => {
		if (!largeScreen || !isActiveInPaneGroup() || !isPaneHandle(pane)) return;
		const storedRaw = localStorage.getItem(storageKey);
		const parsed = storedRaw ? parseInt(storedRaw) : NaN;
		const minSize = Math.max(getMinSize(), 1);
		const target = !Number.isNaN(parsed) && parsed > 0 ? parsed : minSize;

		opening = true;
		// Defer to avoid re-entrant Paneforge assertions
		const { tick } = await import('svelte');
		await tick();
		requestAnimationFrame(() => {
			try {
				if (get(showStore) && isActiveInPaneGroup() && isPaneHandle(pane)) {
					// Avoid redundant resize
					if (!pane.isExpanded() || pane.getSize() !== target) {
						pane.resize(target);
					}
				}
			} catch {
				// swallow; Paneforge will reconcile
			} finally {
				opening = false;
			}
		});
	};

	const clamp = (pane: PaneHandle | null | undefined, minSize?: number) => {
		if (!isPaneHandle(pane)) return;
		try {
			if (get(showStore) && isActiveInPaneGroup() && pane.isExpanded()) {
				const m = Math.max(minSize ?? getMinSize(), 1);
				if (pane.getSize() < m) pane.resize(m);
			}
		} catch {
			// ignore
		}
	};

	const scheduleClamp = (pane: PaneHandle | null | undefined, minSize?: number) => {
		if (clampScheduled) return;
		clampScheduled = true;
		setTimeout(() => {
			clampScheduled = false;
			if (!isPaneHandle(pane)) return;
			clamp(pane, minSize);
			// try {
			//   if (get(showStore) && isActiveInPaneGroup() && pane.isExpanded()) {
			//     const m = Math.max(minSize ?? getMinSize(), 1);
			//     if (pane.getSize() < m) pane.resize(m);
			//   }
			// } catch {
			//   // ignore
			// }
		}, 0);
	};

	const persistSize = (size: number, minSize?: number) => {
		const m = Math.max(minSize ?? getMinSize(), 1);
		try {
			if (size < m) {
				localStorage.setItem(storageKey, '0');
			} else {
				localStorage.setItem(storageKey, String(size));
			}
		} catch {
			// ignore storage errors
		}
	};

	const isOpening = () => opening;

	return { openPane, clamp, scheduleClamp, persistSize, isOpening };
}
