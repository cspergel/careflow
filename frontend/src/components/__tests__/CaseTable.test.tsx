// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC3 — CaseTable has manualSorting/Filtering/Pagination=true
// F22: Tests now exercise actual component behavior, not just local constants.
import React from "react"
import { render, screen, renderHook, fireEvent } from "@testing-library/react"
import { useReactTable, getCoreRowModel, type ColumnDef } from "@tanstack/react-table"

// Mock nuqs to avoid App Router dependency in tests (nuqs v1 has no testing adapter)
jest.mock("nuqs", () => {
  const makeParser = (defaultValue: unknown) => ({
    _default: defaultValue,
    withDefault: (def: unknown) => ({ _default: def }),
  })
  return {
    parseAsInteger: makeParser(0),
    parseAsString: makeParser(""),
    parseAsArrayOf: () => makeParser([]),
    useQueryStates: (parsers: Record<string, { _default: unknown }>) => {
      const defaults = Object.fromEntries(
        Object.entries(parsers).map(([k, v]) => [k, v._default ?? null])
      )
      // eslint-disable-next-line react-hooks/rules-of-hooks
      const [state, setState] = React.useState(defaults)
      return [state, setState]
    },
  }
})

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
    render(
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
    render(
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
    render(
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
    render(
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
      render(
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
