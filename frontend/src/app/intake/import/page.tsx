// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC7 — Spreadsheet Import: upload XLSX → map columns → validate → review results → commit; commit disabled until ready; failed state shows error summary
"use client"

import * as React from "react"
import dynamic from "next/dynamic"
import Link from "next/link"
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowLeft,
  RefreshCw,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiClient, ApiError } from "@/client"
import type { ImportJob } from "@shared/types"
import { formatDateTime } from "@/lib/utils"

// @forgeplan-decision: D-frontend-6-rsi-dynamic-import -- react-spreadsheet-import loaded with next/dynamic + ssr:false. Why: library uses Chakra UI internally and browser-only APIs; SSR would fail
const ReactSpreadsheetImport = dynamic(
  () =>
    import("react-spreadsheet-import").then((mod) => ({
      default: mod.ReactSpreadsheetImport,
    })),
  { ssr: false }
)

// Field definitions for column mapping
const IMPORT_FIELDS = [
  {
    label: "Patient Name",
    key: "patient_name",
    fieldType: { type: "input" } as const,
    validations: [{ rule: "required" as const, errorMessage: "Patient name is required" }],
    example: "Jane Smith",
  },
  {
    label: "Date of Birth",
    key: "dob",
    fieldType: { type: "input" } as const,
    example: "1945-03-22",
  },
  {
    label: "MRN",
    key: "mrn",
    fieldType: { type: "input" } as const,
    example: "MRN123456",
  },
  {
    label: "Hospital Unit",
    key: "hospital_unit",
    fieldType: { type: "input" } as const,
    example: "4 North",
  },
  {
    label: "Room Number",
    key: "room_number",
    fieldType: { type: "input" } as const,
    example: "412B",
  },
  {
    label: "Primary Diagnosis",
    key: "primary_diagnosis_text",
    fieldType: { type: "input" } as const,
    example: "CVA with right hemiplegia",
  },
  {
    label: "Primary Insurance",
    key: "insurance_primary",
    fieldType: { type: "input" } as const,
    example: "Medicare Part A",
  },
  {
    label: "Discharge Target Date",
    key: "discharge_target_date",
    fieldType: { type: "input" } as const,
    example: "2026-04-15",
  },
  {
    label: "Priority Level",
    key: "priority_level",
    fieldType: {
      type: "select",
      options: [
        { label: "Routine", value: "routine" },
        { label: "Urgent", value: "urgent" },
        { label: "Emergent", value: "emergent" },
      ],
    } as const,
    example: "routine",
  },
] as const

type ImportPhase = "upload" | "reviewing" | "committing" | "complete" | "failed"

interface ImportJobResult extends ImportJob {
  error_summary?: string
}

