// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC13 — STATUS_CONFIG map with TypeScript exhaustiveness checking; adding new status without updating STATUS_CONFIG causes TypeScript compile error
"use client"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/**
 * All 14 case statuses in the PlacementOps workflow.
 * This type union drives StatusBadge exhaustiveness checking.
 */
export type CaseStatus =
  | "new"
  | "intake_in_progress"
  | "intake_complete"
  | "needs_clinical_review"
  | "under_clinical_review"
  | "ready_for_matching"
  | "facility_options_generated"
  | "outreach_pending_approval"
  | "outreach_in_progress"
  | "pending_facility_response"
  | "declined_retry_needed"
  | "accepted"
  | "placed"
  | "closed"

export interface StatusConfigEntry {
  label: string
  color: string
  description: string
}

/**
 * STATUS_CONFIG maps every CaseStatus to display metadata.
 * TypeScript will produce a compile error if any status is missing from this map.
 * The `satisfies` keyword enforces exhaustiveness at compile time.
 */
export const STATUS_CONFIG = {
  new: {
    label: "New",
    color: "bg-slate-100 text-slate-700 border-slate-200",
    description: "Case created, intake not yet started",
  },
  intake_in_progress: {
    label: "Intake In Progress",
    color: "bg-blue-100 text-blue-700 border-blue-200",
    description: "Intake staff is actively working on this case",
  },
  intake_complete: {
    label: "Intake Complete",
    color: "bg-blue-100 text-blue-700 border-blue-200",
    description: "Intake complete; awaiting clinical review assignment",
  },
  needs_clinical_review: {
    label: "Needs Clinical Review",
    color: "bg-amber-100 text-amber-700 border-amber-200",
    description: "Clinical review required before matching can proceed",
  },
  under_clinical_review: {
    label: "Under Clinical Review",
    color: "bg-amber-100 text-amber-700 border-amber-200",
    description: "Clinical reviewer is actively reviewing this case",
  },
  ready_for_matching: {
    label: "Ready for Matching",
    color: "bg-blue-100 text-blue-700 border-blue-200",
    description: "Clinical review complete; ready for facility matching",
  },
  facility_options_generated: {
    label: "Facility Options Generated",
    color: "bg-amber-100 text-amber-700 border-amber-200",
    description: "Matching engine has generated facility options",
  },
  outreach_pending_approval: {
    label: "Outreach Pending Approval",
    color: "bg-amber-100 text-amber-700 border-amber-200",
    description: "Outreach draft awaiting manager approval",
  },
  outreach_in_progress: {
    label: "Outreach In Progress",
    color: "bg-blue-100 text-blue-700 border-blue-200",
    description: "Outreach communications sent to facilities",
  },
  pending_facility_response: {
    label: "Pending Facility Response",
    color: "bg-amber-100 text-amber-700 border-amber-200",
    description: "Waiting for facility to respond to outreach",
  },
  declined_retry_needed: {
    label: "Declined — Retry Needed",
    color: "bg-red-100 text-red-700 border-red-200",
    description: "Facility declined; coordinator must route to retry",
  },
  accepted: {
    label: "Accepted",
    color: "bg-emerald-100 text-emerald-700 border-emerald-200",
    description: "Facility has accepted the patient",
  },
  placed: {
    label: "Placed",
    color: "bg-emerald-100 text-emerald-700 border-emerald-200",
    description: "Patient has been placed at the facility",
  },
  closed: {
    label: "Closed",
    color: "bg-slate-100 text-slate-700 border-slate-200",
    description: "Case is closed",
  },
} as const satisfies Record<CaseStatus, StatusConfigEntry>

/**
 * Exhaustiveness check function — used to ensure all 14 statuses are handled.
 * TypeScript will error if this function is called with a value that is not `never`.
 */
export function assertNeverStatus(x: never): never {
  throw new Error("Unexpected case status: " + String(x))
}

interface StatusBadgeProps {
  status: CaseStatus
  className?: string
  showDescription?: boolean
}

/**
 * StatusBadge renders a styled badge for any of the 14 case statuses.
 * Adding a new status to CaseStatus without updating STATUS_CONFIG causes
 * a TypeScript compile error via the `satisfies` constraint.
 */
export function StatusBadge({
  status,
  className,
  showDescription = false,
}: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    color: "bg-slate-100 text-slate-600 border-slate-200",
    description: status,
  }

  return (
    <Badge
      variant="outline"
      className={cn("text-xs font-medium border", config.color, className)}
      title={showDescription ? config.description : undefined}
    >
      {config.label}
    </Badge>
  )
}

export default StatusBadge
