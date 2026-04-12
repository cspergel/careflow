// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC13 — StatusBadge renders correct label/color for each of the 14 statuses
import React from "react"
import { render, screen } from "@testing-library/react"
import { StatusBadge, STATUS_CONFIG, assertNeverStatus } from "../StatusBadge"
import type { CaseStatus } from "../StatusBadge"

const ALL_STATUSES: CaseStatus[] = [
  "new",
  "intake_in_progress",
  "intake_complete",
  "needs_clinical_review",
  "under_clinical_review",
  "ready_for_matching",
  "facility_options_generated",
  "outreach_pending_approval",
  "outreach_in_progress",
  "pending_facility_response",
  "declined_retry_needed",
  "accepted",
  "placed",
  "closed",
]

describe("StatusBadge", () => {
  test("renders all 14 statuses without error", () => {
    ALL_STATUSES.forEach((status) => {
      const { unmount } = render(<StatusBadge status={status} />)
      const config = STATUS_CONFIG[status]
      expect(screen.getByText(config.label)).toBeInTheDocument()
      unmount()
    })
  })

  test("renders correct label for each status", () => {
    const testCases: Array<[CaseStatus, string]> = [
      ["new", "New"],
      ["intake_in_progress", "Intake In Progress"],
      ["intake_complete", "Intake Complete"],
      ["needs_clinical_review", "Needs Clinical Review"],
      ["under_clinical_review", "Under Clinical Review"],
      ["ready_for_matching", "Ready for Matching"],
      ["facility_options_generated", "Facility Options Generated"],
      ["outreach_pending_approval", "Outreach Pending Approval"],
      ["outreach_in_progress", "Outreach In Progress"],
      ["pending_facility_response", "Pending Facility Response"],
      ["declined_retry_needed", "Declined — Retry Needed"],
      ["accepted", "Accepted"],
      ["placed", "Placed"],
      ["closed", "Closed"],
    ]

    testCases.forEach(([status, expectedLabel]) => {
      const { unmount } = render(<StatusBadge status={status} />)
      expect(screen.getByText(expectedLabel)).toBeInTheDocument()
      unmount()
    })
  })

  test("STATUS_CONFIG covers all 14 statuses", () => {
    expect(Object.keys(STATUS_CONFIG)).toHaveLength(14)
    ALL_STATUSES.forEach((status) => {
      expect(STATUS_CONFIG[status]).toBeDefined()
      expect(STATUS_CONFIG[status].label).toBeTruthy()
      expect(STATUS_CONFIG[status].color).toBeTruthy()
    })
  })

  test("STATUS_CONFIG entries have required fields", () => {
    ALL_STATUSES.forEach((status) => {
      const config = STATUS_CONFIG[status]
      expect(config).toHaveProperty("label")
      expect(config).toHaveProperty("color")
      expect(config).toHaveProperty("description")
      expect(typeof config.label).toBe("string")
      expect(typeof config.color).toBe("string")
      expect(typeof config.description).toBe("string")
    })
  })

  test("color classes use valid Tailwind patterns", () => {
    ALL_STATUSES.forEach((status) => {
      const { color } = STATUS_CONFIG[status]
      // Color should contain bg- and text- classes
      expect(color).toMatch(/bg-\w/)
      expect(color).toMatch(/text-\w/)
    })
  })

  test("assertNeverStatus throws for unexpected values", () => {
    expect(() => assertNeverStatus("unknown_status" as never)).toThrow(
      "Unexpected case status: unknown_status"
    )
  })

  test("TypeScript: STATUS_CONFIG satisfies Record<CaseStatus, StatusConfigEntry>", () => {
    // This test verifies the compile-time constraint is also a runtime constraint.
    // If a new status is added to CaseStatus but not STATUS_CONFIG,
    // the `satisfies` keyword in StatusBadge.tsx will cause a TypeScript error.
    const statusKeys = Object.keys(STATUS_CONFIG) as CaseStatus[]
    expect(statusKeys).toEqual(expect.arrayContaining(ALL_STATUSES))
    expect(ALL_STATUSES).toEqual(expect.arrayContaining(statusKeys))
  })
})
