"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { useApi } from "@/lib/api";

export interface GitHubInstallation {
  installation_id: number;
  repositories: Array<{ id: number; full_name: string; private: boolean }>;
}

export function useGitHubInstallations(teamId: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["integrations", "github", teamId],
    queryFn: async () =>
      (
        await api.get<GitHubInstallation[]>("/integrations/github", {
          params: { team_id: teamId },
        })
      ).data,
    enabled: !!teamId,
  });
}

export function useLinkGitHub(teamId: string | undefined) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (installationId: number) =>
      (
        await api.post<GitHubInstallation>(
          "/integrations/github",
          { installation_id: installationId },
          { params: { team_id: teamId } },
        )
      ).data,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["integrations", "github", teamId] }),
  });
}

export function useUnlinkGitHub(teamId: string | undefined) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (installationId: number) => {
      await api.delete(`/integrations/github/${installationId}`, {
        params: { team_id: teamId },
      });
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["integrations", "github", teamId] }),
  });
}
