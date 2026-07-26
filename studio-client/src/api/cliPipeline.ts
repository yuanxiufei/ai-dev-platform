import { client } from './client'

export interface PipelineSample {
  name: string
  description: string
  yaml: string
}

export interface PipelineResult {
  name: string
  success: boolean
  steps: Array<{
    id: string
    command: string
    exit_code: number
    stdout: string
    stderr: string
    duration_ms: number
    success: boolean
  }>
  total_duration_ms: number
}

export const cliPipelineApi = {
  runFromFile(filePath: string, variables?: Record<string, any>) {
    return client.post<PipelineResult>('/api/v1/system/cli-pipeline/run-file', {
      file_path: filePath,
      variables,
    })
  },

  runInline(name: string, steps: Array<Record<string, any>>, variables?: Record<string, any>) {
    return client.post<PipelineResult>('/api/v1/system/cli-pipeline/run-inline', {
      name,
      steps,
      variables,
    })
  },

  runYaml(yamlContent: string) {
    return client.post<PipelineResult>('/api/v1/system/cli-pipeline/run-yaml', yamlContent, {
      headers: { 'Content-Type': 'text/plain' },
    })
  },

  getSamples() {
    return client.get<{ samples: PipelineSample[] }>('/api/v1/system/cli-pipeline/samples')
  },
}
