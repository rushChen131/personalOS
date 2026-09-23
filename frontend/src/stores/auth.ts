"use client";

import { create } from "zustand";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  status: "idle" | "loading" | "authenticated" | "anonymous";
  error: string | null;
  login: (email: string, password: string) => Promise<boolean>;
  restore: () => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "idle",
  error: null,

  async login(email, password) {
    set({ status: "loading", error: null });
    try {
      const result = await api.login(email, password);
      setToken(result.access_token);
      set({ user: result.user, status: "authenticated", error: null });
      return true;
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Login failed";
      set({ status: "anonymous", error: message });
      return false;
    }
  },

  async restore() {
    if (!getToken()) {
      set({ status: "anonymous", user: null });
      return;
    }
    set({ status: "loading" });
    try {
      const user = await api.me();
      set({ user, status: "authenticated" });
    } catch {
      setToken(null);
      set({ user: null, status: "anonymous" });
    }
  },

  logout() {
    setToken(null);
    set({ user: null, status: "anonymous" });
  },
}));
