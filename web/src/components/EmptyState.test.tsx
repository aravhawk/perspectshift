import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";

describe("EmptyState", () => {
  it("renders guidance without placeholder metrics", () => {
    render(
      <EmptyState title="No profiles loaded">
        <p>Connect a real bundle to continue.</p>
      </EmptyState>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("No profiles loaded");
    expect(screen.queryByText(/sample profile/i)).not.toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("exposes textual status not only color", () => {
    render(<StatusBadge tone="bad" label="Control hold asserted" />);
    expect(screen.getByText("Error:")).toBeInTheDocument();
    expect(screen.getByText("Control hold asserted")).toBeInTheDocument();
  });
});
