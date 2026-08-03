import { apiClient } from "./client";

/* ===== Types ===== */
export interface AgentMode {
  slug: string;
  name: string;
  description: string;
  role_instructions: string;
  tools: string[];
  tool_categories: string[];
  preferred_model?: string;
  temperature: number;
  max_turns: number;
  icon?: string;
  color?: string;
  is_preset: boolean;
}

export interface ModeCreateRequest {
  slug: string;
  name: string;
  description?: string;
  role_instructions?: string;
  tools?: string[];
  tool_categories?: string[];
  preferred_model?: string;
  temperature?: number;
  max_turns?: number;
  icon?: string;
  color?: string;
}

export interface ModeUpdateRequest {
  name?: string;
  description?: string;
  role_instructions?: string;
  tools?: string[];
  tool_categories?: string[];
  preferred_model?: string;
  temperature?: number;
  max_turns?: number;
  icon?: string;
  color?: string;
}

export interface LoadFileRequest {
  filepath?: string;
}

export interface ActivateRequest {
  slug: string;
}

export interface ActivateResponse {
  mode: AgentMode;
  agent_config: Record<string, unknown>;
}

export interface AgentModeListResponse {
  data: AgentMode[];
  total: number;
}

/* ===== API ===== */
export const agentModesApi = {
  /** 列出所有 Agent 模式 */
  list() {
    return apiClient.get<AgentModeListResponse>("/agent/modes");
  },

  /** 获取单个模式详情 */
  get(slug: string) {
    return apiClient.get<AgentMode>(`/agent/modes/${slug}`);
  },

  /** 创建自定义模式 */
  create(data: ModeCreateRequest) {
    return apiClient.post<AgentMode>("/agent/modes", data);
  },

  /** 更新模式 */
  update(slug: string, data: ModeUpdateRequest) {
    return apiClient.put<AgentMode>(`/agent/modes/${slug}`, data);
  },

  /** 删除自定义模式（预设模式不可删，后端返回 403） */
  remove(slug: string) {
    return apiClient.delete(`/agent/modes/${slug}`);
  },

  /** 从 .roomodes 文件加载模式 */
  load(data: LoadFileRequest = {}) {
    return apiClient.post<{ imported: number }>("/agent/modes/load", data);
  },

  /** 激活模式，返回 AgentConfig */
  activate(data: ActivateRequest) {
    return apiClient.post<ActivateResponse>("/agent/modes/activate", data);
  },
};
