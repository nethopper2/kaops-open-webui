import { ofetch } from 'ofetch';
import { getBackendConfig } from '$lib/apis';

export const apiFetch = ofetch.create({
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	async onRequest({ request, options }) {
		const backendConfig = await getBackendConfig();
		
		// Check if we should use the new nh-pai-data-service
		const useNewService = localStorage.getItem('use_nh_data_service') === 'true';
		
		if (useNewService) {
			// Use nh-pai-data-service
			options.baseURL = `${backendConfig.nh_data_service.url}/api/v1`;
			
			// Transform DevExtreme FileManager requests
			if (options.url === '/storage/file-manager') {
				// Transform: /storage/file-manager → /files/devextreme
				options.url = '/files/devextreme';
				
				// Transform query parameters for folder navigation
				if (options.query?.path) {
					// Convert 'path' parameter to 'prefix' parameter
					options.query.prefix = options.query.path;
					delete options.query.path;
				}
			}
		} else {
			// Use original private-ai-rest service
			options.baseURL = `${backendConfig.private_ai.rest_api_base_url}/api`;
		}
		
		// Build a full URL for origin/path checks where possible
		let fullUrl: URL | null = null;
		try {
			// If options.url is absolute, use it; otherwise resolve against options.baseURL or current origin
			if (options?.url && /^(https?:)?\/\//i.test(String(options.url))) {
				const u = String(options.url);
				fullUrl = new URL(u.startsWith('http') ? u : `${window.location.protocol}${u}`);
			} else {
				const base = options.baseURL ?? window.location.origin;
				fullUrl = new URL(String(options.url ?? ''), base);
			}
		} catch (e) {
			// If URL parsing fails, leave fullUrl null and avoid adding sensitive headers
			fullUrl = null;
		}

		options.headers ??= new Headers();

		// Attach Authorization header ONLY when the target matches the configured backend service origin/path.
		const token = localStorage.getItem('token');
		if (token && fullUrl) {
			try {
				const serviceBase = new URL(useNewService ? backendConfig.nh_data_service.url : backendConfig.private_ai.rest_api_base_url);
				const allowedOrigin = serviceBase.origin;
				const allowedPath = (serviceBase.pathname || '').replace(/\/$/, ''); // normalize

				// Require same origin and that the target path starts with the configured base path (if any)
				if (
					fullUrl.origin === allowedOrigin &&
					(allowedPath === '' || fullUrl.pathname.startsWith(allowedPath))
				) {
					if (!options.headers.has('Authorization')) {
						options.headers.set('Authorization', `Bearer ${token}`);
					}
				}
			} catch {
				// If anything goes wrong parsing config URLs, do not attach authorization
			}
		}

		// Set Accept header if not provided (safe default)
		if (!options.headers.has('Accept')) {
			options.headers.set('Accept', 'application/json');
		}

		// Set Content-Type only when there is a non-FormData body and the method implies a body.
		try {
			const method = (options.method ?? 'GET').toString().toUpperCase();
			const hasBodyMethod = method !== 'GET' && method !== 'HEAD';

			if (
				hasBodyMethod &&
				options.body != null &&
				!options.headers.has('Content-Type') &&
				!(options.body instanceof FormData)
			) {
				// If body is an object (likely intended to be JSON), stringify and set header
				if (typeof options.body === 'object') {
					options.headers.set('Content-Type', 'application/json');
					// ofetch sometimes expects raw body; if it's an object, stringify it
					try {
						options.body = JSON.stringify(options.body);
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
