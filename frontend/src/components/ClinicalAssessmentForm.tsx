// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC12 — 20+ field react-hook-form v7 + Zod form; inline per-field validation errors
"use client"

import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

// @forgeplan-spec: AC12 — field names match backend ORM ClinicalAssessment and shared ClinicalAssessment type
const clinicalAssessmentSchema = z.object({
  // Level of care
  recommended_level_of_care: z.enum(["snf", "irf", "ltach"], {
    required_error: "Level of care is required",
  }),
  confidence_level: z.string().optional(),

  // Clinical narrative
  clinical_summary: z.string().optional(),
  rehab_tolerance: z.string().optional(),
  mobility_status: z.string().optional(),

  // Respiratory
  accepts_oxygen_therapy: z.boolean().default(false),
  accepts_trach: z.boolean().default(false),
  accepts_vent: z.boolean().default(false),

  // Dialysis (separate flags — no dialysis_type select)
  accepts_hd: z.boolean().default(false),
  in_house_hemodialysis: z.boolean().default(false),
  accepts_peritoneal_dialysis: z.boolean().default(false),

  // Wound/IV
  accepts_wound_vac: z.boolean().default(false),
  accepts_iv_antibiotics: z.boolean().default(false),
  accepts_tpn: z.boolean().default(false),

  // Behavioral/Special
  accepts_isolation_cases: z.boolean().default(false),
  psych_behavior_flags: z.string().optional(),
  accepts_behavioral_complexity: z.boolean().default(false),
  accepts_bariatric: z.boolean().default(false),
  accepts_memory_care: z.boolean().default(false),

  // Additional clinical notes
  special_equipment_needs: z.string().optional(),
  barriers_to_placement: z.string().optional(),
  payer_notes: z.string().optional(),
  family_preference_notes: z.string().optional(),

  // Status
  review_status: z.enum(["draft", "finalized"]).default("draft"),
})

export type ClinicalAssessmentFormData = z.infer<typeof clinicalAssessmentSchema>

export interface ClinicalAssessmentFormProps {
  defaultValues?: Partial<ClinicalAssessmentFormData>
  onSubmit: (data: ClinicalAssessmentFormData) => Promise<void>
  isLoading?: boolean
  readOnly?: boolean
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="pt-2">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <Separator className="mt-1" />
    </div>
  )
}

function BooleanField({
  form,
  name,
  label,
  disabled,
}: {
  form: ReturnType<typeof useForm<ClinicalAssessmentFormData>>
  name: keyof ClinicalAssessmentFormData
  label: string
  disabled?: boolean
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center gap-2 space-y-0">
          <FormControl>
            <Checkbox
              checked={field.value as boolean}
              onCheckedChange={field.onChange}
              disabled={disabled}
              id={String(name)}
            />
          </FormControl>
          <FormLabel
            htmlFor={String(name)}
            className={cn("font-normal text-sm cursor-pointer", disabled && "opacity-50")}
          >
            {label}
          </FormLabel>
        </FormItem>
      )}
    />
  )
}

/**
 * ClinicalAssessmentForm — 20+ field react-hook-form v7 + Zod form.
 * Inline per-field validation errors.
 * Field names match backend ClinicalAssessment ORM (accepts_* convention).
 */
