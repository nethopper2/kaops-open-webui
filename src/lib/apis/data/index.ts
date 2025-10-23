import { DATA_API_BASE_URL } from '$lib/constants';

// Types based on the Python API models
export interface DataSourceResponse {
	id: string;
	user_id: string;
	name: string;
	context: string;
	sync_status: 'synced' | 'syncing' | 'error' | 'unsynced' | 'embedding' | 'deleting' | 'deleted';
	last_sync: string | null;
	icon: string;
	action: string;
	layer?: string;
	created_at: number;
	updated_at: number;
}

export interface DataSourceForm {
	name: string;
	context: string;
	icon?: string;
	action?: string;
}

export interface SyncStatusForm {
	sync_status: string;
	last_sync?: number;
}

export interface SlackAuthResponse {
	url: string;
	user_id: string;
	bot_scopes: string[];
	user_scopes: string[];
}

export interface SlackStatusResponse {
	user_id: string;
	configuration: {
		gcs_bucket_configured: boolean;
		gcs_credentials_configured: boolean;
		slack_client_configured: boolean;
	};
	ready_for_sync: boolean;
}

export interface SlackSyncResponse {
	message: string;
	user_id: string;
	status: string;
	team?: string;
	slack_user?: string;
	token_type?: string;
	bot_token_available?: boolean;
	user_token_available?: boolean;
}

// Data Sources API Functions
export const getDataSources = async (token: string): Promise<DataSourceResponse[]> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/`, {
		method: 'GET',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createDataSource = async (
	token: string,
	payload: DataSourceForm
): Promise<DataSourceResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const initializeDefaultDataSources = async (
	token: string
): Promise<DataSourceResponse[]> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/sources/initialize`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDataSourceById = async (
	token: string,
	id: string
): Promise<DataSourceResponse | null> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/${id}`, {
		method: 'GET',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateDataSource = async (
	token: string,
	id: string,
	payload: DataSourceForm
): Promise<DataSourceResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/${id}/update`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateSyncStatus = async (
	token: string,
	id: string,
	payload: SyncStatusForm
): Promise<DataSourceResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/${id}/sync`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteDataSource = async (
	token: string,
	id: string
): Promise<{ success: boolean; message: string }> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/source/${id}`, {
		method: 'DELETE',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const initializeDataSync = async (
	token: string,
	action: string,
	layer: string
): Promise<SlackAuthResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/${action}/initialize?layer=${layer}`, {
		method: 'GET',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDataSourceStatus = async (token: string): Promise<SlackStatusResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/slack/status`, {
		method: 'GET',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const manualDataSync = async (
	token: string,
	action: string,
	layer: string
): Promise<{ message?: string; url?: string; detail?: { reauth_url?: string } } | null> => {
	let error: any = null;

	const url = `${DATA_API_BASE_URL}/${action}/sync?layer=${layer}`;
	
	const res = await fetch(url, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) {
				// Try to parse JSON error payload and pass it through so callers can handle reauth
				const contentType = res.headers.get('content-type');
				if (contentType && contentType.includes('application/json')) {
					const body = await res.json();
					return body;
				} else {
					// Non-JSON response (e.g., HTML); surface a normalized error
					return { detail: { message: `HTTP ${res.status}: ${res.statusText}` } };
				}
			}
			return res.json();
		})
		.catch((err) => {
			console.log('API Error:', err);
			// If the error already contains a reauth_url, surface it to the caller instead of throwing
			if (err?.reauth_url || err?.detail?.reauth_url) {
				return { detail: { reauth_url: err.reauth_url || err.detail.reauth_url } };
			}
			error = err.detail || err.message || 'Unknown error';
			return null;
		});

	// If we received a payload with a reauth_url, return it directly
	if (res && (res.reauth_url || res?.detail?.reauth_url)) {
		return { detail: { reauth_url: res.reauth_url || res.detail.reauth_url } } as any;
	}

	if (error) {
		throw error;
	}

	return res;
};

export const disconnectDataSync = async (
	token: string,
	action: string,
	layer: string
): Promise<{ message: string; user_id: string; status: string }> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/${action}/disconnect?layer=${layer}`, {
		method: 'DELETE',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			const result = await res.json();
			return result;
		})
		.catch((err) => {
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getJiraProjects = async (token: string) => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/atlassian/projects`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
		error = err.detail;
		console.log(err);
		return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const syncSelectedJiraProjects = async (
	token: string,
	projectKeys: string[],
	layer: string = 'jira'
) => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/atlassian/sync-selected`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			project_keys: projectKeys,
			layer: layer
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
		error = err.detail;
		console.log(err);
		return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const atlassianSelfHostedAuth = async (pat: string, layer: string = 'jira') => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/atlassian/self-hosted/auth`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${localStorage.getItem('token')}`
		},
		body: JSON.stringify({
			pat_token: pat,
			layer: layer
		})
	}).catch((err) => {
		error = err;
		console.error('Network error:', err);
		return null;
	});

	if (error) {
		throw error;
	}

	return res;
};

export const markDataSourceIncomplete = async (token: string, sourceId: string) => {
	const res = await fetch(`${DATA_API_BASE_URL}/source/${sourceId}/incomplete`, {
		method: "POST",
		headers: {
			"Authorization": `Bearer ${token}`,
			"Content-Type": "application/json"
		}
	});

	if (!res.ok) {
		const error = await res.json();
		throw new Error(error.detail || "Failed to mark data source as incomplete");
	}

	return await res.json();
};

export const resetEmbedding = async (token: string, userId: string, dataSource: string) => {
	const res = await fetch(`${DATA_API_BASE_URL}/embedding/reset`, {
		method: "POST",
		headers: {
			"Authorization": `Bearer ${token}`,
			"Content-Type": "application/json"
		},
		body: JSON.stringify({
			userId,
			dataSource
		})
	});

	if (!res.ok) {
		const error = await res.json();
		throw new Error(error.detail || "Failed to reset embedding");
	}

	return await res.json();
};
