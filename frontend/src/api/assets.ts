import http from "./http";

export interface AssetCurrency {
  ccy: string;
  eq: string;
  eqUsd: string;
  availBal: string;
  frozenBal: string;
  [k: string]: unknown;
}

export interface AssetPosition {
  instId: string;
  posSide: string;
  pos: string;
  avgPx: string;
  upl: string;
  uplRatio: string;
  notionalUsd: string;
  lever: string;
  [k: string]: unknown;
}

export interface AssetBill {
  billId: string;
  ts: string;
  ccy: string;
  type: string;
  bal: string;
  balChg: string;
  sz: string;
  fee: string;
  [k: string]: unknown;
}

export interface AssetsSummary {
  net_value: number;
  currencies: AssetCurrency[];
  positions: AssetPosition[];
  bills: AssetBill[];
}

export async function getAssetsSummary(credentialId: number): Promise<AssetsSummary> {
  const r = await http.get<AssetsSummary>("/assets/summary", {
    params: { credential_id: credentialId },
  });
  return r.data;
}
