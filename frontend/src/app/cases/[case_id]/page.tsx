// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC9 — Patient Case Detail: 6 tabs (Overview, Clinical Review, Facility Matches, Outreach, Timeline, Audit); Audit tab only for admin
"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { ArrowLeft, RefreshCw, AlertTriangle } from "lucide-react"
import Link from "next/link"
import { parseAsString, useQueryState } from "nuqs"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { StatusBadge } from "@/components/StatusBadge"
import { FacilityCard, type FacilityCardData } from "@/components/FacilityCard"
import { ActivityTimeline, type TimelineEvent } from "@/components/ActivityTimeline"
import { DraftEditor, type DraftTemplateOption, type ExistingDraft } from "@/components/DraftEditor"
import { ClinicalAssessmentForm, type ClinicalAssessmentFormData } from "@/components/ClinicalAssessmentForm"
import { apiClient, ApiError } from "@/client"
import { formatDate, formatDateTime } from "@/lib/utils"
import { createClient } from "@/lib/supabase/client"
import type { PatientCase, ClinicalAssessment, OutreachTemplate } from "@shared/types"

// User role from Supabase session (client-side)
function useCurrentUserRole() {
  const [role, setRole] = React.useState<string | null>(null)
  React.useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(async ({ data: { user } }) => {
      if (user) {
        const { data } = await supabase
          .from("users")
          .select("role_key")
          .eq("id", user.id)
          .single()
        setRole(data?.role_key ?? null)
      }
    })
  }, [])
  return role
}

