import { DATA_API_BASE_URL } from '$lib/constants';

// Types based on the Python API models
export interface DataSourceResponse {
	id: string;
	user_id: string;
	name: string;
	context: string;
	sync_status: string;
	last_sync: number | null;
	icon: string;
	action: string;
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
	action: string
): Promise<SlackAuthResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/${action}/initialize`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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

export const manualDataSync = async (token: string, action: string): Promise<SlackSyncResponse> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/${action}/sync`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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

export const disconnectDataSync = async (
	token: string,
	action: string
): Promise<{ message: string; user_id: string; status: string }> => {
	let error = null;

	const res = await fetch(`${DATA_API_BASE_URL}/${action}/disconnect`, {
		method: 'DELETE',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
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
