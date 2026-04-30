"use client";

import axios, { type AxiosInstance } from "axios";
import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

/**
 * Returns an axios client with Clerk's session JWT injected on every request.
 *
 * Hits the backend directly via `NEXT_PUBLIC_FIXDOC_API_URL`. We don't proxy
 * through a Next.js rewrite because (a) backend↔frontend cross-service
 * traffic on Railway via the public domain runs into Cloudflare hairpin
 * issues, and (b) the backend URL is already a public hostname — there's no
 * security gain in hiding it server-side. CORS is configured on the backend
 * to allow the frontend origin.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_FIXDOC_API_URL || "http://localhost:8000";

export function useApi(): AxiosInstance {
  const { getToken } = useAuth();

  return useMemo(() => {
    const client = axios.create({
      baseURL: `${API_BASE}/api/v1`,
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
      (err) => Promise.reject(err),
    );

    return client;
  }, [getToken]);
}
