// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC3 — FilterBar inputs connected to nuqs state for URL persistence
"use client"

import * as React from "react"
import { Search, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useCaseTableFilters } from "@/components/CaseTable"
import type { CaseStatus } from "@/components/StatusBadge"
import { STATUS_CONFIG } from "@/components/StatusBadge"
import { cn } from "@/lib/utils"

interface FilterBarProps {
  className?: string
  statusOptions?: CaseStatus[]
  showSearch?: boolean
  showStatusFilter?: boolean
}

/**
 * FilterBar provides search and status filter inputs, synced to nuqs URL state.
 * State persists across page refreshes.
 */
export function FilterBar({
  className,
  statusOptions,
  showSearch = true,
  showStatusFilter = true,
}: FilterBarProps) {
  const [filters, setFilters] = useCaseTableFilters()

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters({ search: e.target.value, page: 1 })
  }

  const handleClearSearch = () => {
    setFilters({ search: "", page: 1 })
  }

  const handleStatusToggle = (status: CaseStatus) => {
    const current = filters.status as CaseStatus[]
    const next = current.includes(status)
      ? current.filter((s) => s !== status)
      : [...current, status]
    setFilters({ status: next, page: 1 })
  }

  const handleClearAll = () => {
    setFilters({ search: "", status: [], page: 1 })
  }

  const hasActiveFilters = filters.search || filters.status.length > 0
  const displayedStatuses = statusOptions ?? (Object.keys(STATUS_CONFIG) as CaseStatus[])

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2 flex-wrap">
        {/* Search input */}
        {showSearch && (
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by patient name, MRN..."
              value={filters.search}
              onChange={handleSearchChange}
              className="pl-8 h-8 text-sm"
            />
            {filters.search && (
              <button
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={handleClearSearch}
                type="button"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )}

        {/* Clear all button */}
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearAll}
            className="h-8 text-xs text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3 mr-1" />
            Clear filters
          </Button>
        )}
      </div>

      {/* Status filter chips */}
      {showStatusFilter && (
        <div className="flex flex-wrap gap-1.5">
          {displayedStatuses.map((status) => {
            const config = STATUS_CONFIG[status]
            const isActive = (filters.status as string[]).includes(status)
            return (
              <button
                key={status}
                type="button"
                onClick={() => handleStatusToggle(status)}
                className={cn(
                  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
                  isActive
                    ? config.color + " ring-2 ring-offset-1 ring-current/30"
                    : "bg-background text-muted-foreground border-border hover:bg-muted"
                )}
              >
                {config.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Active filter summary */}
      {filters.status.length > 0 && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span>Showing:</span>
          {(filters.status as CaseStatus[]).map((status) => (
            <Badge
              key={status}
              variant="secondary"
              className="text-xs h-5 px-1.5"
            >
              {STATUS_CONFIG[status]?.label ?? status}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

export default FilterBar
