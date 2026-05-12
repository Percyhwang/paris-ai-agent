import { apiRequest } from "./apiClient";
import type { User, UserPreferences } from "../types";

type UserUpdatePayload = {
  name?: string;
  profile_image?: string | null;
  preferences?: UserPreferences;
};

export const userService = {
  updateMe(payload: UserUpdatePayload): Promise<User> {
    return apiRequest<User>("/users/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};
