// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC11 — Outreach tab DraftEditor: create draft from template, edit subject/body, submit for approval, approve, mark sent, cancel; phone_manual/task bypass approval flow
"use client"

import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Send, Check, X, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type {
  OutreachChannel,
  OutreachApprovalStatus,
} from "@shared/types"

// Channels that bypass the draft → pending_approval → approved flow
// and are created directly at 'sent' status
// @forgeplan-spec: AC11 — phone_manual/task bypass approval flow
const DIRECT_SEND_CHANNELS: OutreachChannel[] = ["phone_manual", "task"]

export interface DraftTemplateOption {
  id: string
  template_name: string
  template_type: string
  subject_template?: string | null
  body_template: string
}

export interface ExistingDraft {
  id: string
  channel: OutreachChannel
  draft_subject?: string | null
  draft_body: string
  approval_status: OutreachApprovalStatus
}

export interface DraftEditorProps {
  caseId: string
  facilityId?: string
  templates: DraftTemplateOption[]
  existingDraft?: ExistingDraft | null
  userRole?: string
  onSubmit: (data: DraftFormData) => Promise<void>
  onApprove?: (draftId: string) => Promise<void>
  onMarkSent?: (draftId: string) => Promise<void>
  onCancel?: (draftId: string) => Promise<void>
  isLoading?: boolean
}

const draftSchema = z.object({
  template_id: z.string().optional(),
  channel: z.enum([
    "email",
    "phone_manual",
    "task",
    "sms",
    "voicemail_drop",
    "voice_ai",
  ]),
  draft_subject: z.string().optional(),
  draft_body: z.string().min(1, "Message body is required"),
})

export type DraftFormData = z.infer<typeof draftSchema>

const CHANNEL_LABELS: Record<OutreachChannel, string> = {
  email: "Email",
  phone_manual: "Phone (Manual)",
  task: "Task",
  sms: "SMS",
  voicemail_drop: "Voicemail Drop",
  voice_ai: "Voice AI",
}

const APPROVAL_STATUS_CONFIG: Record<
  OutreachApprovalStatus,
  { label: string; color: string }
> = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700" },
  pending_approval: {
    label: "Pending Approval",
    color: "bg-amber-100 text-amber-700",
  },
  approved: { label: "Approved", color: "bg-emerald-100 text-emerald-700" },
  sent: { label: "Sent", color: "bg-blue-100 text-blue-700" },
  canceled: { label: "Canceled", color: "bg-gray-100 text-gray-600" },
  failed: { label: "Failed", color: "bg-red-100 text-red-700" },
}

/**
 * DraftEditor handles the outreach draft workflow.
 *
 * For email/sms/voicemail_drop/voice_ai channels: draft → pending_approval → approved → sent
 * For phone_manual/task channels: created directly at sent (no approval step shown)
 *
 * AC11: phone_manual and task atomically advance case state without approval flow.
 */
