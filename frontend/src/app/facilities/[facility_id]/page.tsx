// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Facility detail with 4 tabs (Overview, Capabilities, Insurance, Contacts)
"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { ArrowLeft, CheckCircle, XCircle, Phone, Mail } from "lucide-react"
import { parseAsString, useQueryState } from "nuqs"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { apiClient, ApiError } from "@/client"
import { formatDate } from "@/lib/utils"
import type {
  Facility,
  FacilityCapabilities,
  FacilityInsuranceRule,
  FacilityContact,
} from "@shared/types"

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-sm">{label}</span>
      {value ? (
        <CheckCircle className="h-4 w-4 text-emerald-500" />
      ) : (
        <XCircle className="h-4 w-4 text-muted-foreground/30" />
      )}
    </div>
  )
}

export default function FacilityDetailPage() {
  const params = useParams()
  const facilityId = params.facility_id as string

  const [activeTab, setActiveTab] = useQueryState(
    "tab",
    parseAsString.withDefault("overview")
  )

  const [facility, setFacility] = React.useState<Facility | null>(null)
  const [capabilities, setCapabilities] =
    React.useState<FacilityCapabilities | null>(null)
  const [insuranceRules, setInsuranceRules] = React.useState<
    FacilityInsuranceRule[]
  >([])
  const [contacts, setContacts] = React.useState<FacilityContact[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [pageError, setPageError] = React.useState<string | null>(null)

  React.useEffect(() => {
    loadFacilityData()
  }, [facilityId])

  const loadFacilityData = async () => {
    setIsLoading(true)
    setPageError(null)
    try {
      const [facilityData, capData, insuranceData, contactData] =
        await Promise.allSettled([
          apiClient.fetch<Facility>(`/api/v1/facilities/${facilityId}`),
          apiClient.fetch<FacilityCapabilities>(
            `/api/v1/facilities/${facilityId}/capabilities`
          ),
          apiClient.fetch<{ items: FacilityInsuranceRule[] }>(
            `/api/v1/facilities/${facilityId}/insurance-rules`
          ),
          apiClient.fetch<{ items: FacilityContact[] }>(
            `/api/v1/facilities/${facilityId}/contacts`
          ),
        ])

      if (facilityData.status === "fulfilled") setFacility(facilityData.value)
      else
        setPageError(
          facilityData.reason instanceof ApiError
            ? facilityData.reason.message
            : "Failed to load facility"
        )

      if (capData.status === "fulfilled") setCapabilities(capData.value)
      if (insuranceData.status === "fulfilled")
        setInsuranceRules(insuranceData.value.items)
      if (contactData.status === "fulfilled")
        setContacts(contactData.value.items)
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="animate-pulse p-6 space-y-4">
        {/* Header skeleton */}
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="bg-gray-200 rounded h-6 w-48" />
            <div className="bg-gray-200 rounded h-4 w-64" />
          </div>
          <div className="bg-gray-200 rounded h-8 w-24" />
        </div>
        {/* Tab bar skeleton */}
        <div className="flex gap-2 border-b pb-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-gray-200 rounded h-8 w-24" />
          ))}
        </div>
        {/* Tab content skeleton */}
        <div className="space-y-3 pt-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="rounded-md border px-4 py-3">
              <div className="bg-gray-200 rounded h-4 w-40 mb-2" />
              <div className="bg-gray-200 rounded h-3 w-56" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (pageError || !facility) {
    return (
      <div className="p-6">
        <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {pageError ?? "Facility not found"}
        </div>
        <Button className="mt-4" variant="outline" asChild>
          <Link href="/facilities">Back to Facilities</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-3 mb-2">
          <Button variant="ghost" size="sm" asChild className="-ml-2">
            <Link href="/facilities">
              <ArrowLeft className="h-4 w-4 mr-1" />
              Facilities
            </Link>
          </Button>
        </div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold">{facility.facility_name}</h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground flex-wrap">
              <Badge variant="outline" className="text-xs">
                {facility.facility_type.toUpperCase()}
              </Badge>
              {facility.city && facility.state && (
                <span>
                  {facility.city}, {facility.state}
                </span>
              )}
            </div>
          </div>
          <Badge
            variant="outline"
            className={
              facility.active_status
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-gray-50 text-gray-500 border-gray-200"
            }
          >
            {facility.active_status ? "Active" : "Inactive"}
          </Badge>
        </div>
      </div>

      {/* 4-tab layout */}
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex-1 flex flex-col overflow-hidden"
      >
        <div className="border-b px-6">
          <TabsList className="h-auto p-0 bg-transparent rounded-none border-0">
            {["overview", "capabilities", "insurance", "contacts"].map(
              (tab) => (
                <TabsTrigger
                  key={tab}
                  value={tab}
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent capitalize px-4 py-2.5 text-sm"
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </TabsTrigger>
              )
            )}
          </TabsList>
        </div>

        <div className="flex-1 overflow-auto">
          {/* Overview tab */}
          <TabsContent value="overview" className="p-6 mt-0 space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                ["Address", facility.address_line_1 ?? "—"],
                ["City", facility.city ?? "—"],
                ["State", facility.state ?? "—"],
                ["ZIP", facility.zip ?? "—"],
                ["County", facility.county ?? "—"],
                ["Type", facility.facility_type.toUpperCase()],
                ["Status", facility.active_status ? "Active" : "Inactive"],
                ["Added", formatDate(facility.created_at)],
                ["Updated", formatDate(facility.updated_at)],
              ].map(([label, value]) => (
                <div key={label} className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-sm font-medium">{value}</p>
                </div>
              ))}
            </div>
            {facility.notes && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Notes</p>
                <p className="text-sm">{facility.notes}</p>
              </div>
            )}
          </TabsContent>

          {/* Capabilities tab */}
          <TabsContent value="capabilities" className="p-6 mt-0">
            {capabilities ? (
              <div className="space-y-4 max-w-md">
                <div>
                  <h3 className="text-sm font-semibold mb-2">Care Types</h3>
                  <BoolRow label="Accepts SNF" value={capabilities.accepts_snf} />
                  <BoolRow label="Accepts IRF" value={capabilities.accepts_irf} />
                  <BoolRow label="Accepts LTACH" value={capabilities.accepts_ltach} />
                </div>
                <Separator />
                <div>
                  <h3 className="text-sm font-semibold mb-2">Clinical Capabilities</h3>
                  <BoolRow label="Tracheostomy" value={capabilities.accepts_trach} />
                  <BoolRow label="Ventilator" value={capabilities.accepts_vent} />
                  <BoolRow label="Hemodialysis" value={capabilities.accepts_hd} />
                  <BoolRow label="In-House HD" value={capabilities.in_house_hemodialysis} />
                  <BoolRow label="Peritoneal Dialysis" value={capabilities.accepts_peritoneal_dialysis} />
                  <BoolRow label="Wound VAC" value={capabilities.accepts_wound_vac} />
                  <BoolRow label="IV Antibiotics" value={capabilities.accepts_iv_antibiotics} />
                  <BoolRow label="TPN" value={capabilities.accepts_tpn} />
                  <BoolRow label="Bariatric" value={capabilities.accepts_bariatric} />
                  <BoolRow label="Behavioral Complexity" value={capabilities.accepts_behavioral_complexity} />
                  <BoolRow label="Memory Care" value={capabilities.accepts_memory_care} />
                  <BoolRow label="Isolation Cases" value={capabilities.accepts_isolation_cases} />
                  <BoolRow label="Oxygen Therapy" value={capabilities.accepts_oxygen_therapy} />
                </div>
                <Separator />
                <div>
                  <h3 className="text-sm font-semibold mb-2">Admissions</h3>
                  <BoolRow label="Weekend Admissions" value={capabilities.weekend_admissions} />
                  <BoolRow label="After-Hours Admissions" value={capabilities.after_hours_admissions} />
                </div>
                {capabilities.last_verified_at && (
                  <p className="text-xs text-muted-foreground">
                    Last verified: {formatDate(capabilities.last_verified_at)}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No capabilities data available.
              </p>
            )}
          </TabsContent>

          {/* Insurance tab */}
          <TabsContent value="insurance" className="p-6 mt-0">
            {insuranceRules.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No insurance rules configured.
              </p>
            ) : (
              <div className="space-y-2">
                {insuranceRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="flex items-center justify-between rounded-md border px-4 py-3"
                  >
                    <span className="text-sm font-medium">{rule.payer_name}</span>
                    <Badge
                      variant="outline"
                      className={
                        rule.accepted_status === "accepted"
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200 text-xs"
                          : rule.accepted_status === "conditional"
                            ? "bg-amber-50 text-amber-700 border-amber-200 text-xs"
                            : "bg-red-50 text-red-700 border-red-200 text-xs"
                      }
                    >
                      {rule.accepted_status.replace("_", " ")}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Contacts tab */}
          <TabsContent value="contacts" className="p-6 mt-0">
            {contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No contacts on file.
              </p>
            ) : (
              <div className="space-y-3">
                {contacts.map((contact) => (
                  <div key={contact.id} className="rounded-md border p-4 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">
                        {contact.contact_name}
                      </span>
                      {contact.is_primary && (
                        <Badge variant="secondary" className="text-xs">Primary</Badge>
                      )}
                    </div>
                    {contact.title && (
                      <p className="text-xs text-muted-foreground">{contact.title}</p>
                    )}
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      {contact.phone && (
                        <span className="flex items-center gap-1">
                          <Phone className="h-3 w-3" />
                          {contact.phone}
                        </span>
                      )}
                      {contact.email && (
                        <span className="flex items-center gap-1">
                          <Mail className="h-3 w-3" />
                          {contact.email}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
