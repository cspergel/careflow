// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC15 — Admin Settings: 4 tabs (Users, Templates, Import Jobs, Org Settings); only admin can access /admin
"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { parseAsString, useQueryState } from "nuqs"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatDate, formatDateTime } from "@/lib/utils"
import { apiClient, ApiError } from "@/client"
import { createClient } from "@/lib/supabase/client"
import type { User, OutreachTemplate, ImportJob } from "@shared/types"

function useAdminGuard() {
  const router = useRouter()
  const [isAdmin, setIsAdmin] = React.useState<boolean | null>(null)

  React.useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) {
        router.push("/login")
        return
      }
      const { data } = await supabase
        .from("users")
        .select("role_key")
        .eq("id", user.id)
        .single()

      if (!data || data.role_key !== "admin") {
        router.push("/dashboard")
      } else {
        setIsAdmin(true)
      }
    })
  }, [router])

  return isAdmin
}

// Users Tab
function UsersTab() {
  const [users, setUsers] = React.useState<User[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    apiClient
      .fetch<{ items: User[] }>("/api/v1/admin/users")
      .then((data) => setUsers(data.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load users")
      )
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) return (
    <div className="animate-pulse space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex items-center justify-between rounded-md border px-4 py-3">
          <div className="space-y-2">
            <div className="bg-gray-200 rounded h-4 w-36" />
            <div className="bg-gray-200 rounded h-3 w-48" />
          </div>
          <div className="flex gap-2">
            <div className="bg-gray-200 rounded h-5 w-16" />
            <div className="bg-gray-200 rounded h-5 w-14" />
          </div>
        </div>
      ))}
    </div>
  )
  if (error) return <p className="text-sm text-destructive">{error}</p>

  return (
    <div className="space-y-3">
      {users.map((user) => (
        <div
          key={user.id}
          className="flex items-center justify-between rounded-md border px-4 py-3"
        >
          <div>
            <p className="text-sm font-medium">{user.full_name}</p>
            <p className="text-xs text-muted-foreground">{user.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs capitalize">
              {user.role_key.replace("_", " ")}
            </Badge>
            <Badge
              variant="outline"
              className={
                user.status === "active"
                  ? "text-xs bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "text-xs bg-gray-50 text-gray-500 border-gray-200"
              }
            >
              {user.status}
            </Badge>
          </div>
        </div>
      ))}
      {users.length === 0 && <p className="text-sm text-muted-foreground py-4">No users found.</p>}
    </div>
  )
}

// Templates Tab
function TemplatesTab() {
  const [templates, setTemplates] = React.useState<OutreachTemplate[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    // F5: correct route is /api/v1/templates/outreach
    apiClient
      .fetch<{ items: OutreachTemplate[] }>("/api/v1/templates/outreach")
      .then((data) => setTemplates(data.items))
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Failed to load templates"
        )
      )
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) return (
    <div className="animate-pulse space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="rounded-md border p-4">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="bg-gray-200 rounded h-4 w-40" />
              <div className="bg-gray-200 rounded h-3 w-24" />
            </div>
            <div className="bg-gray-200 rounded h-5 w-14" />
          </div>
        </div>
      ))}
    </div>
  )
  if (error) return <p className="text-sm text-destructive">{error}</p>

  return (
    <div className="space-y-3">
      {templates.map((template) => (
        <div key={template.id} className="rounded-md border p-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium">{template.template_name}</p>
              <p className="text-xs text-muted-foreground mt-0.5 capitalize">
                {template.template_type.replace("_", " ")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={
                  template.recipient_type === "patient_family"
                    ? "text-xs bg-violet-50 text-violet-700 border-violet-200"
                    : "text-xs bg-blue-50 text-blue-700 border-blue-200"
                }
              >
                {template.recipient_type === "patient_family" ? "Patient / Family" : "Facility"}
              </Badge>
              <Badge
                variant="outline"
                className={
                  template.is_active
                    ? "text-xs bg-emerald-50 text-emerald-700 border-emerald-200"
                    : "text-xs bg-gray-50 text-gray-500 border-gray-200"
                }
              >
                {template.is_active ? "Active" : "Inactive"}
              </Badge>
            </div>
          </div>
          {template.subject_template && (
            <p className="text-xs text-muted-foreground mt-2">
              Subject: {template.subject_template}
            </p>
          )}
        </div>
      ))}
      {templates.length === 0 && (
        <p className="text-sm text-muted-foreground">No templates configured.</p>
      )}
    </div>
  )
}

