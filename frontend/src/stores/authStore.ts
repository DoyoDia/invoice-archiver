import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
  getAuthToken,
  setAuthToken,
  presetTokens,
  getStoredRole,
  setStoredRole,
  clearStoredRole,
  UserRole
} from "../utils/authToken";

export const roleLabelMap: Record<UserRole, string> = {
  viewer: "查看者",
  uploader: "上传者",
  admin: "管理员"
};

const findRoleByToken = (token: string): UserRole | null => {
  const entry = Object.entries(presetTokens).find(([, value]) => value === token);
  return entry ? (entry[0] as UserRole) : null;
};

export const useAuthStore = defineStore("auth", () => {
  const role = ref<UserRole>("admin");
  const token = ref<string>(presetTokens.admin);
  const isCustomToken = ref(false);

  const authToken = computed(() => token.value);

  const initialize = () => {
    const storedToken = getAuthToken();
    const storedRole = getStoredRole();

    if (storedToken) {
      token.value = storedToken;
      const matchedRole = findRoleByToken(storedToken);
      if (matchedRole) {
        role.value = matchedRole;
        isCustomToken.value = false;
        setStoredRole(matchedRole);
      } else {
        isCustomToken.value = true;
        if (storedRole) {
          role.value = storedRole;
        }
      }
    } else {
      setRole(role.value);
    }
  };

  const setRole = (nextRole: UserRole) => {
    role.value = nextRole;
    token.value = presetTokens[nextRole];
    isCustomToken.value = false;
    setAuthToken(token.value);
    setStoredRole(nextRole);
  };

  const setCustomToken = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    token.value = trimmed;
    const matchedRole = findRoleByToken(trimmed);
    if (matchedRole) {
      role.value = matchedRole;
      isCustomToken.value = false;
      setStoredRole(matchedRole);
    } else {
      isCustomToken.value = true;
      clearStoredRole();
    }
    setAuthToken(trimmed);
  };

  const resetToPreset = () => {
    setRole(role.value);
  };

  const roleOptions = computed(() =>
    (Object.keys(presetTokens) as UserRole[]).map((key) => ({
      label: roleLabelMap[key],
      value: key
    }))
  );

  return {
    role,
    authToken,
    isCustomToken,
    roleOptions,
    initialize,
    setRole,
    setCustomToken,
    resetToPreset
  };
});

