import { toast } from 'svelte-sonner';

interface UserPermissions {
    chat?: {
        file_upload?: boolean;
    };
}

interface User {
    role?: string;
    permissions?: UserPermissions;
}

interface Model {
    id: string;
    info?: {
        meta?: {
            capabilities?: {
                file_upload?: boolean;
            };
        };
    };
}

/**
 * Check if a user has permission to upload files (user permissions only)
 * @param user - The user object to check permissions for
 * @returns boolean - true if user can upload files, false otherwise
 */
export function canUploadFiles(user: User | null | undefined): boolean {
    return user?.role === 'admin' || (user?.permissions?.chat?.file_upload ?? true);
}

/**
 * Check if selected models support file uploads
 * @param selectedModels - Array of selected model IDs
 * @param allModels - Array of all available models
 * @returns boolean - true if all selected models support file uploads, false otherwise
 */
export function canModelsUploadFiles(selectedModels: string[], allModels: Model[]): boolean {
    return selectedModels.every((modelId) => {
        const model = allModels.find((m) => m.id === modelId);
        return model?.info?.meta?.capabilities?.file_upload ?? true;
    });
}

/**
 * Check file upload permissions (user + model capabilities) and show error message if denied
 * @param user - The user object to check permissions for
 * @param selectedModels - Array of selected model IDs
 * @param allModels - Array of all available models
 * @param i18n - The i18n store for translations
 * @returns boolean - true if user can upload files and models support it, false otherwise
 */
export function checkFileUploadPermission(
    user: User | null | undefined, 
    selectedModels: string[], 
    allModels: Model[], 
    i18n: { t: (key: string) => string }
): boolean {
    // Check user permissions first
    if (!canUploadFiles(user)) {
        toast.error(i18n.t('You do not have permission to upload files.'));
        return false;
    }
    
    // Check model capabilities (applies to all users, including admins)
    if (!canModelsUploadFiles(selectedModels, allModels)) {
        toast.error(i18n.t('Selected model(s) do not support file upload'));
        return false;
    }
    
    return true;
} 