// Import Jobs Tab
function ImportJobsTab() {
  const [jobs, setJobs] = React.useState<ImportJob[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    apiClient
      .fetch<{ items: ImportJob[] }>("/api/v1/imports?page_size=20")
      .then((data) => setJobs(data.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load import jobs")
      )
      .finally(() => setIsLoading(false))
  }, [])

  const STATUS_COLORS: Record<string, string> = {
    complete: "bg-emerald-100 text-emerald-700 border-emerald-200",
    completed: "bg-emerald-100 text-emerald-700 border-emerald-200",
    ready: "bg-emerald-100 text-emerald-700 border-emerald-200",
    failed: "bg-red-100 text-red-700 border-red-200",
    committing: "bg-blue-100 text-blue-700 border-blue-200",
    processing: "bg-blue-100 text-blue-700 border-blue-200",
    mapping: "bg-blue-100 text-blue-700 border-blue-200",
    validating: "bg-blue-100 text-blue-700 border-blue-200",
    uploaded: "bg-slate-100 text-slate-700 border-slate-200",
    pending: "bg-slate-100 text-slate-700 border-slate-200",
  }

  if (isLoading) return (
    <div className="animate-pulse space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="rounded-md border p-4">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="bg-gray-200 rounded h-4 w-48" />
              <div className="bg-gray-200 rounded h-3 w-32" />
            </div>
            <div className="bg-gray-200 rounded h-5 w-16" />
          </div>
        </div>
      ))}
    </div>
  )
  if (error) return <p className="text-sm text-destructive">{error}</p>

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <div key={job.id} className="rounded-md border p-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium">{job.file_name}</p>
              <p className="text-xs text-muted-foreground">
                {formatDateTime(job.created_at)}
              </p>
            </div>
            <Badge
              variant="outline"
              className={`text-xs ${STATUS_COLORS[job.status] ?? ""}`}
            >
              {job.status}
            </Badge>
          </div>
          <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
            <span>Total: {job.total_rows ?? "—"}</span>
            <span className="text-emerald-600">Created: {job.created_count}</span>
            <span className="text-red-600">Failed: {job.failed_count}</span>
          </div>
        </div>
      ))}
      {jobs.length === 0 && (
        <p className="text-sm text-muted-foreground">No import jobs found.</p>
      )}
    </div>
  )
}

// Org Settings Tab
function OrgSettingsTab() {
  const [orgName, setOrgName] = React.useState("")
  const [isSaving, setIsSaving] = React.useState(false)
  const [isLoadingOrg, setIsLoadingOrg] = React.useState(true)
  const [saveMessage, setSaveMessage] = React.useState<string | null>(null)

  // F20: Fetch current org settings on mount so the input is pre-populated
  React.useEffect(() => {
    apiClient
      .fetch<{ org_name: string }>("/api/v1/admin/organization")
      .then((data) => setOrgName(data.org_name ?? ""))
      .catch(() => {
        // Non-critical — input remains empty
      })
      .finally(() => setIsLoadingOrg(false))
  }, [])

  const handleSave = async () => {
    setIsSaving(true)
    setSaveMessage(null)
    try {
      await apiClient.fetch("/api/v1/admin/organization", {
        method: "PATCH",
        body: JSON.stringify({ org_name: orgName }),
      })
      setSaveMessage("Settings saved.")
    } catch (err) {
      setSaveMessage(
        err instanceof ApiError ? err.message : "Failed to save settings"
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-4 max-w-md">
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Organization Name</label>
        <Input
          value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
          placeholder="Mercy Regional Medical Center"
        />
      </div>
      <Button onClick={handleSave} disabled={isSaving || isLoadingOrg || !orgName} size="sm">
        {isSaving ? "Saving..." : "Save Settings"}
      </Button>
      {saveMessage && (
        <p className="text-xs text-muted-foreground">{saveMessage}</p>
      )}
    </div>
  )
}

export default function AdminPage() {
  const isAdmin = useAdminGuard()
  const [activeTab, setActiveTab] = useQueryState(
    "tab",
    parseAsString.withDefault("users")
  )

  if (isAdmin === null) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Checking permissions...
      </div>
    )
  }

  if (!isAdmin) {
    return null // router.push handles redirect
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-bold">Admin Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage users, templates, imports, and organization settings
        </p>
      </div>

      {/* @forgeplan-spec: AC15 — 4 tabs */}
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex-1 flex flex-col overflow-hidden"
      >
        <div className="border-b px-6">
          <TabsList className="h-auto p-0 bg-transparent rounded-none border-0">
            {["users", "templates", "imports", "org-settings"].map((tab) => (
              <TabsTrigger
                key={tab}
                value={tab}
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent capitalize px-4 py-2.5 text-sm"
              >
                {tab === "org-settings"
                  ? "Org Settings"
                  : tab === "imports"
                    ? "Import Jobs"
                    : tab.charAt(0).toUpperCase() + tab.slice(1)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <TabsContent value="users" className="mt-0">
            <UsersTab />
          </TabsContent>
          <TabsContent value="templates" className="mt-0">
            <TemplatesTab />
          </TabsContent>
          <TabsContent value="imports" className="mt-0">
            <ImportJobsTab />
          </TabsContent>
          <TabsContent value="org-settings" className="mt-0">
            <OrgSettingsTab />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
