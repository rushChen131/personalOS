"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";

/** Restores the session from localStorage once per app load. */
export function useSessionRestore(): void {
  const restore = useAuthStore((state) => state.restore);
  const status = useAuthStore((state) => state.status);

  useEffect(() => {
    if (status === "idle") void restore();
  }, [status, restore]);
}
