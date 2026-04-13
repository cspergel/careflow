// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC6 — Intake Workbench: census table, create case form, duplicate warning, quick-edit via Sheet
"use client"

import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Plus, Upload, AlertTriangle } from "lucide-react"
import Link from "next/link"
import { ColumnDef } from "@tanstack/react-table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { StatusBadge } from "@/components/StatusBadge"
import { CaseTable } from "@/components/CaseTable"
import { FilterBar } from "@/components/FilterBar"
import { formatDate } from "@/lib/utils"
import { apiClient, ApiError } from "@/client"
import type { PatientCase } from "@shared/types"

// Create case form schema
const createCaseSchema = z.object({
  patient_name: z.string().min(1, "Patient name is required"),
  dob: z.string().optional(),
  hospital_id: z.string().min(1, "Hospital is required"),
  hospital_unit: z.string().optional(),
  room_number: z.string().optional(),
  primary_diagnosis_text: z.string().optional(),
  insurance_primary: z.string().optional(),
  priority_level: z.enum(["routine", "urgent", "emergent"]).optional(),
})

type CreateCaseFormData = z.infer<typeof createCaseSchema>

// F15: Shape matches backend schema for duplicate_warning field in POST /cases response
interface DuplicateWarning {
  existing_case_id: string
  patient_name: string
  dob: string
  hospital_id: string
  current_status: string
}

