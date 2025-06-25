import type { Model } from '$lib/stores';

export const PRIVATE_AI_MODEL_PREFIX = 'pipeline-'

/**
 * Determines if the provided model is a private AI model.
 *
 * @param {Model} model - The model object to check.
 */
export function isPrivateAiModel(model: Model) {
	if(model?.id) {
		// NOTE: It might be worth finding a better way to identify a private model!
		return model.id.startsWith(PRIVATE_AI_MODEL_PREFIX);
	}
	return false;
}
