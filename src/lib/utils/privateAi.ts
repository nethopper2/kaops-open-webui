import type { Model } from '$lib/stores';
import { PRIVATE_AI_MODEL_PREFIX } from '$lib/shared/privateAi';
import { apiFetch } from '$lib/apis/private-ai/fetchClients';
import { toast } from 'svelte-sonner';

/**
 * Download or open a proxied resource served by the private-ai nh_data_service_url.
 *
 * Parameters:
 * - target: string or URL pointing to the proxy-download endpoint (e.g. https://svc/files/.../proxy-download)
 * - backendConfig: optional backend config object used to validate service origin/path (same shape as getBackendConfig())
 * - opts.bypassAllowlist: if true, skip allowlist/origin/path checks (caller must ensure safety)
 *
 * The function will attempt to open PDFs in a new tab and otherwise trigger a secure download.
 * It shows simple toast notifications for success/failure.
 */
export async function downloadProxyResource(
	target: string | URL,
	backendConfig?: any,
	opts: { bypassAllowlist?: boolean } = {}
): Promise<void> {
	const bypass = !!opts.bypassAllowlist;

	let targetUrl: URL;
	try {
		targetUrl = typeof target === 'string' ? new URL(target, window.location.href) : target;
	} catch (err) {
		console.warn('Invalid target URL for downloadProxyResource', err);
		toast.error('Invalid download URL');
		return;
	}

	// Allowlist/origin/path validation is controlled explicitly by the bypass flag:
	// - If bypassAllowlist is true, skip validation (caller assumes trust).
	// - Otherwise require backendConfig.private_ai.nh_data_service_url and validate origin/path.
	if (!bypass) {
		if (!backendConfig || !backendConfig.private_ai || !backendConfig.private_ai.nh_data_service_url) {
			console.warn('Missing private_ai.nh_data_service_url in backend config', backendConfig);
			toast.error('Configuration issue: cannot open linked resource.');
			return;
		}

		let serviceBase: URL;
		try {
			serviceBase = new URL(backendConfig.private_ai.nh_data_service_url);
		} catch (err) {
			console.warn('Invalid backend private_ai.nh_data_service_url in config', err, backendConfig);
			toast.error('Configuration issue: invalid service URL.');
			return;
		}

		// Allowlist for common development hostnames
		const devHostnames = new Set<String>([]);

		if (import.meta.env.DEV === true) {
  		devHostnames.add('localhost');
  		devHostnames.add('127.0.0.1');
  		devHostnames.add('0.0.0.0');
		}

		const pageIsLocal = devHostnames.has(window.location.hostname);
		const targetIsLocal = devHostnames.has(targetUrl.hostname);
		const serviceIsLocal = devHostnames.has(serviceBase.hostname);

		const originAllowed =
			targetUrl.origin === serviceBase.origin ||
			(pageIsLocal && targetIsLocal) ||
			(serviceIsLocal && targetIsLocal);

		if (!originAllowed) {
			console.warn('Link origin not allowed by policy', {
				target: targetUrl.toString(),
				serviceBase: serviceBase.toString(),
				pageHostname: window.location.hostname
			});
			toast.error('Link refused: origin mismatch for linked resource.');
			return;
		}

		const servicePath = (serviceBase.pathname || '').replace(/\/$/, '');
		if (servicePath) {
			const p = targetUrl.pathname || '';
			// Allow when the target path exactly equals servicePath or is under it (component boundary)
			if (!(p === servicePath || p.startsWith(servicePath + '/'))) {
				console.warn('Link path not under configured service path', {
					targetPath: p,
					servicePath
				});
				toast.error('Link refused.');
				return;
			}
		}
	} // end if !bypass

	// Fetch resource via apiFetch.raw()
	let resp: Response | null = null;
	try {
		resp = await apiFetch.raw(targetUrl.toString());
	} catch (err) {
		console.error('apiFetch.raw failed for downloadProxyResource', err);
		toast.error('Failed to retrieve resource');
		return;
	}

	try {
		if (!resp || !resp.ok) {
			console.warn('Non-OK response from proxy download', resp);
			toast.error('Resource unavailable');
			return;
		}

		// Robustly obtain a Blob from the response. ofetch sometimes exposes parsed data
		// on resp._data (which can be a Blob, ArrayBuffer, Uint8Array, string, or parsed JSON object).
		let blob: Blob | null = null;

		// @ts-ignore - ofetch specific property
		const maybeData = resp && (resp as any)._data;

		if (maybeData) {
			// If it's already a Blob, use it.
			if (maybeData instanceof Blob) {
				blob = maybeData as Blob;
			} else if (maybeData instanceof ArrayBuffer) {
				blob = new Blob([maybeData]);
			} else if (maybeData instanceof Uint8Array) {
				blob = new Blob([maybeData.buffer]);
			} else if (typeof maybeData === 'string') {
				// If ofetch returned a string, create a blob (best-effort).
				blob = new Blob([maybeData]);
			} else if (typeof maybeData === 'object') {
				// Handle parsed JSON objects from ofetch by stringifying to a JSON Blob
				try {
					blob = new Blob([JSON.stringify(maybeData)], { type: 'application/json' });
				} catch {
					// ignore and try other fallbacks
				}
			} else {
				// Unknown _data shape: try to coerce with ArrayBuffer if available
				try {
					const ab = await (maybeData as any).arrayBuffer?.();
					if (ab) blob = new Blob([ab]);
				} catch {
					// ignore
				}
			}
		}

		// If we still don't have a usable blob, try reading directly from the response
		if (!(blob instanceof Blob) || blob.size === 0) {
			try {
				const b = await resp.blob();
				if (b && b.size > 0) {
					blob = b;
				}
			} catch {
				// ignore
			}
		}

		if (!(blob instanceof Blob) || blob.size === 0) {
			console.warn('Invalid or empty Blob returned for download', resp);
			toast.error('Resource unavailable');
			return;
		}

		// Try to derive filename from response.url or the target URL.
		let filename = 'download';
		try {
			const responseUrl = typeof (resp as any).url === 'string' && (resp as any).url ? (resp as any).url : targetUrl.toString();
			const u = new URL(responseUrl, window.location.href);
			const pathname = u.pathname || '';
			const proxySuffix = '/proxy-download';

			let candidate = '';
			if (pathname.endsWith(proxySuffix)) {
				const filePath = pathname.slice(0, -proxySuffix.length);
				candidate = filePath.split('/').filter(Boolean).pop() ?? '';
			} else {
				candidate = pathname.split('/').filter(Boolean).pop() ?? '';
			}

			if (candidate) {
				try {
					filename = decodeURIComponent(candidate);
				} catch {
					filename = String(candidate);
				}
				filename = filename.replace(/[^a-zA-Z0-9.\-_]/g, '_');
			}
		} catch (e) {
			filename = 'download';
		}

		if (filename.length > 200) {
			const extMatch = filename.match(/(\.[a-zA-Z0-9]{1,8})$/);
			const ext = extMatch ? extMatch[1] : '';
			const namePart = filename.slice(0, 200 - ext.length);
			filename = `${namePart}${ext}`;
		}

		const objectUrl = URL.createObjectURL(blob);

		// Decide whether the resource is safe/viewable to open in a browser tab.
		const viewableMimePrefixes = ['image/', 'text/', 'video/', 'audio/'];
		const viewableMimeExact = new Set([
			'application/pdf',
			'application/json',
			'image/svg+xml',
			'text/html'
		]);

		const filenameExt = ((): string => {
			const m = filename.match(/\.([a-zA-Z0-9]{1,8})$/);
			return m ? m[1].toLowerCase() : '';
		})();

		const viewableExts = new Set(['svg', 'html', 'htm', 'json', 'txt', 'csv']);

		const isViewableByMime =
			typeof blob.type === 'string' &&
			(blob.type !== '' &&
				(viewableMimePrefixes.some((p) => blob.type.startsWith(p)) || viewableMimeExact.has(blob.type)));

		const isViewableByExt = filenameExt && viewableExts.has(filenameExt);

		const isViewable = isViewableByMime || isViewableByExt;

		let opened = false;
		if (isViewable) {
			// Most browsers allow opening an object URL in a new tab from a click handler.
			const w = window.open(objectUrl, '_blank', 'noopener,noreferrer');
			opened = !!w;
		}

		if (!opened) {
			// Fallback to downloading or opening in a new tab when open() is blocked.
			const a = document.createElement('a');
			a.href = objectUrl;
			// If the resource is viewable, force the anchor to open in a new tab as a fallback.
			if (isViewable) {
				a.target = '_blank';
			} else {
				// Non-viewable resources should trigger a download
				a.download = filename;
			}
			a.rel = 'noopener noreferrer';
			document.body.appendChild(a);
			a.click();
			a.remove();
		}

		// Revoke after a minute to give browser time to load/use it
		setTimeout(() => {
			try {
				URL.revokeObjectURL(objectUrl);
			} catch (e) {
				// ignore
			}
		}, 60000);

		toast.success(isViewable ? 'Opened in a new tab' : 'Download started');
	} catch (err) {
		console.error('Failed to process downloaded Blob', err);
		toast.error('Failed to download resource');
	}
}
// Type guard to safely detect a 'pipeline' property without indexing errors
function hasPipeline(obj: unknown): obj is { pipeline: unknown } {
	return typeof obj === 'object' && obj !== null && 'pipeline' in obj;
}

/**
 * Determines if the provided model is a private AI model.
 *
 * @param {Model} model - The model object to check.
 */
export function isPrivateAiModel(model: Model) {
	// Consider Ollama models as private AI models since they run in the user's cluster.
	if (model?.owned_by === 'ollama') {
		return true;
	}

	const isPipeline = hasPipeline(model);

	// Check for pipeline models with a specific prefix.
	if (isPipeline && model?.id) {
		// Can be indicated as a private AI model in the following ways:
		// 1. Starts with the private-ai prefix.
		//    This is either directly in the id or a `Prefix ID` can be defined in the
		//    connection settings within Open Webui.
		return model.id.startsWith(PRIVATE_AI_MODEL_PREFIX);
	}
	return false;
}
