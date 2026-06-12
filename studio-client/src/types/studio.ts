export interface Project {
  id: string
  name: string
  description?: string
  status: 'draft' | 'building' | 'deploying' | 'running' | 'failed'
  created_at: string
  updated_at?: string
}

export interface Template {
  id: string
  name: string
  description?: string
  category?: string
  thumbnail_url?: string
}
