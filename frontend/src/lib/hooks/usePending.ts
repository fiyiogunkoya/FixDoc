"use client";

import { useQuery } from "@tanstack/react-query";

import { useApi } from "@/lib/api";
import type { PendingEntry } from "@/lib/types";

export function usePending(teamId: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["pending", teamId],
    queryFn: async () =>
      (await api.get<PendingEntry[]>(`/pending`, { params: { team_id: teamId } })).data,
    enabled: !!teamId,
  });
}
