import { apiClient } from "./client";
import type { PaginatedResponse } from "./client";

/* ===== Types ===== */
export type ArenaCategory = "chat" | "code" | "vision";

export interface ArenaCompareRequest {
  prompt: string;
  model_a?: string;
  model_b?: string;
  system_prompt?: string;
  temperature?: number;
  max_tokens?: number;
  category?: ArenaCategory;
}

export interface ArenaCompareResponse {
  comparison_id: string;
  prompt: string;
  model_a: string;
  response_a: string;
  latency_a_ms: number;
  tokens_a: number;
  model_b: string;
  response_b: string;
  latency_b_ms: number;
  tokens_b: number;
  category: ArenaCategory;
}

export interface VoteRequest {
  comparison_id: string;
  winner: "A" | "B" | "tie";
}

export interface EloRankingEntry {
  model_name: string;
  elo: number;
  wins: number;
  losses: number;
  ties: number;
  total_comparisons: number;
  category: ArenaCategory;
}

export interface EloRankingResponse {
  rankings: EloRankingEntry[];
  category: ArenaCategory;
}

export interface ArenaHistoryQuery {
  page?: number;
  size?: number;
  category?: ArenaCategory;
}

/* ===== API ===== */
export const modelArenaApi = {
  /** 并排对比两个模型 */
  compare(data: ArenaCompareRequest) {
    return apiClient.post<ArenaCompareResponse>("/arena/compare", data);
  },

  /** 为对比结果投票（ELO 更新） */
  vote(data: VoteRequest) {
    return apiClient.post<{ message: string }>("/arena/vote", data);
  },

  /** 获取 ELO 排行榜 */
  getRankings(category?: ArenaCategory) {
    const params = category ? { category } : {};
    return apiClient.get<EloRankingResponse>("/arena/rankings", { params });
  },

  /** 获取对比历史（仅已投票） */
  getHistory(query: ArenaHistoryQuery = {}) {
    return apiClient.get<PaginatedResponse<ArenaCompareResponse>>(
      "/arena/history",
      { params: query },
    );
  },
};
