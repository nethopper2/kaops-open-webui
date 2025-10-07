import { ofetch } from 'ofetch';
import { getBackendConfig } from '$lib/apis';

// Types for the new metadata API
export interface MetadataResponse {
	exists: boolean;
	metadata: {
		name: string;
		contentType: string;
		size: number;
		createdAt: string;
		updatedAt: string;
		etag: string;
		metadata: {
			tags?: string;
			context?: string;
			[key: string]: string | undefined;
		};
	};
}

export interface MetadataUpdateRequest {
	metadata: {
		tags?: string;
		context?: string;
		[key: string]: string | undefined;
	};
	merge?: boolean;
}

export interface MetadataUpdateResponse {
	filePath: string;
	metadata: {
		tags?: string;
		context?: string;
		existing?: string;
		[key: string]: string | undefined;
	};
}

export interface BatchMetadataRequest {
	files: string[];
}

export interface BatchMetadataResponse {
	results: Array<{
		filePath: string;
		metadata: {
			tags?: string;
			context?: string;
			[key: string]: string | undefined;
		} | null;
		error: string | null;
	}>;
}

// Validation utilities
export class MetadataValidator {
	private static readonly KEY_PATTERN = /^[a-z0-9._-]{1,40}$/;
	private static readonly MAX_VALUE_LENGTH = 512;
	private static readonly MAX_PAYLOAD_SIZE = 2048;

	static validateKey(key: string): { valid: boolean; error?: string } {
		if (!key) {
			return { valid: false, error: 'Metadata key cannot be empty' };
		}
		if (!this.KEY_PATTERN.test(key)) {
			return { 
				valid: false, 
				error: 'Metadata key must be lowercase alphanumeric with ._- only, max 40 characters' 
			};
		}
		return { valid: true };
	}

	static validateValue(value: string): { valid: boolean; error?: string } {
		if (value.length > this.MAX_VALUE_LENGTH) {
			return { 
				valid: false, 
				error: `Metadata value cannot exceed ${this.MAX_VALUE_LENGTH} characters` 
			};
		}
		return { valid: true };
	}

	static validatePayload(payload: Record<string, string>): { valid: boolean; error?: string } {
		const payloadStr = JSON.stringify(payload);
		if (payloadStr.length > this.MAX_PAYLOAD_SIZE) {
			return { 
				valid: false, 
				error: `Total payload cannot exceed ${this.MAX_PAYLOAD_SIZE} bytes` 
			};
		}
		return { valid: true };
	}

	static validateMetadata(metadata: Record<string, string>): { valid: boolean; errors: string[] } {
		const errors: string[] = [];
		
		for (const [key, value] of Object.entries(metadata)) {
			const keyValidation = this.validateKey(key);
			if (!keyValidation.valid) {
				errors.push(`Key "${key}": ${keyValidation.error}`);
			}
			
			const valueValidation = this.validateValue(value);
			if (!valueValidation.valid) {
				errors.push(`Value for "${key}": ${valueValidation.error}`);
			}
		}
		
		const payloadValidation = this.validatePayload(metadata);
		if (!payloadValidation.valid) {
			errors.push(payloadValidation.error!);
		}
		
		return { valid: errors.length === 0, errors };
	}
}

// Error handling utilities
interface ErrorWithStatus {
	status: number;
	data?: unknown;
	message?: string;
}

export class MetadataError extends Error {
	constructor(
		message: string,
		public statusCode?: number,
		public response?: unknown
	) {
		super(message);
		this.name = 'MetadataError';
	}
}

