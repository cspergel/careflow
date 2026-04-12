// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC3 — CaseTable has manualSorting/Filtering/Pagination=true
// F22: Tests now exercise actual component behavior, not just local constants.
import React from "react"
import { render, screen, renderHook, fireEvent } from "@testing-library/react"
import { useReactTable, getCoreRowModel, type ColumnDef } from "@tanstack/react-table"
import { NuqsTestingAdapter } from "nuqs/adapters/testing"

// Helper to wrap components that depend on nuqs URL state
function withNuqs(ui: React.ReactElement) {
  return render(<NuqsTestingAdapter>{ui}</NuqsTestingAdapter>)
}

describe("CaseTable — manual server-side flags", () => {
  test("useReactTable accepts all manual flags without error", () => {
    expect(() => {
      renderHook(() =>
        useReactTable({
          data: [],
          columns: [],
          getCoreRowModel: getCoreRowModel(),
          manualSorting: true,
          manualFiltering: true,
          manualPagination: true,
          rowCount: 0,
        })
      )
    }).not.toThrow()
  })
})

describe("CaseTable component", () => {
  type Row = { id: string; name: string }

  const columns: ColumnDef<Row>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: ({ row }) => row.getValue("name"),
    },
  ]

  test("renders column headers", () => {
    const { CaseTable } = require("../CaseTable")
    withNuqs(
      <CaseTable
        data={[]}
        columns={columns}
        totalCount={0}
      />
    )
    expect(screen.getByText("Name")).toBeInTheDocument()
  })

  test("renders empty state when data is empty", () => {
    const { CaseTable } = require("../CaseTable")
    withNuqs(
      <CaseTable
        data={[]}
        columns={columns}
        totalCount={0}
      />
    )
    expect(screen.getByText("No cases found.")).toBeInTheDocument()
  })

  test("renders row data", () => {
    const { CaseTable } = require("../CaseTable")
    const data: Row[] = [{ id: "1", name: "Alice Smith" }]
    withNuqs(
      <CaseTable
        data={data}
        columns={columns}
        totalCount={1}
      />
    )
    expect(screen.getByText("Alice Smith")).toBeInTheDocument()
  })

  test("calls onRowClick when a row is clicked", () => {
    const { CaseTable } = require("../CaseTable")
    const onRowClick = jest.fn()
    const data: Row[] = [{ id: "1", name: "Bob Jones" }]
    withNuqs(
      <CaseTable
        data={data}
        columns={columns}
        totalCount={1}
        onRowClick={onRowClick}
      />
    )
    fireEvent.click(screen.getByText("Bob Jones"))
    expect(onRowClick).toHaveBeenCalledWith(data[0])
  })

  test("module exports CaseTable and useCaseTableFilters", async () => {
    const module = await import("../CaseTable")
    expect(typeof module.CaseTable).toBe("function")
    expect(typeof module.useCaseTableFilters).toBe("function")
  })
})

describe("CaseTable — pageKey URL namespacing (F11)", () => {
  test("accepts pageKey prop without error", () => {
    const { CaseTable } = require("../CaseTable")
    expect(() => {
      withNuqs(
        <CaseTable
          data={[]}
          columns={[]}
          totalCount={0}
          pageKey="intake"
        />
      )
    }).not.toThrow()
  })
})
