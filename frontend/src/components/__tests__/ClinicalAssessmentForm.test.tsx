// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC12 — ClinicalAssessmentForm uses accepts_* field names matching backend ORM
import React from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ClinicalAssessmentForm } from "../ClinicalAssessmentForm"

describe("ClinicalAssessmentForm", () => {
  const mockOnSubmit = jest.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    mockOnSubmit.mockClear()
  })

  test("renders the form", () => {
    render(<ClinicalAssessmentForm onSubmit={mockOnSubmit} />)
    expect(
      screen.getByLabelText(/Recommended Level of Care/i)
    ).toBeInTheDocument()
  })

  test("shows in-house HD field when accepts_hd is checked", async () => {
    render(<ClinicalAssessmentForm onSubmit={mockOnSubmit} />)

    // In-house HD field should not be visible initially
    expect(screen.queryByLabelText(/In-House Hemodialysis/i)).not.toBeInTheDocument()

    // Check accepts_hd checkbox
    const hdCheckbox = screen.getByLabelText(/Hemodialysis \(HD\)/i)
    await userEvent.click(hdCheckbox)

    // In-house HD field should now be visible
    await waitFor(() => {
      expect(screen.getByLabelText(/In-House Hemodialysis/i)).toBeInTheDocument()
    })
  })

  test("AC12: form submits with accepts_hd and in_house_hemodialysis", async () => {
    render(
      <ClinicalAssessmentForm
        onSubmit={mockOnSubmit}
        defaultValues={{
          recommended_level_of_care: "snf",
          accepts_hd: true,
          in_house_hemodialysis: true,
        }}
      />
    )

    // In-house HD field should be visible (accepts_hd is pre-checked)
    await waitFor(() => {
      expect(screen.getByLabelText(/In-House Hemodialysis/i)).toBeInTheDocument()
    })

    // Submit should succeed
    const saveButton = screen.getByRole("button", { name: /Save Draft/i })
    await userEvent.click(saveButton)

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          accepts_hd: true,
          in_house_hemodialysis: true,
        })
      )
    })
  })

  test("peritoneal dialysis checkbox independent of HD", async () => {
    render(
      <ClinicalAssessmentForm
        onSubmit={mockOnSubmit}
        defaultValues={{ recommended_level_of_care: "snf" }}
      />
    )

    // Peritoneal dialysis field should be visible independently
    expect(screen.getByLabelText(/Peritoneal Dialysis/i)).toBeInTheDocument()

    // In-house HD should NOT be visible when accepts_hd is unchecked
    expect(screen.queryByLabelText(/In-House Hemodialysis/i)).not.toBeInTheDocument()
  })

  test("renders all major form sections", () => {
    render(<ClinicalAssessmentForm onSubmit={mockOnSubmit} />)

    // Should have 20+ fields across these sections
    expect(screen.getByRole("heading", { name: "Level of Care Recommendation" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Clinical Summary" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Respiratory Needs" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Dialysis" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Wound & IV Needs" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Behavioral & Special Needs" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Additional Notes" })).toBeInTheDocument()
  })

  test("Save Draft and Finalize Assessment buttons are present", () => {
    render(<ClinicalAssessmentForm onSubmit={mockOnSubmit} />)

    expect(screen.getByRole("button", { name: /Save Draft/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Finalize Assessment/i })).toBeInTheDocument()
  })

  test("form is read-only when readOnly=true", () => {
    render(
      <ClinicalAssessmentForm
        onSubmit={mockOnSubmit}
        readOnly={true}
        defaultValues={{ recommended_level_of_care: "snf" }}
      />
    )

    // Buttons should not be present in read-only mode
    expect(screen.queryByRole("button", { name: /Save Draft/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Finalize Assessment/i })).not.toBeInTheDocument()
  })
})
