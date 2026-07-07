export interface CustomerRow {
  customer_number: string;
  name: string;
  address: string;
  contact_number: string;
  phase: string | null;
  block: string | null;
  street: string | null;
  x_coordinate: number | null;
  y_coordinate: number | null;
  last_reading_value: number | null;
  last_reading_timestamp: number | null;
}

export interface ReadingRow {
  id: number;
  server_id: number | null;
  customer_number: string;
  reading_value: number;
  reader_id: string | null;
  timestamp: number;
  synced: number;
  rejected: number;
}

export interface CustomerFilters {
  phase?: string;
  block?: string;
  street?: string;
}

export interface PricingTier {
  label: string;
  from_unit: number;
  to_unit: number;
  rate: number;
  unit?: string;
}

export interface BreakdownItem {
  label: string;
  units: number;
  charge: number;
}
