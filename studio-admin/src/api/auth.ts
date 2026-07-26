import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
}

/** OAuth2 密码模式登录 */
export async function loginWithPassword(email: string, password: string): Promise<LoginResponse> {
  const formData = new URLSearchParams()
  formData.append('username', email)
  formData.append('password', password)

  const res = await client.post<LoginResponse>('/login/access-token', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}
