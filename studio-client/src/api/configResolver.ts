import { client } from './client'

export interface VariableDef {
  name: string
  description: string
}

export interface ResolveResult {
  original: string
  resolved: string
}

export interface ResolveAllResult {
  original: Record<string, any>
  resolved: Record<string, any>
}

export const configResolverApi = {
  resolve(text: string, context?: {
    workspace_root?: string
    file?: string
    file_basename?: string
    file_extname?: string
    file_dirname?: string
    relative_file?: string
    line_number?: string
    selected_text?: string
    config_overrides?: Record<string, any>
    env_overrides?: Record<string, string>
  }) {
    return client.post<ResolveResult>('/api/v1/system/config-resolver/resolve', {
      text,
      workspace_root: context?.workspace_root ?? '',
      file: context?.file ?? '',
      file_basename: context?.file_basename ?? '',
      file_extname: context?.file_extname ?? '',
      file_dirname: context?.file_dirname ?? '',
      relative_file: context?.relative_file ?? '',
      line_number: context?.line_number ?? '',
      selected_text: context?.selected_text ?? '',
      config_overrides: context?.config_overrides ?? {},
      env_overrides: context?.env_overrides ?? {},
    })
  },

  resolveAll(data: Record<string, any>, context?: {
    workspace_root?: string
    file?: string
    config_overrides?: Record<string, any>
    env_overrides?: Record<string, string>
  }) {
    return client.post<ResolveAllResult>('/api/v1/system/config-resolver/resolve-all', {
      data,
      workspace_root: context?.workspace_root ?? '',
      file: context?.file ?? '',
      config_overrides: context?.config_overrides ?? {},
      env_overrides: context?.env_overrides ?? {},
    })
  },

  listVariables() {
    return client.get<{ variables: VariableDef[] }>('/api/v1/system/config-resolver/variables')
  },
}
