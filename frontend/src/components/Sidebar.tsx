// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Left sidebar shows only role-appropriate links
"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  ClipboardList,
  ListChecks,
  Send,
  Building2,
  BarChart2,
  Settings,
  LayoutDashboard,
  LogOut,
  ChevronRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { UserRole } from "@shared/types"

export interface NavItem {
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  allowed_roles: UserRole[]
}

// @forgeplan-spec: AC2 — Navigation items with role-based visibility
const NAV_ITEMS: NavItem[] = [
  {
    label: "Intake",
    href: "/intake",
    icon: ClipboardList,
    allowed_roles: ["intake_staff", "placement_coordinator", "admin"],
  },
  {
    label: "Operations Queue",
    href: "/queue",
    icon: ListChecks,
    allowed_roles: [
      "placement_coordinator",
      "clinical_reviewer",
      "manager",
      "admin",
    ],
  },
  {
    label: "Outreach",
    href: "/outreach",
    icon: Send,
    allowed_roles: ["placement_coordinator", "admin"],
  },
  {
    label: "Facilities",
    href: "/facilities",
    icon: Building2,
    allowed_roles: [
      "placement_coordinator",
      "clinical_reviewer",
      "manager",
      "admin",
      "read_only",
    ],
  },
  {
    label: "Analytics",
    href: "/analytics",
    icon: BarChart2,
    allowed_roles: ["manager", "admin"],
  },
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    allowed_roles: ["manager", "admin", "read_only"],
  },
  {
    label: "Admin",
    href: "/admin",
    icon: Settings,
    allowed_roles: ["admin"],
  },
]

interface SidebarProps {
  userRole?: UserRole
  userEmail?: string
  userFullName?: string
  onSignOut?: () => void
}

/**
 * Sidebar renders a role-aware navigation menu.
 * Only nav items whose allowed_roles include the current user's role are shown.
 */
export function Sidebar({
  userRole,
  userEmail,
  userFullName,
  onSignOut,
}: SidebarProps) {
  const pathname = usePathname()

  const visibleNavItems = userRole
    ? NAV_ITEMS.filter((item) => item.allowed_roles.includes(userRole))
    : []

  return (
    <aside className="flex h-full w-60 flex-col border-r bg-sidebar">
      {/* Logo / App Name */}
      <div className="flex h-14 items-center border-b px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-primary text-primary-foreground text-xs font-bold">
            PO
          </div>
          <span className="font-semibold text-sm">PlacementOps</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        <ul className="space-y-0.5">
          {visibleNavItems.map((item) => {
            const Icon = item.icon
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href)

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "group flex items-center gap-3 py-2 text-sm font-medium transition-colors border-l-[3px]",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground border-primary rounded-r-md pl-[9px] pr-3"
                      : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground border-transparent rounded-md px-3"
                  )}
                >
                  <Icon
                    className={cn(
                      "h-4 w-4 shrink-0",
                      isActive
                        ? "text-sidebar-primary"
                        : "text-muted-foreground group-hover:text-sidebar-primary"
                    )}
                  />
                  {item.label}
                  {isActive && (
                    <ChevronRight className="ml-auto h-3 w-3 text-sidebar-primary" />
                  )}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* User footer */}
      <div className="border-t px-3 py-3">
        <div className="mb-2 px-1">
          <p className="text-xs font-medium truncate">
            {userFullName ?? "User"}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {userEmail ?? ""}
          </p>
          {userRole && (
            <p className="text-xs text-muted-foreground capitalize">
              {userRole.replace("_", " ")}
            </p>
          )}
        </div>
        {onSignOut && (
          <button
            onClick={onSignOut}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <LogOut className="h-3 w-3" />
            Sign out
          </button>
        )}
      </div>
    </aside>
  )
}

export default Sidebar
