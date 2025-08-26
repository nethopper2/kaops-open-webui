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
		
		options.headers ??= new Headers();
		options.headers.set('Authorization', `Bearer ${localStorage.getItem('token')}`);
	}
});
