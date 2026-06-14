import type { AxiosError } from "axios"
import axios from "axios"
import { toast } from "@/composables/useToast"

/**
 * Extract a human-readable error message from an Axios error or API error response.
 */
export function extractErrorMessage(
  error: unknown,
  fallback = "An error occurred",
): string {
  if (error instanceof axios.AxiosError) {
    const err = error as AxiosError<{ detail?: unknown }>
    const detail = err.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      const first = detail[0]
      if (first && typeof first === "object" && "msg" in first) {
        return String((first as Record<string, unknown>).msg)
      }
    }
    return err.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

export function handleError(error: unknown, message = "An error occurred") {
  const detail = extractErrorMessage(error)
  toast(detail || message, "error")
}

export function getInitials(fullName?: string): string {
  if (!fullName) return "U"
  const parts = fullName.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}
