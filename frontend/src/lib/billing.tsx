"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { type BillingSummary, useApi } from "./api";
import { useWorkspace } from "./workspace";

type BillingState = { billing: BillingSummary | null; refreshBilling: () => Promise<void> };

const Ctx = createContext<BillingState>({ billing: null, refreshBilling: async () => {} });

/** Keeps the current workspace's balance and limits fresh for the sidebar and the Create page. */
export function BillingProvider({ children }: { children: React.ReactNode }) {
  const api = useApi();
  const { current } = useWorkspace();
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const id = current?.id;

  const refreshBilling = useCallback(async () => {
    if (!id) return;
    try {
      setBilling(await api<BillingSummary>(`/v1/workspaces/${id}/billing`));
    } catch {}
  }, [api, id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reload when the workspace changes
    refreshBilling();
    const timer = setInterval(refreshBilling, 30_000);
    return () => clearInterval(timer);
  }, [refreshBilling]);

  return <Ctx.Provider value={{ billing, refreshBilling }}>{children}</Ctx.Provider>;
}

export const useBilling = () => useContext(Ctx);

/** Spending room left this month for the current user, or null when unlimited. */
export function monthlyRoom(b: BillingSummary): number | null {
  const rooms = [
    b.monthly_limit_usd != null ? b.monthly_limit_usd - b.spent_this_month_usd : null,
    b.my_monthly_limit_usd != null ? b.my_monthly_limit_usd - b.my_spent_this_month_usd : null,
  ].filter((r): r is number => r != null);
  return rooms.length ? Math.max(0, Math.min(...rooms)) : null;
}
