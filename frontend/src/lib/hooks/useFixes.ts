"use client";

import { useQuery } from "@tanstack/react-query";

import { useApi } from "@/lib/api";
import type { Fix, Paginated } from "@/lib/types";

export function useFixes(teamId: string | undefined, params?: { q?: string; limit?: number; offset?: number }) {
  const api = useApi();
  return useQuery({
    queryKey: ["fixes", teamId, params],
    queryFn: async () =>
      (
        await api.get<Paginated<Fix>>(`/fixes`, {
          params: { team_id: teamId, ...params },
        })
      ).data,
    enabled: !!teamId,
  });
}

export function useFix(teamId: string | undefined, fixId: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["fixes", teamId, fixId],
    queryFn: async () =>
      (
        await api.get<Fix>(`/fixes/${fixId}`, {
          params: { team_id: teamId },
        })
      ).data,
    enabled: !!teamId && !!fixId,
  });
}
