import { describe, it, expect, vi, beforeEach } from 'vitest';
import { metadataApi, MetadataValidator, MetadataError } from '../metadata';

// Mock the dependencies
vi.mock('$lib/apis', () => ({
	getBackendConfig: vi.fn().mockResolvedValue({
		private_ai: {
			nh_data_service_url: 'http://localhost:8000'
		}
	})
}));

vi.mock('ofetch', () => ({
	ofetch: {
		create: vi.fn(() => vi.fn())
	}
}));

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
	value: {
		getItem: vi.fn(() => 'mock-token'),
		setItem: vi.fn(),
		removeItem: vi.fn()
	}
});

describe('MetadataValidator', () => {
	describe('validateKey', () => {
		it('should accept valid keys', () => {
			expect(MetadataValidator.validateKey('valid_key')).toEqual({ valid: true });
			expect(MetadataValidator.validateKey('valid-key')).toEqual({ valid: true });
			expect(MetadataValidator.validateKey('valid.key')).toEqual({ valid: true });
			expect(MetadataValidator.validateKey('valid123')).toEqual({ valid: true });
			expect(MetadataValidator.validateKey('a')).toEqual({ valid: true });
			expect(MetadataValidator.validateKey('a'.repeat(40))).toEqual({ valid: true });
		});

		it('should reject invalid keys', () => {
			expect(MetadataValidator.validateKey('')).toEqual({
				valid: false,
				error: 'Metadata key cannot be empty'
			});
			expect(MetadataValidator.validateKey('Invalid_Key')).toEqual({
				valid: false,
				error: 'Metadata key must be lowercase alphanumeric with ._- only, max 40 characters'
			});
			expect(MetadataValidator.validateKey('key with spaces')).toEqual({
				valid: false,
				error: 'Metadata key must be lowercase alphanumeric with ._- only, max 40 characters'
			});
			expect(MetadataValidator.validateKey('a'.repeat(41))).toEqual({
				valid: false,
				error: 'Metadata key must be lowercase alphanumeric with ._- only, max 40 characters'
			});
		});
	});

	describe('validateValue', () => {
		it('should accept valid values', () => {
			expect(MetadataValidator.validateValue('valid value')).toEqual({ valid: true });
			expect(MetadataValidator.validateValue('a'.repeat(512))).toEqual({ valid: true });
		});

		it('should reject values that are too long', () => {
			expect(MetadataValidator.validateValue('a'.repeat(513))).toEqual({
				valid: false,
				error: 'Metadata value cannot exceed 512 characters'
			});
		});
	});

	describe('validatePayload', () => {
		it('should accept valid payloads', () => {
			const smallPayload = { key1: 'value1', key2: 'value2' };
			expect(MetadataValidator.validatePayload(smallPayload)).toEqual({ valid: true });
		});

		it('should reject payloads that are too large', () => {
			const largePayload = { key: 'a'.repeat(2049) };
			expect(MetadataValidator.validatePayload(largePayload)).toEqual({
				valid: false,
				error: 'Total payload cannot exceed 2048 bytes'
			});
		});
	});

	describe('validateMetadata', () => {
		it('should validate all metadata fields', () => {
			const validMetadata = {
				tags: 'alpha,beta',
				context: 'test context'
			};
			expect(MetadataValidator.validateMetadata(validMetadata)).toEqual({
				valid: true,
				errors: []
			});
		});

		it('should collect all validation errors', () => {
			const invalidMetadata = {
				'Invalid Key': 'value',
				'valid_key': 'a'.repeat(513)
			};
			const result = MetadataValidator.validateMetadata(invalidMetadata);
			expect(result.valid).toBe(false);
			expect(result.errors).toHaveLength(2);
			expect(result.errors[0]).toContain('Invalid Key');
			expect(result.errors[1]).toContain('valid_key');
		});
	});
});

describe('MetadataError', () => {
	it('should create error with message and status code', () => {
		const error = new MetadataError('Test error', 400, { detail: 'test' });
		expect(error.message).toBe('Test error');
		expect(error.statusCode).toBe(400);
		expect(error.response).toEqual({ detail: 'test' });
		expect(error.name).toBe('MetadataError');
	});
});

describe('metadataApi', () => {
	// Note: These tests would require more complex mocking of the ofetch client
	// For now, we'll focus on the validation and error handling logic
	
	it('should be defined', () => {
		expect(metadataApi).toBeDefined();
		expect(metadataApi.getMetadata).toBeDefined();
		expect(metadataApi.updateMetadata).toBeDefined();
		expect(metadataApi.getBatchMetadata).toBeDefined();
		expect(metadataApi.deleteMetadata).toBeDefined();
	});
});
