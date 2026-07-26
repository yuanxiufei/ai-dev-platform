import { client } from './client'

export interface RemoteSession {
  connection_id: string
  connection_type: string
  state: string
  connected_at: string
  last_heartbeat: string
}

export interface PortMapping {
  mapping_id: string
  local_port: number
  proxy_port: number
  service_name: string
  status: string
  visibility: string
  connection_id: string
}

export interface WorkspaceTrust {
  workspace_path: string
  trust_level: string
  reason: string
  granted_at: string
  granted_by: string
  can_exec_shell: boolean
  can_write_files: boolean
  can_network: boolean
}

export const remoteApi = {
  // Sessions
  createSession(metadata?: Record<string, any>) {
    return client.post<{ connection_id: string; token: string }>('/api/v1/system/remote/sessions', metadata)
  },

  listSessions() {
    return client.get<{ data: RemoteSession[]; total: number }>('/api/v1/system/remote/sessions')
  },

  endSession(connectionId: string) {
    return client.delete(`/api/v1/system/remote/sessions/${connectionId}`)
  },

  // Port Forwarding
  createPort(connectionId: string, localPort: number, serviceName?: string) {
    return client.post('/api/v1/system/remote/ports', null, {
      params: { connection_id: connectionId, local_port: localPort, service_name: serviceName ?? '' },
    })
  },

  listPorts(connectionId?: string) {
    return client.get<{ data: PortMapping[]; total: number }>('/api/v1/system/remote/ports', {
      params: connectionId ? { connection_id: connectionId } : undefined,
    })
  },

  closePort(mappingId: string) {
    return client.delete(`/api/v1/system/remote/ports/${mappingId}`)
  },

  // Workspace Trust
  getTrust(workspacePath: string) {
    return client.get<WorkspaceTrust>(`/api/v1/system/remote/trust/${encodeURIComponent(workspacePath)}`)
  },

  grantTrust(workspacePath: string, level: string = 'trusted') {
    return client.post(`/api/v1/system/remote/trust/${encodeURIComponent(workspacePath)}/grant`, null, {
      params: { level },
    })
  },
}
