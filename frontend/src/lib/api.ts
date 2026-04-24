"use client";

import axios, { type AxiosInstance } from "axios";
import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

/**
 * Returns an axios client with Clerk's session JWT injected on every request.
 *
 * Rewrite rule in `next.config.ts` maps `/api/proxy/*` → `FIXDOC_API_URL/*`,
 * so the browser always talks to the Next.js server (same-origin) and the
 * backend URL stays server-side — no CORS, no leaking prod URLs into JS.
 */
export function useApi(): AxiosInstance {
  const { getToken } = useAuth();

  return useMemo(() => {
    const client = axios.create({
      baseURL: "/api/proxy/api/v1",
      timeout: 30_000,
    });

    client.interceptors.request.use(async (config) => {
      const token = await getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    client.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err?.response?.status === 401) {
          // Clerk will handle re-auth via middleware; no-op here
        }
        return Promise.reject(err);
      },
    );

    return client;
  }, [getToken]);
}
