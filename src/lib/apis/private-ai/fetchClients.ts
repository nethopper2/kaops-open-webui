import { ofetch } from 'ofetch';
import { getBackendConfig } from '$lib/apis';

export const apiFetch = ofetch.create({
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	async onRequest({ request, options }) {
		const backendConfig = await getBackendConfig();
		options.baseURL = `${backendConfig.private_ai.rest_api_base_url}/api`,
		options.headers ??= new Headers();
		options.headers.set('Authorization', `Bearer ${localStorage.getItem('token')}`);
		console.log('apiFetch request:', request, options);
	}
});
