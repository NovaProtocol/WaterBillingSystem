export interface CustomerDetailResponse {
  customer_number: string;
  name: string;
  address: string;
  contact_number: string;
  email: string;
  x_coordinate: number;
  y_coordinate: number;
  cumulative_balance: number;
  readings: ReadingResponse[];
}

export interface ReadingResponse {
  id: number;
  customer_number: string;
  reading_value: number;
  reader: string | null;
  timestamp: number;
}

export interface SyncResponse {
  synced: number;
  total: number;
  results: { index: number; reading_id: number; customer_number: string }[];
  errors: { index: number; error: string }[];
}

export interface PricingResponse {
  tiers: { label: string; from_unit: number; to_unit: number; rate: number; unit: string }[];
  late_penalty: number;
  due_days: number;
}

export interface ChangedCustomersResponse {
  customer_numbers: string[];
  server_time: number;
  total_customers: number;
}

export interface BulkCustomerData {
  customer: {
    customer_number: string;
    name: string;
    address: string;
    contact_number: string;
    phase: string | null;
    block: string | null;
    street: string | null;
    x_coordinate: number | null;
    y_coordinate: number | null;
    nfc_uid: string | null;
  };
  readings: {
    id: number;
    reading_value: number;
    reader: string | null;
    timestamp: number;
  }[];
}

export interface BulkReadingsResponse {
  customers: Record<string, BulkCustomerData>;
}

export interface NfcConfigResponse {
  nfc_pwd_secret: string;
  nfc_generation: number;
}

export interface NfcTagsResponse {
  tags: { uid: string; customer_number: string }[];
}

export interface NfcSyncRequest {
  enrollments: { uid: string; customer_number: string }[];
}

export interface NfcSyncResponse {
  synced: number;
  total: number;
  errors: { index: number; error: string }[];
}

export interface KeyInfoResponse {
  api_key: {
    id: number;
    label: string;
    is_active: boolean;
    date_created: string;
  };
  staff: {
    id: number;
    username: string;
    name: string;
    can_read_meters: boolean;
    can_accept_payment: boolean;
    can_enroll_customer: boolean;
    can_drop_reading: boolean;
    can_drop_payment: boolean;
    can_enroll_staff: boolean;
    can_manage_billing: boolean;
  } | null;
}