export function handleMetadataError(error: unknown): MetadataError {
	if (error && typeof error === 'object' && 'status' in error) {
		const errorWithStatus = error as ErrorWithStatus;
		const statusCode = errorWithStatus.status;
		let message = 'An error occurred';
		
		switch (statusCode) {
			case 400:
				message = 'Invalid request data. Please check your input.';
				break;
			case 403:
				message = 'Access denied. You do not have permission to perform this action.';
				break;
			case 404:
				message = 'File or metadata not found.';
				break;
			case 413:
				message = 'Request payload too large. Please reduce the amount of data.';
				break;
			case 500:
				message = 'Internal server error. Please try again later.';
				break;
			default:
				message = `Request failed with status ${statusCode}`;
		}
		
		return new MetadataError(message, statusCode, errorWithStatus.data);
	}
	
	const errorMessage = error && typeof error === 'object' && 'message' in error 
		? (error as { message: string }).message 
		: 'An unexpected error occurred';
	
	return new MetadataError(errorMessage);
}

// Create metadata API client
const createMetadataClient = () => {
	return ofetch.create({
		async onRequest({ options }) {
			const backendConfig = await getBackendConfig();
			
			// Set base URL for metadata API
			// nh_data_service_url already includes /api/v1, so we don't need to add it again
			options.baseURL = backendConfig.private_ai.nh_data_service_url;
			
			// Add authorization header
			const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
			if (token) {
				options.headers = new Headers({
					...options.headers,
					'Authorization': `Bearer ${token}`,
					'Content-Type': 'application/json'
				});
			}
		},
		
		async onResponseError({ response }) {
			// Let the error bubble up to be handled by the calling code
			throw response._data || response;
		}
	});
};

const metadataClient = createMetadataClient();

// API functions
export const metadataApi = {
	/**
	 * Get metadata for a specific file
	 */
	async getMetadata(filePath: string, debugRaw = false): Promise<MetadataResponse> {
		try {
			const response = await metadataClient<MetadataResponse>(`/files/${encodeURIComponent(filePath)}/metadata`, {
				method: 'GET',
				query: debugRaw ? { debugRaw: 'true' } : undefined
			});
			return response;
		} catch (error) {
			throw handleMetadataError(error);
		}
	},

	/**
	 * Update metadata for a specific file
	 */
	async updateMetadata(
		filePath: string, 
		metadata: Record<string, string>, 
		merge = true
	): Promise<MetadataUpdateResponse> {
		// Validate metadata before sending
		const validation = MetadataValidator.validateMetadata(metadata);
		if (!validation.valid) {
			throw new MetadataError(`Validation failed: ${validation.errors.join(', ')}`, 400);
		}

		try {
			const requestBody: MetadataUpdateRequest = {
				metadata,
				merge
			};

			const response = await metadataClient<MetadataUpdateResponse>(`/files/${encodeURIComponent(filePath)}/metadata`, {
				method: 'PUT',
				body: requestBody
			});
			return response;
		} catch (error) {
			throw handleMetadataError(error);
		}
	},

	/**
	 * Get metadata for multiple files in batch
	 */
	async getBatchMetadata(filePaths: string[]): Promise<BatchMetadataResponse> {
		if (!filePaths.length) {
			throw new MetadataError('File paths array cannot be empty', 400);
		}

		try {
			const requestBody: BatchMetadataRequest = {
				files: filePaths
			};

			const response = await metadataClient<BatchMetadataResponse>('/files/batch/metadata', {
				method: 'POST',
				body: requestBody
			});
			return response;
		} catch (error) {
			throw handleMetadataError(error);
		}
	},

	/**
	 * Delete metadata for a specific file (if supported by the API)
	 * Note: This might need to be implemented as a PUT with empty metadata
	 */
	async deleteMetadata(filePath: string): Promise<void> {
		try {
			// If the API supports DELETE, use it; otherwise use PUT with empty metadata
			await metadataClient(`/files/${encodeURIComponent(filePath)}/metadata`, {
				method: 'DELETE'
			});
		} catch (error) {
			// If DELETE is not supported, try PUT with empty metadata
			if (error && typeof error === 'object' && 'status' in error && (error as ErrorWithStatus).status === 405) {
				await this.updateMetadata(filePath, {}, false);
			} else {
				throw handleMetadataError(error);
			}
		}
	}
};