export function DraftEditor({
  templates,
  existingDraft,
  userRole,
  onSubmit,
  onApprove,
  onMarkSent,
  onCancel,
  isLoading = false,
}: DraftEditorProps) {
  const [selectedTemplateId, setSelectedTemplateId] = React.useState<
    string | undefined
  >(undefined)
  const [error, setError] = React.useState<string | null>(null)

  const form = useForm<DraftFormData>({
    resolver: zodResolver(draftSchema),
    defaultValues: {
      channel: existingDraft?.channel ?? "email",
      draft_subject: existingDraft?.draft_subject ?? "",
      draft_body: existingDraft?.draft_body ?? "",
    },
  })

  const watchChannel = form.watch("channel") as OutreachChannel
  const isDirectSend = DIRECT_SEND_CHANNELS.includes(watchChannel)

  // When a template is selected, populate subject/body
  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplateId(templateId)
    const template = templates.find((t) => t.id === templateId)
    if (template) {
      if (template.subject_template) {
        form.setValue("draft_subject", template.subject_template)
      }
      form.setValue("draft_body", template.body_template)
    }
  }

  const handleSubmit = async (data: DraftFormData) => {
    try {
      setError(null)
      await onSubmit(data)
      form.reset()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit draft")
    }
  }

  // If we have an existing draft, show its status and action buttons
  if (existingDraft) {
    const statusConfig = APPROVAL_STATUS_CONFIG[existingDraft.approval_status]
    const existingIsDirectSend = DIRECT_SEND_CHANNELS.includes(
      existingDraft.channel
    )
    const canApprove =
      existingDraft.approval_status === "pending_approval" &&
      (userRole === "admin" || userRole === "manager")
    const canMarkSent = existingDraft.approval_status === "approved"
    const canCancel =
      existingDraft.approval_status !== "sent" &&
      existingDraft.approval_status !== "canceled"

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Outreach Draft</h3>
          <Badge
            variant="outline"
            className={cn("text-xs", statusConfig.color)}
          >
            {statusConfig.label}
          </Badge>
        </div>

        <div className="rounded-md border p-4 space-y-3 bg-muted/30">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Channel:</span>
            <span className="font-medium">
              {CHANNEL_LABELS[existingDraft.channel]}
            </span>
          </div>

          {existingDraft.draft_subject && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Subject</p>
              <p className="text-sm">{existingDraft.draft_subject}</p>
            </div>
          )}

          <div>
            <p className="text-xs text-muted-foreground mb-1">Message</p>
            <p className="text-sm whitespace-pre-wrap">
              {existingDraft.draft_body}
            </p>
          </div>
        </div>

        {/* AC11: Approval step only shown for non-phone_manual/task channels */}
        {!existingIsDirectSend && (
          <div className="flex flex-wrap gap-2">
            {existingDraft.approval_status === "draft" && (
              <Button
                size="sm"
                onClick={() =>
                  // F19: include draft_subject so it is not dropped on re-submit
                  onSubmit({
                    channel: existingDraft.channel,
                    draft_body: existingDraft.draft_body,
                    ...(existingDraft.draft_subject
                      ? { draft_subject: existingDraft.draft_subject }
                      : {}),
                  })
                }
                disabled={isLoading}
              >
                <Send className="h-3 w-3 mr-1" />
                Submit for Approval
              </Button>
            )}

            {canApprove && (
              <Button
                size="sm"
                variant="default"
                onClick={() => onApprove?.(existingDraft.id)}
                disabled={isLoading}
              >
                <Check className="h-3 w-3 mr-1" />
                Approve
              </Button>
            )}

            {canMarkSent && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onMarkSent?.(existingDraft.id)}
                disabled={isLoading}
              >
                <Send className="h-3 w-3 mr-1" />
                Mark Sent
              </Button>
            )}

            {canCancel && (
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => onCancel?.(existingDraft.id)}
                disabled={isLoading}
              >
                <X className="h-3 w-3 mr-1" />
                Cancel
              </Button>
            )}
          </div>
        )}

        {/* phone_manual/task: no approval step, just shows sent status */}
        {existingIsDirectSend && existingDraft.approval_status === "sent" && (
          <p className="text-xs text-emerald-600 font-medium flex items-center gap-1">
            <Check className="h-3 w-3" />
            {existingDraft.channel === "phone_manual"
              ? "Call logged"
              : "Task created"}
          </p>
        )}
      </div>
    )
  }

  // New draft form
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">New Outreach</h3>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {/* Channel selector */}
        <div className="space-y-1.5">
          <Label htmlFor="channel">Channel</Label>
          <Select
            value={watchChannel}
            onValueChange={(val) =>
              form.setValue("channel", val as OutreachChannel)
            }
          >
            <SelectTrigger id="channel">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Template selector */}
        {templates.length > 0 && (
          <div className="space-y-1.5">
            <Label>Template (optional)</Label>
            <Select
              value={selectedTemplateId}
              onValueChange={handleTemplateSelect}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a template..." />
              </SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.template_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Subject (email only) */}
        {watchChannel === "email" && (
          <div className="space-y-1.5">
            <Label htmlFor="draft_subject">Subject</Label>
            <Input
              id="draft_subject"
              placeholder="Email subject..."
              {...form.register("draft_subject")}
            />
          </div>
        )}

        {/* Body */}
        <div className="space-y-1.5">
          <Label htmlFor="draft_body">Message</Label>
          <Textarea
            id="draft_body"
            rows={6}
            placeholder="Enter message..."
            {...form.register("draft_body")}
          />
          {form.formState.errors.draft_body && (
            <p className="text-xs text-destructive">
              {form.formState.errors.draft_body.message}
            </p>
          )}
        </div>

        {/* AC11: For phone_manual/task — button says "Log" not "Submit for Approval" */}
        <div className="flex gap-2">
          <Button
            type="submit"
            size="sm"
            disabled={isLoading || form.formState.isSubmitting}
          >
            <Send className="h-3 w-3 mr-1" />
            {isDirectSend ? "Log" : "Submit for Approval"}
          </Button>
        </div>

        {isDirectSend && (
          <p className="text-xs text-muted-foreground">
            {watchChannel === "phone_manual"
              ? "Phone calls are logged directly without an approval step."
              : "Tasks are created directly without an approval step."}
          </p>
        )}
      </form>
    </div>
  )
}

export default DraftEditor