export function ClinicalAssessmentForm({
  defaultValues,
  onSubmit,
  isLoading = false,
  readOnly = false,
}: ClinicalAssessmentFormProps) {
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  // F21: Track which button was clicked to avoid stale review_status on error
  const [submittingAs, setSubmittingAs] = React.useState<"draft" | "finalized" | null>(null)

  const form = useForm<ClinicalAssessmentFormData>({
    resolver: zodResolver(clinicalAssessmentSchema),
    defaultValues: {
      recommended_level_of_care: defaultValues?.recommended_level_of_care,
      confidence_level: defaultValues?.confidence_level ?? "",
      clinical_summary: defaultValues?.clinical_summary ?? "",
      rehab_tolerance: defaultValues?.rehab_tolerance ?? "",
      mobility_status: defaultValues?.mobility_status ?? "",
      accepts_oxygen_therapy: defaultValues?.accepts_oxygen_therapy ?? false,
      accepts_trach: defaultValues?.accepts_trach ?? false,
      accepts_vent: defaultValues?.accepts_vent ?? false,
      accepts_hd: defaultValues?.accepts_hd ?? false,
      in_house_hemodialysis: defaultValues?.in_house_hemodialysis ?? false,
      accepts_peritoneal_dialysis: defaultValues?.accepts_peritoneal_dialysis ?? false,
      accepts_wound_vac: defaultValues?.accepts_wound_vac ?? false,
      accepts_iv_antibiotics: defaultValues?.accepts_iv_antibiotics ?? false,
      accepts_tpn: defaultValues?.accepts_tpn ?? false,
      accepts_isolation_cases: defaultValues?.accepts_isolation_cases ?? false,
      psych_behavior_flags: defaultValues?.psych_behavior_flags ?? "",
      accepts_behavioral_complexity: defaultValues?.accepts_behavioral_complexity ?? false,
      accepts_bariatric: defaultValues?.accepts_bariatric ?? false,
      accepts_memory_care: defaultValues?.accepts_memory_care ?? false,
      special_equipment_needs: defaultValues?.special_equipment_needs ?? "",
      barriers_to_placement: defaultValues?.barriers_to_placement ?? "",
      payer_notes: defaultValues?.payer_notes ?? "",
      family_preference_notes: defaultValues?.family_preference_notes ?? "",
      review_status: defaultValues?.review_status ?? "draft",
    },
  })

  const acceptsHd = form.watch("accepts_hd")

  const handleSubmit = async (data: ClinicalAssessmentFormData) => {
    try {
      setSubmitError(null)
      await onSubmit(data)
      setSubmittingAs(null)
    } catch (err) {
      // F21: Reset submittingAs so the button state is not stuck after a failed submit
      setSubmittingAs(null)
      setSubmitError(
        err instanceof Error ? err.message : "Failed to save assessment"
      )
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(handleSubmit)}
        className="space-y-5"
        aria-label="Clinical Assessment Form"
      >
        {submitError && (
          <div className="rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-sm text-destructive">
            {submitError}
          </div>
        )}

        {/* ─── Level of Care ─────────────────────────────────── */}
        <SectionHeader title="Level of Care Recommendation" />

        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="recommended_level_of_care"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Recommended Level of Care *</FormLabel>
                <Select
                  value={field.value}
                  onValueChange={field.onChange}
                  disabled={readOnly}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="snf">SNF (Skilled Nursing)</SelectItem>
                    <SelectItem value="irf">IRF (Inpatient Rehab)</SelectItem>
                    <SelectItem value="ltach">LTACH (Long-Term Acute Care)</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="confidence_level"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confidence Level</FormLabel>
                <Select
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  disabled={readOnly}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="moderate">Moderate</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* ─── Clinical Narrative ────────────────────────────── */}
        <SectionHeader title="Clinical Summary" />

        <FormField
          control={form.control}
          name="clinical_summary"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Clinical Summary</FormLabel>
              <FormControl>
                <Textarea
                  rows={3}
                  placeholder="Summarize the patient's clinical presentation..."
                  disabled={readOnly}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="rehab_tolerance"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Rehab Tolerance</FormLabel>
                <Select
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  disabled={readOnly}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="good">Good (3+ hrs/day)</SelectItem>
                    <SelectItem value="fair">Fair (1-3 hrs/day)</SelectItem>
                    <SelectItem value="poor">Poor (&lt;1 hr/day)</SelectItem>
                    <SelectItem value="not_applicable">Not Applicable</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="mobility_status"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Mobility Status</FormLabel>
                <Select
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  disabled={readOnly}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="ambulatory">Ambulatory</SelectItem>
                    <SelectItem value="ambulatory_assist">Ambulatory w/ Assist</SelectItem>
                    <SelectItem value="wheelchair">Wheelchair</SelectItem>
                    <SelectItem value="bedbound">Bedbound</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* ─── Respiratory Needs ─────────────────────────────── */}
        <SectionHeader title="Respiratory Needs" />

        <div className="grid grid-cols-3 gap-3">
          <BooleanField form={form} name="accepts_oxygen_therapy" label="Oxygen Therapy" disabled={readOnly} />
          <BooleanField form={form} name="accepts_trach" label="Tracheostomy" disabled={readOnly} />
          <BooleanField form={form} name="accepts_vent" label="Ventilator" disabled={readOnly} />
        </div>

        {/* ─── Dialysis ──────────────────────────────────────── */}
        <SectionHeader title="Dialysis" />

        <div className="space-y-3">
          <BooleanField form={form} name="accepts_hd" label="Hemodialysis (HD)" disabled={readOnly} />

          {acceptsHd && (
            <BooleanField
              form={form}
              name="in_house_hemodialysis"
              label="In-House Hemodialysis Required"
              disabled={readOnly}
            />
          )}

          <BooleanField form={form} name="accepts_peritoneal_dialysis" label="Peritoneal Dialysis" disabled={readOnly} />
        </div>

        {/* ─── Wound / IV Needs ─────────────────────────────── */}
        <SectionHeader title="Wound & IV Needs" />

        <div className="grid grid-cols-3 gap-3">
          <BooleanField form={form} name="accepts_wound_vac" label="Wound VAC" disabled={readOnly} />
          <BooleanField form={form} name="accepts_iv_antibiotics" label="IV Antibiotics" disabled={readOnly} />
          <BooleanField form={form} name="accepts_tpn" label="TPN" disabled={readOnly} />
        </div>

        {/* ─── Behavioral / Special ─────────────────────────── */}
        <SectionHeader title="Behavioral & Special Needs" />

        <div className="grid grid-cols-2 gap-3">
          <BooleanField form={form} name="accepts_isolation_cases" label="Isolation Precautions" disabled={readOnly} />
          <BooleanField form={form} name="accepts_behavioral_complexity" label="Behavioral Complexity" disabled={readOnly} />
          <BooleanField form={form} name="accepts_bariatric" label="Bariatric Needs" disabled={readOnly} />
          <BooleanField form={form} name="accepts_memory_care" label="Memory Care" disabled={readOnly} />
        </div>

        <FormField
          control={form.control}
          name="psych_behavior_flags"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Psych / Behavior Notes</FormLabel>
              <FormControl>
                <Textarea
                  rows={2}
                  placeholder="Narrative notes about behavioral complexity..."
                  disabled={readOnly}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* ─── Additional Notes ─────────────────────────────── */}
        <SectionHeader title="Additional Notes" />

        <div className="space-y-4">
          <FormField
            control={form.control}
            name="special_equipment_needs"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Special Equipment Needs</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g., hospital bed, hoyer lift..."
                    disabled={readOnly}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="barriers_to_placement"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Barriers to Placement</FormLabel>
                <FormControl>
                  <Textarea
                    rows={2}
                    placeholder="Describe any known barriers..."
                    disabled={readOnly}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="payer_notes"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Payer Notes</FormLabel>
                <FormControl>
                  <Textarea
                    rows={2}
                    placeholder="Insurance-specific notes..."
                    disabled={readOnly}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="family_preference_notes"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Family Preference Notes</FormLabel>
                <FormControl>
                  <Textarea
                    rows={2}
                    placeholder="Family location preferences, facility requests..."
                    disabled={readOnly}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* ─── Submit actions ───────────────────────────────── */}
        {/* F21: Use submittingAs to track which button triggered submit, reset on error */}
        {!readOnly && (
          <div className="flex gap-2 pt-2">
            <Button
              type="submit"
              size="sm"
              disabled={isLoading || submittingAs !== null}
              onClick={() => {
                setSubmittingAs("draft")
                form.setValue("review_status", "draft")
              }}
            >
              {submittingAs === "draft" ? "Saving..." : "Save Draft"}
            </Button>
            <Button
              type="submit"
              size="sm"
              variant="default"
              disabled={isLoading || submittingAs !== null}
              onClick={() => {
                setSubmittingAs("finalized")
                form.setValue("review_status", "finalized")
              }}
            >
              {submittingAs === "finalized" ? "Finalizing..." : "Finalize Assessment"}
            </Button>
          </div>
        )}
      </form>
    </Form>
  )
}

export default ClinicalAssessmentForm
