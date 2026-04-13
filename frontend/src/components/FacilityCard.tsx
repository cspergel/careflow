// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC10 — Facility cards show name, type, distance, scores, is_recommended badge, blocker chips, explanation text
"use client"

import * as React from "react"
import { MapPin, Star, AlertTriangle, CheckCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { cn } from "@/lib/utils"

// F17: FacilityMatchResponse from backend only guarantees facility_id on the match record.
// facility_name, facility_type, distance_miles may not be present — make them optional
// so the card degrades gracefully without a separate facility lookup.
export interface FacilityCardData {
  id: string
  facility_id: string
  facility_name?: string | null
  facility_type?: "snf" | "irf" | "ltach" | null
  distance_miles?: number | null
  overall_score: number
  payer_fit_score?: number | null
  clinical_fit_score?: number | null
  geography_score?: number | null
  preference_score?: number | null
  is_recommended: boolean
  selected_for_outreach: boolean
  blockers_json?: Record<string, string>[] | null
  explanation_text?: string | null
  rank_order: number
}

interface FacilityCardProps {
  facility: FacilityCardData
  onSelectToggle?: (facilityMatchId: string, selected: boolean) => void
  onOutreachPromptClick?: () => void
  isUpdating?: boolean
}

const FACILITY_TYPE_LABELS: Record<Exclude<FacilityCardData["facility_type"], null | undefined>, string> =
  {
    snf: "Skilled Nursing Facility",
    irf: "Inpatient Rehab Facility",
    ltach: "Long-Term Acute Care Hospital",
  }

function ScorePill({
  label,
  score,
}: {
  label: string
  score?: number | null
}) {
  if (score == null) return null
  const pct = Math.round(score * 100)
  const colorClass =
    pct >= 80
      ? "bg-emerald-100 text-emerald-700"
      : pct >= 60
        ? "bg-amber-100 text-amber-700"
        : "bg-red-100 text-red-700"
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        colorClass
      )}
    >
      {label}: {pct}%
    </span>
  )
}

/**
 * FacilityCard displays a single facility match result for the Facility Matches tab.
 * Shows name, type, scores, is_recommended badge, blocker chips, explanation text,
 * and Select For Outreach toggle.
 */
export function FacilityCard({
  facility,
  onSelectToggle,
  onOutreachPromptClick,
  isUpdating = false,
}: FacilityCardProps) {
  const hasBlockers =
    facility.blockers_json && facility.blockers_json.length > 0

  return (
    <Card
      className={cn(
        "relative transition-all",
        facility.selected_for_outreach &&
          "ring-2 ring-primary border-primary",
        hasBlockers && "opacity-75"
      )}
    >
      {/* Rank badge */}
      <div className="absolute -left-3 -top-3 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground shadow">
        {facility.rank_order}
      </div>

      <CardHeader className="pb-2 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-sm truncate">
                {/* F17: facility_name may be absent; fall back to facility_id */}
                {facility.facility_name ?? `Facility ${facility.facility_id.slice(0, 8)}…`}
              </h3>
              {facility.is_recommended && (
                <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 text-xs">
                  <Star className="h-3 w-3 mr-1 fill-emerald-600" />
                  Recommended
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
              {facility.facility_type && (
                <span>{FACILITY_TYPE_LABELS[facility.facility_type]}</span>
              )}
              {facility.distance_miles != null && (
                <span className="flex items-center gap-0.5">
                  <MapPin className="h-3 w-3" />
                  {facility.distance_miles.toFixed(1)} mi
                </span>
              )}
            </div>
          </div>

          {/* Overall score */}
          <div className="flex flex-col items-center shrink-0">
            <span className="text-2xl font-bold text-primary">
              {Math.round(facility.overall_score * 100)}
            </span>
            <span className="text-xs text-muted-foreground">score</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Score pills */}
        <div className="flex flex-wrap gap-1">
          <ScorePill label="Payer" score={facility.payer_fit_score} />
          <ScorePill label="Clinical" score={facility.clinical_fit_score} />
          <ScorePill label="Geography" score={facility.geography_score} />
          <ScorePill label="Preference" score={facility.preference_score} />
        </div>

        {/* Explanation text */}
        {facility.explanation_text && (
          <p className="text-xs text-muted-foreground leading-relaxed">
            {facility.explanation_text}
          </p>
        )}

        {/* Blocker chips */}
        {hasBlockers && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-destructive flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Blockers
            </p>
            <div className="flex flex-wrap gap-1">
              {(facility.blockers_json as Record<string, string>[]).map(
                (blocker, i) => (
                  <Badge
                    key={i}
                    variant="outline"
                    className="text-xs bg-red-50 text-red-700 border-red-200"
                  >
                    {blocker.reason ?? blocker.field ?? JSON.stringify(blocker)}
                  </Badge>
                )
              )}
            </div>
          </div>
        )}

        {/* Select for outreach toggle */}
        {!hasBlockers && (
          <div className="flex items-center justify-between pt-1">
            <Button
              size="sm"
              variant={facility.selected_for_outreach ? "default" : "outline"}
              onClick={() =>
                onSelectToggle?.(facility.id, !facility.selected_for_outreach)
              }
              disabled={isUpdating}
              className="gap-1"
            >
              {facility.selected_for_outreach ? (
                <>
                  <CheckCircle className="h-3 w-3" />
                  Selected for Outreach
                </>
              ) : (
                "Select for Outreach"
              )}
            </Button>
          </div>
        )}

        {/* AC10: Contextual prompt after selecting */}
        {facility.selected_for_outreach && onOutreachPromptClick && (
          <div className="rounded-md bg-primary/5 border border-primary/20 px-3 py-2 text-xs">
            <span className="text-primary font-medium">
              Ready to create outreach?{" "}
            </span>
            <button
              className="text-primary underline underline-offset-2 hover:no-underline"
              onClick={onOutreachPromptClick}
            >
              Go to Outreach tab →
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default FacilityCard