// @forgeplan-spec: AC6 — Table columns for intake workbench
const intakeColumns: ColumnDef<PatientCase>[] = [
  {
    accessorKey: "patient_name",
    header: "Patient",
    cell: ({ row }) => (
      <Link
        href={`/cases/${row.original.id}`}
        className="font-medium hover:underline"
      >
        {row.getValue("patient_name")}
      </Link>
    ),
  },
  {
    accessorKey: "dob",
    header: "DOB",
    cell: ({ row }) => formatDate(row.getValue("dob")),
  },
  {
    accessorKey: "current_status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.getValue("current_status")} />,
  },
  {
    accessorKey: "primary_diagnosis_text",
    header: "Diagnosis",
    cell: ({ row }) => (
      <span className="truncate max-w-48 block text-sm text-muted-foreground">
        {row.getValue("primary_diagnosis_text") ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "insurance_primary",
    header: "Insurance",
    cell: ({ row }) => row.getValue("insurance_primary") ?? "—",
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDate(row.getValue("created_at")),
  },
]

export default function IntakePage() {
  const [cases, setCases] = React.useState<PatientCase[]>([])
  const [totalCount, setTotalCount] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [createSheetOpen, setCreateSheetOpen] = React.useState(false)
  const [editCase, setEditCase] = React.useState<PatientCase | null>(null)
  const [duplicateWarning, setDuplicateWarning] =
    React.useState<DuplicateWarning | null>(null)
  const [pageError, setPageError] = React.useState<string | null>(null)

  const form = useForm<CreateCaseFormData>({
    resolver: zodResolver(createCaseSchema),
    defaultValues: { priority_level: "routine" },
  })

  // Load intake cases
  React.useEffect(() => {
    loadCases()
  }, [])

  const loadCases = async () => {
    setIsLoading(true)
    setPageError(null)
    try {
      // F13: backend PaginatedCasesResponse uses key `cases`, not `items`
      const data = await apiClient.fetch<{
        cases: PatientCase[]
        total: number
      }>("/api/v1/cases?status=new&status=intake_in_progress&page_size=50")
      setCases(data.cases)
      setTotalCount(data.total)
    } catch (err) {
      setPageError(
        err instanceof ApiError
          ? `Failed to load cases: ${err.message}`
          : "Failed to load cases"
      )
    } finally {
      setIsLoading(false)
    }
  }

  // F14: GET /api/v1/cases/check-duplicate doesn't exist — backend embeds duplicate_warning
  // in the POST /api/v1/cases response. Handle it there instead.

  const handleCreateCase = async (data: CreateCaseFormData) => {
    try {
      // F14: Backend may return duplicate_warning in the POST response body
      const response = await apiClient.fetch<{ id: string; duplicate_warning?: DuplicateWarning }>(
        "/api/v1/cases",
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      )
      if (response.duplicate_warning) {
        setDuplicateWarning(response.duplicate_warning)
        // Don't close — let the user review the warning. Case was still created.
      } else {
        setDuplicateWarning(null)
      }
      setCreateSheetOpen(false)
      form.reset()
      await loadCases()
    } catch (err) {
      form.setError("root", {
        message:
          err instanceof ApiError
            ? err.message
            : "Failed to create case. Please try again.",
      })
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-bold">Intake Workbench</h1>
          <p className="text-sm text-muted-foreground">
            Manage incoming patient cases
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/intake/import">
              <Upload className="h-4 w-4 mr-2" />
              Import
            </Link>
          </Button>
          <Button size="sm" onClick={() => setCreateSheetOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Case
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6 space-y-4">
        {pageError && (
          <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {pageError}
          </div>
        )}

        {/* F29: pageKey must match CaseTable's pageKey so filter URL params stay in sync */}
        <FilterBar
          pageKey="intake"
          statusOptions={[
            "new",
            "intake_in_progress",
            "intake_complete",
          ]}
        />

        {/* F11: pageKey namespaces nuqs URL params so intake filters don't contaminate other pages */}
        <CaseTable
          data={cases}
          columns={intakeColumns}
          totalCount={totalCount}
          isLoading={isLoading}
          onRowClick={(row) => setEditCase(row as PatientCase)}
          pageKey="intake"
        />
      </div>

      {/* @forgeplan-spec: AC6 — Create case Sheet (shadcn/ui Sheet, NOT Dialog) */}
      <Sheet open={createSheetOpen} onOpenChange={setCreateSheetOpen}>
        <SheetContent side="right" className="w-[480px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>New Patient Case</SheetTitle>
            <SheetDescription>
              Enter patient intake information to create a new case
            </SheetDescription>
          </SheetHeader>

          <form
            onSubmit={form.handleSubmit(handleCreateCase)}
            className="mt-6 space-y-4"
          >
            {form.formState.errors.root && (
              <div className="rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-sm text-destructive">
                {form.formState.errors.root.message}
              </div>
            )}

            {/* Duplicate warning */}
            {/* F14/F15: duplicate_warning comes back in POST response; shape matches backend */}
            {duplicateWarning && (
              <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-amber-800">
                      Possible duplicate detected
                    </p>
                    <p className="text-xs text-amber-700 mt-0.5">
                      An existing case was found for {duplicateWarning.patient_name} (DOB:{" "}
                      {duplicateWarning.dob}) — status: {duplicateWarning.current_status}.{" "}
                      Case ID: {duplicateWarning.existing_case_id.slice(0, 8)}…
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="patient_name">Patient Name *</Label>
              <Input
                id="patient_name"
                placeholder="First Last"
                {...form.register("patient_name")}
              />
              {form.formState.errors.patient_name && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.patient_name.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="dob">Date of Birth</Label>
              <Input
                id="dob"
                type="date"
                {...form.register("dob")}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="hospital_id">Hospital *</Label>
              <Input
                id="hospital_id"
                placeholder="Hospital ID or name"
                {...form.register("hospital_id")}
              />
              {form.formState.errors.hospital_id && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.hospital_id.message}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="hospital_unit">Unit</Label>
                <Input
                  id="hospital_unit"
                  placeholder="e.g., 4N"
                  {...form.register("hospital_unit")}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="room_number">Room</Label>
                <Input
                  id="room_number"
                  placeholder="e.g., 412B"
                  {...form.register("room_number")}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="primary_diagnosis_text">Primary Diagnosis</Label>
              <Input
                id="primary_diagnosis_text"
                placeholder="e.g., CVA with right hemiplegia"
                {...form.register("primary_diagnosis_text")}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="insurance_primary">Primary Insurance</Label>
              <Input
                id="insurance_primary"
                placeholder="e.g., Medicare Part A"
                {...form.register("insurance_primary")}
              />
            </div>

            <div className="space-y-1.5">
              <Label>Priority Level</Label>
              <Select
                defaultValue="routine"
                onValueChange={(val) =>
                  form.setValue(
                    "priority_level",
                    val as "routine" | "urgent" | "emergent"
                  )
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="routine">Routine</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="emergent">Emergent</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2 pt-2">
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "Creating..." : "Create Case"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setCreateSheetOpen(false)
                  form.reset()
                  setDuplicateWarning(null)
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        </SheetContent>
      </Sheet>

      {/* Quick-edit Sheet for existing case */}
      <Sheet open={!!editCase} onOpenChange={(open) => !open && setEditCase(null)}>
        <SheetContent side="right" className="w-[480px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Edit Case</SheetTitle>
            <SheetDescription>
              {editCase?.patient_name}
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            {editCase && (
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-muted-foreground">Status</p>
                  <StatusBadge status={editCase.current_status} className="mt-1" />
                </div>
                <Button
                  size="sm"
                  asChild
                  className="w-full"
                >
                  <Link href={`/cases/${editCase.id}`}>
                    Open Full Case Detail
                  </Link>
                </Button>
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
