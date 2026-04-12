// @forgeplan-node: frontend-app-shell
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import type { UserRole } from "@shared/types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formats a date string for display.
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—"
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

/**
 * Formats a datetime string for display.
 */
export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "—"
  return new Date(dateStr).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/**
 * Returns days elapsed since the given date string.
 */
export function daysElapsed(dateStr: string | null | undefined): number {
  if (!dateStr) return 0
  const elapsed = Date.now() - new Date(dateStr).getTime()
  return Math.floor(elapsed / (1000 * 60 * 60 * 24))
}

/**
 * Converts a snake_case key to a Title Case label.
 */
export function toTitleCase(str: string): string {
  return str
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

/**
 * F23: Returns the role-appropriate landing page path.
 * Extracted from layout.tsx and page.tsx to avoid duplication.
 */
export function getRoleLanding(role: UserRole): string {
  switch (role) {
    case "intake_staff":
      return "/intake"
    case "clinical_reviewer":
    case "placement_coordinator":
      return "/queue"
    case "manager":
    case "admin":
    case "read_only":
      return "/dashboard"
    default:
      return "/dashboard"
  }
}
