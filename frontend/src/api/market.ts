import http from "./http";

export interface Candle {
  ts: number;
  o: string;
  h: string;
  l: string;
  c: string;
  vol: string;
  volCcy?: string;
}

export interface CandlesResponse {
  symbol: string;
  bar: string;
  data: Candle[];
}

export interface Symbol {
  instId: string;
  baseCcy: string;
  quoteCcy: string;
  state: string;
}

export interface SymbolsResponse {
  data: Symbol[];
}

export async function getCandles(
  symbol: string,
  bar: string = "1m",
  limit: number = 100,
  after?: number,
): Promise<CandlesResponse> {
  const params: Record<string, string | number> = { symbol, bar, limit };
  if (after !== undefined) {
    params.after = after;
  }
  const r = await http.get<CandlesResponse>("/market/candles", { params });
  return r.data;
}

export async function getSymbols(): Promise<Symbol[]> {
  const r = await http.get<SymbolsResponse>("/market/symbols");
  return r.data.data ?? [];
}
