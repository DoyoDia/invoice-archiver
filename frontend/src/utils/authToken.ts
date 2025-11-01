const TOKEN_STORAGE_KEY = "demo-auth-token";
const ROLE_STORAGE_KEY = "demo-auth-role";

export const presetTokens = {
  viewer: "viewer-token",
  uploader: "uploader-token",
  admin: "admin-token"
} as const;

export type UserRole = keyof typeof presetTokens;

const isBrowser = typeof window !== "undefined" && typeof window.localStorage !== "undefined";

export const getStoredRole = (): UserRole | null => {
  if (!isBrowser) return null;
  const value = window.localStorage.getItem(ROLE_STORAGE_KEY);
  if (value && value in presetTokens) {
    return value as UserRole;
  }
  return null;
};

export const setStoredRole = (role: UserRole) => {
  if (!isBrowser) return;
  window.localStorage.setItem(ROLE_STORAGE_KEY, role);
};

export const clearStoredRole = () => {
  if (!isBrowser) return;
  window.localStorage.removeItem(ROLE_STORAGE_KEY);
};

export const getAuthToken = (): string => {
  if (!isBrowser) return "";
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
};

export const setAuthToken = (token: string) => {
  if (!isBrowser) return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
};

export const clearAuthToken = () => {
  if (!isBrowser) return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
};
