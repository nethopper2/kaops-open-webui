import { ofetch, type FetchContext } from 'ofetch';
import { getBackendConfig } from '$lib/apis';

function ensureHeaders(options: FetchContext['options']): Headers {
	const current = options.headers;
	if (current instanceof Headers) {
		return current;
	}
	const h = new Headers(current as HeadersInit | undefined);
	options.headers = h;
	return h;
}

export const apiFetch = ofetch.create({
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	async onRequest({ request, options }) {
		const backendConfig = await getBackendConfig();

		options.baseURL = backendConfig.private_ai.nh_data_service_url;

		// Build a full URL for origin/path checks where possible (SSR-safe: avoid window usage)
		let fullUrl: URL | null = null;
		try {
			const reqUrlStr = typeof request === 'string' ? request : (request as Request).url;
			if (/^(https?:)?\/\//i.test(String(reqUrlStr))) {
				const u = String(reqUrlStr);
				// If protocol-relative (//host/...), prepend https: to make a valid absolute URL for parsing.
				const absolute = u.startsWith('http') ? u : `https:${u}`;
				fullUrl = new URL(absolute);
			} else {
				// Resolve relative url against the configured baseURL if present; avoid window in SSR.
				const base = options.baseURL ?? 'http://localhost';
				fullUrl = new URL(String(reqUrlStr ?? ''), base);
			}
		} catch (e) {
			// If URL parsing fails, leave fullUrl null and avoid adding sensitive headers
			fullUrl = null;
		}

		const headers = ensureHeaders(options);

		// Attach Authorization header ONLY when the target matches the configured backend service origin/path.
		const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
		if (token && fullUrl) {
			try {
				const serviceBase = new URL(backendConfig.private_ai.nh_data_service_url);
				const allowedOrigin = serviceBase.origin;

				// Relax path check: attach auth for any request to the same origin as the configured backend.
				// This avoids missing Authorization when callers pass absolute paths (e.g., "/v1/..."),
				// which reset the path and bypass the previous base-path check.
				if (fullUrl.origin === allowedOrigin) {
					if (!headers.has('Authorization')) {
						headers.set('Authorization', `Bearer ${token}`);
					}
				}
			} catch {
				// If anything goes wrong parsing config URLs, do not attach authorization
			}
		}

		// Set the Accept header if not provided (safe default)
		if (!headers.has('Accept')) {
			headers.set('Accept', 'application/json');
		}

		// Set Content-Type only when there is a non-FormData body and the method implies a body.
		try {
			const method = (options.method ?? 'GET').toString().toUpperCase();
			const hasBodyMethod = method !== 'GET' && method !== 'HEAD';

			if (
				hasBodyMethod &&
				options.body != null &&
				!headers.has('Content-Type') &&
				!(options.body instanceof FormData)
			) {
				// If body is an object (likely intended to be JSON), stringify and set header
				if (typeof options.body === 'object') {
					headers.set('Content-Type', 'application/json');
					// ofetch sometimes expects raw body; if it's an object, stringify it
					try {
						options.body = JSON.stringify(options.body as unknown as Record<string, unknown>);
					} catch {
						// If stringify fails, leave the body as-is
					}
				}
			}
		} catch {
			// Silently ignore header adjustments on error to avoid breaking requests
		}
	}
});
