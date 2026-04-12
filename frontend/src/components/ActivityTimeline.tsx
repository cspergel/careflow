// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC9 — Timeline tab from GET /api/v1/cases/{id}/timeline
"use client"

import * as React from "react"
import {
  ArrowRightLeft,
  PlusCircle,
  Stethoscope,
  Mail,
  Building2,
  ClipboardCheck,
  CheckCircle,
  Lock,
  Pin,
} from "lucide-react"
import { formatDateTime } from "@/lib/utils"
import { cn } from "@/lib/utils"

export interface TimelineEvent {
  id: string
  event_type: string
  entity_type: string
  old_value_json?: Record<string, unknown> | null
  new_value_json?: Record<string, unknown> | null
  actor_user_id?: string | null
  actor_name?: string | null
  created_at: string
}

interface ActivityTimelineProps {
  events: TimelineEvent[]
  isLoading?: boolean
}

function eventIcon(eventType: string): React.ReactElement {
  if (eventType.includes("status_changed")) return <ArrowRightLeft className="h-3 w-3" />
  if (eventType.includes("created")) return <PlusCircle className="h-3 w-3" />
  if (eventType.includes("assessment")) return <Stethoscope className="h-3 w-3" />
  if (eventType.includes("outreach")) return <Mail className="h-3 w-3" />
  if (eventType.includes("match")) return <Building2 className="h-3 w-3" />
  if (eventType.includes("outcome")) return <ClipboardCheck className="h-3 w-3" />
  if (eventType.includes("placed")) return <CheckCircle className="h-3 w-3" />
  if (eventType.includes("closed")) return <Lock className="h-3 w-3" />
  return <Pin className="h-3 w-3" />
}

function formatEventType(eventType: string): string {
  return eventType
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

/**
 * ActivityTimeline renders chronological case events from the audit/timeline API.
 */
export function ActivityTimeline({
  events,
  isLoading = false,
}: ActivityTimelineProps) {
  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex gap-3">
            <div className="h-8 w-8 rounded-full bg-muted" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-48 rounded bg-muted" />
              <div className="h-3 w-24 rounded bg-muted" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        No timeline events found.
      </div>
    )
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-4 top-2 bottom-2 w-px bg-border" />

      <ol className="space-y-4">
        {events.map((event, index) => (
          <li key={event.id} className="flex gap-3 relative">
            {/* Icon */}
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-background text-sm z-10",
                index === 0 ? "ring-2 ring-primary ring-offset-1" : ""
              )}
            >
              {eventIcon(event.event_type)}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0 pt-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">
                    {formatEventType(event.event_type)}
                  </p>
                  {event.actor_name && (
                    <p className="text-xs text-muted-foreground">
                      by {event.actor_name}
                    </p>
                  )}
                  {!event.actor_name && event.actor_user_id && (
                    <p className="text-xs text-muted-foreground">
                      by user {event.actor_user_id.slice(0, 8)}…
                    </p>
                  )}
                  {!event.actor_name && !event.actor_user_id && (
                    <p className="text-xs text-muted-foreground">
                      System action
                    </p>
                  )}
                </div>
                <time className="text-xs text-muted-foreground shrink-0">
                  {formatDateTime(event.created_at)}
                </time>
              </div>

              {/* Status change detail */}
              {event.event_type === "status_changed" &&
                event.old_value_json &&
                event.new_value_json && (
                  <div className="mt-1 flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">
                      {String(
                        (event.old_value_json as { status?: string }).status ??
                          ""
                      ).replace(/_/g, " ")}
                    </span>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium text-foreground">
                      {String(
                        (event.new_value_json as { status?: string }).status ??
                          ""
                      ).replace(/_/g, " ")}
                    </span>
                  </div>
                )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default ActivityTimeline