export default function IntakeImportPage() {
  const [phase, setPhase] = React.useState<ImportPhase>("upload")
  const [importJobId, setImportJobId] = React.useState<string | null>(null)
  const [importJob, setImportJob] = React.useState<ImportJobResult | null>(null)
  const [isOpen, setIsOpen] = React.useState(false)
  const [commitError, setCommitError] = React.useState<string | null>(null)
  // F18: Use a ref instead of state for the interval ID to avoid stale-closure issues.
  // The ref is always current and the cleanup reliably clears on unmount.
  const pollIntervalRef = React.useRef<NodeJS.Timeout | null>(null)

  const clearPollInterval = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }

  // Poll import job status
  const pollJobStatus = React.useCallback(async (jobId: string) => {
    try {
      const job = await apiClient.fetch<ImportJobResult>(
        `/api/v1/intake/imports/${jobId}`
      )
      setImportJob(job)

      if (job.status === "ready") {
        setPhase("reviewing")
        clearPollInterval()
      } else if (job.status === "complete") {
        setPhase("complete")
        clearPollInterval()
      } else if (job.status === "failed") {
        setPhase("failed")
        clearPollInterval()
      }
    } catch {
      // Poll failure is non-fatal
    }
  }, [])

  React.useEffect(() => {
    if (importJobId && (phase === "reviewing" || phase === "committing")) {
      clearPollInterval()
      pollIntervalRef.current = setInterval(() => pollJobStatus(importJobId), 2000)
      // Cleanup on unmount or when deps change
      return () => clearPollInterval()
    }
  }, [importJobId, phase, pollJobStatus])

  // @forgeplan-spec: AC7 — react-spreadsheet-import onSubmit handler
  const handleImportData = async (
    data: { validData: Record<string, unknown>[]; invalidData?: Record<string, unknown>[] },
    _file: File
  ) => {
    setIsOpen(false)
    setCommitError(null)

    try {
      const job = await apiClient.fetch<ImportJob>("/api/v1/intake/imports", {
        method: "POST",
        body: JSON.stringify({
          rows: data.validData,
          file_name: "spreadsheet_import.xlsx",
          file_size_bytes: 0,
        }),
      })
      setImportJobId(job.id)
      setImportJob(job as ImportJobResult)
      setPhase("reviewing")
    } catch (err) {
      setCommitError(
        err instanceof ApiError
          ? `Upload failed: ${err.message}`
          : "Upload failed. Please try again."
      )
    }
  }

  // @forgeplan-spec: AC7 — Commit button disabled until ImportJob.status=ready
  const handleCommit = async () => {
    if (!importJobId || importJob?.status !== "ready") return

    setPhase("committing")
    setCommitError(null)

    try {
      await apiClient.fetch(`/api/v1/intake/imports/${importJobId}/commit`, {
        method: "POST",
      })
      // Poll for completion
      pollJobStatus(importJobId)
    } catch (err) {
      setCommitError(
        err instanceof ApiError
          ? `Commit failed: ${err.message}`
          : "Commit failed. Please try again."
      )
      setPhase("reviewing")
    }
  }

  const handleStartNew = () => {
    setPhase("upload")
    setImportJobId(null)
    setImportJob(null)
    setCommitError(null)
    clearPollInterval()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center gap-4 border-b px-6 py-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/intake">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to Intake
          </Link>
        </Button>
        <div>
          <h1 className="text-xl font-bold">Spreadsheet Import</h1>
          <p className="text-sm text-muted-foreground">
            Upload XLSX or CSV file to bulk-import patient cases
          </p>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* Error banner */}
        {commitError && (
          <div className="mb-4 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {commitError}
          </div>
        )}

        {/* Phase: Upload */}
        {phase === "upload" && (
          <div className="flex flex-col items-center justify-center min-h-64 gap-6">
            <div className="text-center">
              <h2 className="text-lg font-semibold">Upload Patient Census</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Upload an Excel or CSV file to import multiple cases at once.
                You will be able to map columns before committing.
              </p>
            </div>
            <Button size="lg" onClick={() => setIsOpen(true)}>
              Choose File to Import
            </Button>
          </div>
        )}

        {/* Phase: Reviewing (job is ready) */}
        {(phase === "reviewing" || phase === "committing") && importJob && (
          <div className="space-y-6 max-w-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Review Import</h2>
                <p className="text-sm text-muted-foreground">
                  File: {importJob.file_name}
                </p>
              </div>
              <Badge
                variant="outline"
                className={
                  importJob.status === "ready"
                    ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                    : "bg-amber-100 text-amber-700 border-amber-200"
                }
              >
                {importJob.status === "ready" ? "Ready to Commit" : importJob.status}
              </Badge>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-muted-foreground">Total Rows</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{importJob.total_rows ?? "—"}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-emerald-600">Will Create</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold text-emerald-600">{importJob.created_count}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-red-600">Errors</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold text-red-600">{importJob.failed_count}</p>
                </CardContent>
              </Card>
            </div>

            {/* Per-row error detail */}
            {importJob.error_detail_json && importJob.error_detail_json.length > 0 && (
              <div className="rounded-md border border-red-200 bg-red-50 p-4 space-y-2">
                <p className="text-sm font-medium text-red-700 flex items-center gap-1">
                  <AlertTriangle className="h-4 w-4" />
                  Row Errors
                </p>
                <ul className="space-y-1 max-h-40 overflow-y-auto">
                  {importJob.error_detail_json.map((err, i) => (
                    <li key={i} className="text-xs text-red-600">
                      Row {(err as { row?: number }).row ?? i + 1}:{" "}
                      {(err as { error?: string }).error ?? JSON.stringify(err)}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* @forgeplan-spec: AC7 — Commit disabled until status=ready */}
            <div className="flex gap-2">
              <Button
                onClick={handleCommit}
                disabled={
                  importJob.status !== "ready" || phase === "committing"
                }
              >
                {phase === "committing" ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    Committing...
                  </>
                ) : (
                  "Commit Import"
                )}
              </Button>
              <Button variant="outline" onClick={handleStartNew}>
                Start New Import
              </Button>
            </div>

            {importJob.status !== "ready" && (
              <p className="text-xs text-muted-foreground">
                Validating rows... Please wait.
              </p>
            )}
          </div>
        )}

        {/* Phase: Complete */}
        {phase === "complete" && importJob && (
          <div className="flex flex-col items-center justify-center min-h-64 gap-4 max-w-sm mx-auto text-center">
            <CheckCircle className="h-16 w-16 text-emerald-500" />
            <div>
              <h2 className="text-lg font-semibold">Import Complete!</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Successfully created {importJob.created_count} cases
                {importJob.failed_count > 0 &&
                  `, ${importJob.failed_count} rows failed`}
                .
              </p>
            </div>
            <div className="flex gap-2">
              <Button asChild>
                <Link href="/intake">View Intake</Link>
              </Button>
              <Button variant="outline" onClick={handleStartNew}>
                Start New Import
              </Button>
            </div>
          </div>
        )}

        {/* Phase: Failed — AC7: show error summary + "Start New Import" reset */}
        {phase === "failed" && (
          <div className="flex flex-col items-center justify-center min-h-64 gap-4 max-w-sm mx-auto text-center">
            <XCircle className="h-16 w-16 text-destructive" />
            <div>
              <h2 className="text-lg font-semibold">Import Failed</h2>
              <p className="text-sm text-muted-foreground mt-1">
                {importJob?.error_summary ??
                  "The import could not be completed. Please review your file and try again."}
              </p>
              {importJob?.error_detail_json &&
                importJob.error_detail_json.length > 0 && (
                  <ul className="mt-3 space-y-1 text-left max-h-40 overflow-y-auto">
                    {importJob.error_detail_json.map((err, i) => (
                      <li key={i} className="text-xs text-destructive">
                        {JSON.stringify(err)}
                      </li>
                    ))}
                  </ul>
                )}
            </div>
            <Button onClick={handleStartNew}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Start New Import
            </Button>
          </div>
        )}
      </div>

      {/* react-spreadsheet-import modal */}
      {typeof window !== "undefined" && (
        <ReactSpreadsheetImport
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
          onSubmit={handleImportData}
          fields={IMPORT_FIELDS}
        />
      )}
    </div>
  )
}
