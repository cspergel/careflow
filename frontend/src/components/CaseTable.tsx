// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC3 — TanStack Table v8 with manualSorting=true, manualFiltering=true, manualPagination=true; nuqs URL state
"use client"

import * as React from "react"
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  SortingState,
  ColumnFiltersState,
  PaginationState,
} from "@tanstack/react-table"
import {
  parseAsInteger,
  parseAsString,
  parseAsArrayOf,
  useQueryStates,
} from "nuqs"
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// @forgeplan-decision: D-frontend-5-nuqs-v1-api -- Using nuqs v1 API (useQueryStates, parseAsString, etc). Why: spec pins nuqs@^1.17.0; v1 and v2 have different import paths
// F11: Accept a pageKey prop to prefix all nuqs keys and prevent cross-page contamination.
function makeCaseTableParsers(prefix: string) {
  return {
    [`${prefix}_page`]: parseAsInteger.withDefault(1),
    [`${prefix}_per_page`]: parseAsInteger.withDefault(50),
    [`${prefix}_sort`]: parseAsString.withDefault("created_at"),
    [`${prefix}_sort_dir`]: parseAsString.withDefault("desc"),
    [`${prefix}_search`]: parseAsString.withDefault(""),
    [`${prefix}_status`]: parseAsArrayOf(parseAsString).withDefault([]),
  }
}

export type CaseTableFilters = {
  page: number
  per_page: number
  sort: string
  sort_dir: string
  search: string
  status: string[]
}

// Default (unprefixed) parsers for backward-compat when pageKey not provided
const defaultParsers = {
  page: parseAsInteger.withDefault(1),
  per_page: parseAsInteger.withDefault(50),
  sort: parseAsString.withDefault("created_at"),
  sort_dir: parseAsString.withDefault("desc"),
  search: parseAsString.withDefault(""),
  status: parseAsArrayOf(parseAsString).withDefault([]),
}

export function useCaseTableFilters() {
  return useQueryStates(defaultParsers, { shallow: false })
}

/**
 * F29: Returns a [filters, setFilters] pair that uses pageKey-prefixed URL params
 * when a pageKey is provided, matching CaseTable's own prefixed nuqs state.
 * Use this in FilterBar (or any companion component) to keep params in sync with CaseTable.
 */
export function useCaseTableFiltersForKey(pageKey?: string) {
  const prefixedParsers = pageKey ? makeCaseTableParsers(pageKey) : defaultParsers
  const [rawFilters, setRawFilters] = useQueryStates(prefixedParsers as typeof defaultParsers, { shallow: false })

  const filters: CaseTableFilters = pageKey
    ? {
        page: (rawFilters as Record<string, unknown>)[`${pageKey}_page`] as number ?? 1,
        per_page: (rawFilters as Record<string, unknown>)[`${pageKey}_per_page`] as number ?? 50,
        sort: (rawFilters as Record<string, unknown>)[`${pageKey}_sort`] as string ?? "created_at",
        sort_dir: (rawFilters as Record<string, unknown>)[`${pageKey}_sort_dir`] as string ?? "desc",
        search: (rawFilters as Record<string, unknown>)[`${pageKey}_search`] as string ?? "",
        status: (rawFilters as Record<string, unknown>)[`${pageKey}_status`] as string[] ?? [],
      }
    : rawFilters as unknown as CaseTableFilters

  const setFilters = (updates: Partial<CaseTableFilters>) => {
    if (pageKey) {
      const prefixed: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(updates)) {
        prefixed[`${pageKey}_${k}`] = v
      }
      setRawFilters(prefixed as Parameters<typeof setRawFilters>[0])
    } else {
      setRawFilters(updates as Parameters<typeof setRawFilters>[0])
    }
  }

  return [filters, setFilters] as const
}

interface CaseTableProps<TData> {
  data: TData[]
  columns: ColumnDef<TData>[]
  totalCount: number
  isLoading?: boolean
  onRowClick?: (row: TData) => void
  /** F11: Prefix nuqs keys to avoid cross-page URL state contamination */
  pageKey?: string
}

/**
 * CaseTable wraps TanStack Table v8 with mandatory server-side options:
 * - manualSorting: true
 * - manualFiltering: true
 * - manualPagination: true
 * Filter/sort/pagination state is URL-persisted via nuqs.
 * Pass `pageKey` to namespace URL params when multiple CaseTables exist across pages.
 */
