import type { OntologyNode } from "@nql/shared-types";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NodeDrawer } from "@/components/ontology/node-drawer";

const NODE: OntologyNode = {
  id: "table:fact_sales",
  label: "Sales Transactions",
  kind: "table",
  domain: "Automotive Sales",
  description: "One governed row per sales order.",
  physicalName: "automotive.fact_sales",
  tableType: "fact",
  grain: "One row per sales order",
  primaryKey: "order_id",
  synonyms: ["sales", "transactions"],
  tables: ["automotive.fact_sales"],
  columns: [
    { name: "order_id", displayName: "Order ID", type: "bigint", role: "key" },
    {
      name: "carline_id",
      displayName: "Car Line ID",
      type: "integer",
      role: "foreign_key",
      references: "dim_carline.carline_id",
    },
  ],
  relationships: ["Sales to Vehicle → Vehicle / Car Line"],
  lineage: ["fact_sales.carline_id → dim_carline.carline_id"],
  degree: 7,
  cluster: "Facts",
  clusterColor: "#2563eb",
};

describe("NodeDrawer", () => {
  it("opens with business names and aliases, hiding technical bindings", () => {
    render(<NodeDrawer node={NODE} onClose={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Sales Transactions" })).toBeVisible();
    expect(screen.getByText("Business Events")).toBeVisible();
    expect(screen.getByText("Also known as")).toBeVisible();
    expect(screen.getByText("sales")).toBeVisible();
    expect(screen.queryByText("automotive.fact_sales")).toBeNull();
  });

  it("shows source bindings with the technical overlay", () => {
    render(<NodeDrawer node={NODE} onClose={vi.fn()} overlay="technical" />);

    expect(screen.getAllByText("automotive.fact_sales").length).toBeGreaterThanOrEqual(2);
  });

  it("shows field-level schema and reference targets", async () => {
    const user = userEvent.setup();
    render(<NodeDrawer node={NODE} onClose={vi.fn()} />);

    await user.click(screen.getByRole("tab", { name: "Fields" }));
    expect(screen.getByText("order_id")).toBeVisible();
    expect(screen.getByText("ref:dim_carline.carline_id")).toBeVisible();
    expect(screen.getByLabelText("Primary key")).toBeVisible();
  });

  it("shows graph reach and lineage without another request", async () => {
    const user = userEvent.setup();
    render(<NodeDrawer node={NODE} onClose={vi.fn()} />);

    await user.click(screen.getByRole("tab", { name: "Connections" }));
    expect(screen.getByText("7")).toBeVisible();
    expect(screen.getByText("Sales to Vehicle → Vehicle / Car Line")).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Source" }));
    expect(screen.getByText("fact_sales.carline_id → dim_carline.carline_id")).toBeVisible();
  });

  it("closes from the button and Escape", async () => {
    const close = vi.fn();
    const user = userEvent.setup();
    render(<NodeDrawer node={NODE} onClose={close} />);

    await user.click(screen.getByRole("button", { name: "Close details" }));
    expect(close).toHaveBeenCalledTimes(1);

    await user.keyboard("{Escape}");
    expect(close).toHaveBeenCalledTimes(2);
  });
});
