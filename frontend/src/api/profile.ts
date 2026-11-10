import { http } from "./http";
import type { UserProfile } from "../types";

export async function getProfile(): Promise<UserProfile> {
  const { data } = await http.get<UserProfile>("/profile");
  return data;
}

export async function updateProfile(
  patch: Partial<UserProfile>,
): Promise<UserProfile> {
  const { data } = await http.patch<UserProfile>(
    "/profile",
    patch,
  );
  return data;
}