export function CaseTable<TData>({
  data,
  columns,
  totalCount,
  isLoading = false,
  onRowClick,
  pageKey,
}: CaseTableProps<TData>) {
  // F11: Use prefixed parsers when pageKey is provided so filters don't bleed across pages
  const prefixedParsers = pageKey ? makeCaseTableParsers(pageKey) : defaultParsers
  const [rawFilters, setRawFilters] = useQueryStates(prefixedParsers as typeof defaultParsers, { shallow: false })

  // Normalise prefixed keys back to the well-known filter shape
  const filters: CaseTableFilters = pageKey
    ? {
        page: (rawFilters as Record<string, unknown>)[`${pageKey}_page`] as number ?? 1,
        per_page: (rawFilters as Record<string, unknown>)[`${pageKey}_per_page`] as number ?? 50,
        sort: (rawFilters as Record<string, unknown>)[`${pageKey}_sort`] as string ?? "created_at",
        sort_dir: (rawFilters as Record<string, unknown>)[`${pageKey}_sort_dir`] as string ?? "desc",
        search: (rawFilters as Record<string, unknown>)[`${pageKey}_search`] as string ?? "",
        status: (rawFilters as Record<string, unknown>)[`${pageKey}_status`] as string[] ?? [],
      }
    : rawFilters as unknown as CaseTableFilters

  const setFilters = (updates: Partial<CaseTableFilters>) => {
    if (pageKey) {
      const prefixed: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(updates)) {
        prefixed[`${pageKey}_${k}`] = v
      }
      setRawFilters(prefixed as Parameters<typeof setRawFilters>[0])
    } else {
      setRawFilters(updates as Parameters<typeof setRawFilters>[0])
    }
  }

  // Derived TanStack Table state from nuqs URL state
  const sorting: SortingState = [
    { id: filters.sort, desc: filters.sort_dir === "desc" },
  ]
  const pagination: PaginationState = {
    pageIndex: Math.max(0, filters.page - 1),
    pageSize: filters.per_page,
  }
  const columnFilters: ColumnFiltersState = filters.status.length > 0
    ? [{ id: "current_status", value: filters.status }]
    : []

  // @forgeplan-spec: AC3 — manualSorting, manualFiltering, manualPagination all true
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    // Server-side data management — all three must be true
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,
    rowCount: totalCount,
    state: {
      sorting,
      columnFilters,
      pagination,
    },
    onSortingChange: (updater) => {
      const newSorting =
        typeof updater === "function" ? updater(sorting) : updater
      if (newSorting.length > 0) {
        setFilters({
          sort: newSorting[0].id,
          sort_dir: newSorting[0].desc ? "desc" : "asc",
          page: 1,
        })
      }
    },
    onPaginationChange: (updater) => {
      const newPagination =
        typeof updater === "function" ? updater(pagination) : updater
      setFilters({
        page: newPagination.pageIndex + 1,
        per_page: newPagination.pageSize,
      })
    },
  })

  const pageCount = Math.ceil(totalCount / filters.per_page)

  return (
    <div className="w-full">
      <div className="rounded-md border overflow-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b bg-muted/50">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-3 py-2 text-left font-medium text-muted-foreground"
                  >
                    {header.isPlaceholder ? null : (
                      <div
                        className={cn(
                          "flex items-center gap-1",
                          header.column.getCanSort()
                            ? "cursor-pointer select-none hover:text-foreground"
                            : ""
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                        {header.column.getCanSort() && (
                          <span className="ml-1">
                            {header.column.getIsSorted() === "asc" ? (
                              <ChevronUp className="h-3 w-3" />
                            ) : header.column.getIsSorted() === "desc" ? (
                              <ChevronDown className="h-3 w-3" />
                            ) : (
                              <ChevronsUpDown className="h-3 w-3 opacity-50" />
                            )}
                          </span>
                        )}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <>
                {[...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b">
                    <td colSpan={columns.length} className="px-3 py-2">
                      <div className="animate-pulse flex gap-3">
                        <div className="bg-gray-200 rounded h-4 w-24" />
                        <div className="bg-gray-200 rounded h-4 w-32" />
                        <div className="bg-gray-200 rounded h-4 w-20" />
                        <div className="bg-gray-200 rounded h-4 flex-1" />
                      </div>
                    </td>
                  </tr>
                ))}
              </>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="h-24 text-center text-muted-foreground"
                >
                  No cases found.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    "border-b transition-colors hover:bg-muted/50",
                    onRowClick && "cursor-pointer"
                  )}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-1.5">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between py-2">
        <p className="text-sm text-muted-foreground">
          {totalCount > 0 ? (
            <>
              Showing{" "}
              {Math.min(
                (filters.page - 1) * filters.per_page + 1,
                totalCount
              )}{" "}
              –{" "}
              {Math.min(filters.page * filters.per_page, totalCount)} of{" "}
              {totalCount} cases
            </>
          ) : (
            "No results"
          )}
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setFilters({ page: Math.max(1, filters.page - 1) })}
            disabled={filters.page <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm">
            Page {filters.page} of {Math.max(1, pageCount)}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              setFilters({ page: Math.min(pageCount, filters.page + 1) })
            }
            disabled={filters.page >= pageCount}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

export default CaseTable