export default function CaseDetailPage() {
  const params = useParams()
  const caseId = params.case_id as string
  const userRole = useCurrentUserRole()

  // Tab state in URL for deep-linkable tabs
  const [activeTab, setActiveTab] = useQueryState(
    "tab",
    parseAsString.withDefault("overview")
  )

  const [patientCase, setPatientCase] = React.useState<PatientCase | null>(null)
  const [assessment, setAssessment] = React.useState<ClinicalAssessment | null>(null)
  const [matches, setMatches] = React.useState<FacilityCardData[]>([])
  const [outreachActions, setOutreachActions] = React.useState<ExistingDraft[]>([])
  const [templates, setTemplates] = React.useState<DraftTemplateOption[]>([])
  const [timeline, setTimeline] = React.useState<TimelineEvent[]>([])
  const [auditEvents, setAuditEvents] = React.useState<TimelineEvent[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [pageError, setPageError] = React.useState<string | null>(null)

  // AC10: Re-match warning state
  const [rematchSheetOpen, setRematchSheetOpen] = React.useState(false)
  const [isGeneratingMatches, setIsGeneratingMatches] = React.useState(false)
  const [matchError, setMatchError] = React.useState<string | null>(null)

  // AC10: Contextual prompt after selecting facility
  const [selectedFacilityForOutreach, setSelectedFacilityForOutreach] =
    React.useState<string | null>(null)

  React.useEffect(() => {
    loadCaseData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  // F10: Re-load audit events when userRole resolves (it starts null and updates async)
  React.useEffect(() => {
    if (userRole === "admin" && !isLoading) {
      apiClient
        .fetch<{ events: TimelineEvent[] }>(`/api/v1/cases/${caseId}/audit`)
        .then((auditData) => setAuditEvents(auditData.events))
        .catch(() => {
          // Audit load failure is non-critical
        })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userRole, caseId])

  const loadCaseData = async () => {
    setIsLoading(true)
    setPageError(null)
    try {
      const [caseData, matchData, outreachData, templateData, timelineData] =
        await Promise.allSettled([
          apiClient.fetch<PatientCase>(`/api/v1/cases/${caseId}`),
          // F7: backend returns key `matches`, not `items`
          apiClient.fetch<{ matches: FacilityCardData[] }>(
            `/api/v1/cases/${caseId}/matches`
          ),
          // F2: correct endpoint is /outreach-actions
          apiClient.fetch<{ items: ExistingDraft[] }>(
            `/api/v1/cases/${caseId}/outreach-actions`
          ),
          // F5: correct route is /api/v1/templates/outreach
          apiClient.fetch<{ items: OutreachTemplate[] }>(
            `/api/v1/templates/outreach`
          ),
          apiClient.fetch<{ events: TimelineEvent[] }>(
            `/api/v1/cases/${caseId}/timeline`
          ),
        ])

      if (caseData.status === "fulfilled") setPatientCase(caseData.value)
      else setPageError("Failed to load case data")

      // F7: backend returns key `matches`
      if (matchData.status === "fulfilled") setMatches(matchData.value.matches)
      if (outreachData.status === "fulfilled")
        setOutreachActions(outreachData.value.items)
      if (templateData.status === "fulfilled") {
        setTemplates(
          (templateData.value.items as OutreachTemplate[]).map((t) => ({
            id: t.id,
            template_name: t.template_name,
            template_type: t.template_type,
            subject_template: t.subject_template,
            body_template: t.body_template,
          }))
        )
      }
      if (timelineData.status === "fulfilled")
        setTimeline(timelineData.value.events)

      // Load assessment if available
      // F12: backend returns key `assessments`, not `items`
      try {
        const assessmentData = await apiClient.fetch<{ assessments: ClinicalAssessment[] }>(
          `/api/v1/cases/${caseId}/assessments`
        )
        if (assessmentData.assessments.length > 0) {
          setAssessment(assessmentData.assessments[0])
        }
      } catch {
        // No assessment yet — that's OK
      }

      // Load audit events for admin
      if (userRole === "admin") {
        try {
          const auditData = await apiClient.fetch<{ events: TimelineEvent[] }>(
            `/api/v1/cases/${caseId}/audit`
          )
          setAuditEvents(auditData.events)
        } catch {
          // Audit load failure is non-critical
        }
      }
    } catch (err) {
      setPageError(
        err instanceof ApiError ? err.message : "Failed to load case"
      )
    } finally {
      setIsLoading(false)
    }
  }

  // AC10: Generate/Regenerate matches
  const handleGenerateMatches = async (confirmed: boolean = false) => {
    if (!confirmed && matches.length > 0) {
      setRematchSheetOpen(true)
      return
    }
    setRematchSheetOpen(false)
    setIsGeneratingMatches(true)
    setMatchError(null)
    try {
      await apiClient.fetch(`/api/v1/cases/${caseId}/matches/generate`, {
        method: "POST",
      })
      // F7: backend returns key `matches`
      const matchData = await apiClient.fetch<{ matches: FacilityCardData[] }>(
        `/api/v1/cases/${caseId}/matches`
      )
      setMatches(matchData.matches)
    } catch (err) {
      setMatchError(
        err instanceof ApiError ? err.message : "Failed to generate matches"
      )
    } finally {
      setIsGeneratingMatches(false)
    }
  }

  // AC10: Select/deselect facility for outreach
  // F16: backend endpoint takes no body for the select toggle
  const handleSelectFacility = async (facilityMatchId: string, selected: boolean) => {
    try {
      await apiClient.fetch(
        `/api/v1/cases/${caseId}/matches/${facilityMatchId}/select`,
        {
          method: "POST",
        }
      )
      setMatches((prev) =>
        prev.map((m) =>
          m.id === facilityMatchId
            ? { ...m, selected_for_outreach: selected }
            : m
        )
      )
      if (selected) {
        setSelectedFacilityForOutreach(facilityMatchId)
      }
    } catch (err) {
      setMatchError(
        err instanceof ApiError ? err.message : "Failed to update selection"
      )
    }
  }

  const handleSaveClinicalAssessment = async (
    data: ClinicalAssessmentFormData
  ) => {
    // F9: PATCH route is /assessments/{assessment_id}, POST creates on the case
    if (assessment) {
      await apiClient.fetch(`/api/v1/assessments/${assessment.id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      })
    } else {
      await apiClient.fetch(`/api/v1/cases/${caseId}/assessments`, {
        method: "POST",
        body: JSON.stringify(data),
      })
    }
    await loadCaseData()
  }

  const handleCreateOutreach = async (draftData: {
    channel: string
    draft_body: string
    draft_subject?: string
    template_id?: string
  }) => {
    // F8: correct route is /outreach-actions
    await apiClient.fetch(`/api/v1/cases/${caseId}/outreach-actions`, {
      method: "POST",
      body: JSON.stringify({
        ...draftData,
        action_type: "facility_outreach",
      }),
    })
    await loadCaseData()
  }

  // F3: backend registers at /outreach-actions/{id}/approve|mark-sent|cancel
  const handleApproveOutreach = async (actionId: string) => {
    await apiClient.fetch(`/api/v1/outreach-actions/${actionId}/approve`, {
      method: "POST",
    })
    await loadCaseData()
  }

  const handleMarkSentOutreach = async (actionId: string) => {
    await apiClient.fetch(`/api/v1/outreach-actions/${actionId}/mark-sent`, {
      method: "POST",
    })
    await loadCaseData()
  }

  const handleCancelOutreach = async (actionId: string) => {
    await apiClient.fetch(`/api/v1/outreach-actions/${actionId}/cancel`, {
      method: "POST",
    })
    await loadCaseData()
  }

  if (isLoading) {
    return (
      <div className="animate-pulse p-6 space-y-4">
        {/* Header skeleton */}
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="bg-gray-200 rounded h-6 w-48" />
            <div className="bg-gray-200 rounded h-4 w-72" />
          </div>
          <div className="bg-gray-200 rounded h-8 w-24" />
        </div>
        {/* Tab bar skeleton */}
        <div className="flex gap-2 border-b pb-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-gray-200 rounded h-8 w-24" />
          ))}
        </div>
        {/* Tab content skeleton */}
        <div className="space-y-3 pt-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="rounded-md border px-4 py-3">
              <div className="bg-gray-200 rounded h-4 w-40 mb-2" />
              <div className="bg-gray-200 rounded h-3 w-64" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (pageError || !patientCase) {
    return (
      <div className="p-6">
        <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {pageError ?? "Case not found"}
        </div>
        <Button className="mt-4" variant="outline" asChild>
          <Link href="/queue">Back to Queue</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Case header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-3 mb-2">
          <Button variant="ghost" size="sm" asChild className="-ml-2">
            <Link href="/queue">
              <ArrowLeft className="h-4 w-4 mr-1" />
              Queue
            </Link>
          </Button>
        </div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold">{patientCase.patient_name}</h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground flex-wrap">
              {patientCase.dob && (
                <span>DOB: {formatDate(patientCase.dob)}</span>
              )}
              {patientCase.mrn && <span>MRN: {patientCase.mrn}</span>}
              {patientCase.primary_diagnosis_text && (
                <span className="truncate max-w-sm">
                  {patientCase.primary_diagnosis_text}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {patientCase.priority_level &&
              patientCase.priority_level !== "routine" && (
                <Badge
                  className={
                    patientCase.priority_level === "emergent"
                      ? "bg-red-100 text-red-700 border-red-200"
                      : "bg-amber-100 text-amber-700 border-amber-200"
                  }
                >
                  {patientCase.priority_level.toUpperCase()}
                </Badge>
              )}
            <StatusBadge status={patientCase.current_status} />
          </div>
        </div>
      </div>

      {/* @forgeplan-spec: AC9 — 6-tab case detail; Audit tab only for admin */}
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex-1 flex flex-col overflow-hidden"
      >
        <div className="border-b px-6">
          <TabsList className="h-auto p-0 bg-transparent rounded-none border-0">
            {[
              "overview",
              "clinical",
              "matches",
              "outreach",
              "timeline",
              ...(userRole === "admin" ? ["audit"] : []),
            ].map((tab) => (
              <TabsTrigger
                key={tab}
                value={tab}
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent capitalize px-4 py-2.5 text-sm"
              >
                {tab === "matches"
                  ? "Facility Matches"
                  : tab.charAt(0).toUpperCase() + tab.slice(1).replace("_", " ")}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <div className="flex-1 overflow-auto">
          {/* Overview tab */}
          <TabsContent value="overview" className="p-6 mt-0 space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                ["Insurance (Primary)", patientCase.insurance_primary ?? "—"],
                ["Insurance (Secondary)", patientCase.insurance_secondary ?? "—"],
                ["Hospital Unit", patientCase.hospital_unit ?? "—"],
                ["Room", patientCase.room_number ?? "—"],
                ["Patient ZIP", patientCase.patient_zip ?? "—"],
                [
                  "Discharge Target",
                  formatDate(patientCase.discharge_target_date),
                ],
                ["Created", formatDateTime(patientCase.created_at)],
                ["Updated", formatDateTime(patientCase.updated_at)],
              ].map(([label, value]) => (
                <div key={label} className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-sm font-medium">{value}</p>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* Clinical Review tab — AC12 */}
          <TabsContent value="clinical" className="p-6 mt-0">
            <ClinicalAssessmentForm
              defaultValues={(assessment as unknown) as Partial<ClinicalAssessmentFormData>}
              onSubmit={handleSaveClinicalAssessment}
            />
          </TabsContent>

          {/* Facility Matches tab — AC10 */}
          <TabsContent value="matches" className="p-6 mt-0 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Facility Matches</h2>
              <Button
                size="sm"
                onClick={() => handleGenerateMatches(false)}
                disabled={isGeneratingMatches}
              >
                {isGeneratingMatches ? (
                  <>
                    <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                    Generating...
                  </>
                ) : matches.length > 0 ? (
                  "Regenerate"
                ) : (
                  "Generate Matches"
                )}
              </Button>
            </div>

            {matchError && (
              <div className="rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-sm text-destructive">
                {matchError}
              </div>
            )}

            {/* AC10: Contextual prompt after selecting */}
            {selectedFacilityForOutreach && (
              <div className="rounded-md bg-primary/5 border border-primary/20 px-4 py-3 text-sm flex items-center justify-between">
                <span>
                  <span className="font-medium text-primary">
                    Ready to create outreach?{" "}
                  </span>
                  Facility selected for outreach.
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setActiveTab("outreach")}
                >
                  Go to Outreach tab →
                </Button>
              </div>
            )}

            {matches.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground text-sm">
                No matches generated yet. Click &quot;Generate Matches&quot; to start.
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {matches.map((match) => (
                  <FacilityCard
                    key={match.id}
                    facility={match}
                    onSelectToggle={handleSelectFacility}
                    onOutreachPromptClick={() => setActiveTab("outreach")}
                  />
                ))}
              </div>
            )}

            {/* AC10: Re-match warning Sheet */}
            <Sheet
              open={rematchSheetOpen}
              onOpenChange={setRematchSheetOpen}
            >
              <SheetContent side="right" className="w-[400px]">
                <SheetHeader>
                  <SheetTitle>Regenerate Matches?</SheetTitle>
                  <SheetDescription>
                    <span className="flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                      Re-generating matches will clear your current selections.
                      This cannot be undone.
                    </span>
                  </SheetDescription>
                </SheetHeader>
                <div className="mt-6 flex gap-2">
                  <Button
                    onClick={() => handleGenerateMatches(true)}
                    disabled={isGeneratingMatches}
                    variant="destructive"
                    size="sm"
                  >
                    {isGeneratingMatches ? "Generating..." : "Yes, Regenerate"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRematchSheetOpen(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </SheetContent>
            </Sheet>
          </TabsContent>

          {/* Outreach tab — AC11 */}
          <TabsContent value="outreach" className="p-6 mt-0 space-y-4">
            <h2 className="text-base font-semibold">Outreach</h2>
            {outreachActions.length > 0 ? (
              <div className="space-y-4">
                {outreachActions.map((action) => (
                  <div
                    key={action.id}
                    className="rounded-md border p-4"
                  >
                    <DraftEditor
                      caseId={caseId}
                      templates={templates}
                      existingDraft={action}
                      userRole={userRole ?? undefined}
                      onSubmit={handleCreateOutreach}
                      onApprove={handleApproveOutreach}
                      onMarkSent={handleMarkSentOutreach}
                      onCancel={handleCancelOutreach}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No outreach communications yet. Use the form below to create one.</p>
            )}

            {/* New outreach draft form */}
            <div className="rounded-md border p-4">
              <DraftEditor
                caseId={caseId}
                templates={templates}
                userRole={userRole ?? undefined}
                onSubmit={handleCreateOutreach}
              />
            </div>
          </TabsContent>

          {/* Timeline tab */}
          <TabsContent value="timeline" className="p-6 mt-0">
            <ActivityTimeline events={timeline} />
          </TabsContent>

          {/* Audit tab — AC9: only visible/rendered for admin role */}
          {userRole === "admin" && (
            <TabsContent value="audit" className="p-6 mt-0">
              <h2 className="text-base font-semibold mb-4">Audit Log</h2>
              <ActivityTimeline events={auditEvents} />
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  )
}
