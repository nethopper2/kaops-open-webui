import type { Model } from '$lib/stores';
import { PRIVATE_AI_MODEL_PREFIX } from '$lib/shared/private_ai';

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
