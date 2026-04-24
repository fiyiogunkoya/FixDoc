"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { useApi } from "@/lib/api";
import type { ApiKey, ApiKeyWithToken, Team, TeamMember } from "@/lib/types";

export function useTeams() {
  const api = useApi();
  return useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get<Team[]>("/teams")).data,
  });
}

export function useCreateTeam() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; slug: string }) =>
      (await api.post<Team>("/teams", payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["teams"] }),
  });
}

export function useTeamMembers(teamId: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["teams", teamId, "members"],
    queryFn: async () =>
      (await api.get<TeamMember[]>(`/teams/${teamId}/members`)).data,
    enabled: !!teamId,
  });
}

export function useApiKeys(teamId: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["api-keys", teamId],
    queryFn: async () =>
      (await api.get<ApiKey[]>(`/api-keys`, { params: { team_id: teamId } })).data,
    enabled: !!teamId,
  });
}

export function useCreateApiKey(teamId: string | undefined) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) =>
      (
        await api.post<ApiKeyWithToken>(
          `/api-keys`,
          { name },
          { params: { team_id: teamId } },
        )
      ).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys", teamId] }),
  });
}

export function useDeleteApiKey(teamId: string | undefined) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: string) => {
      await api.delete(`/api-keys/${keyId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys", teamId] }),
  });
}
