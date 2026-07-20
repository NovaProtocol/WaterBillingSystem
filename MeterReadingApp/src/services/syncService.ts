import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import {
  getConfig,
  setConfig,
  getIntSetting,
  setIntSetting,
  getUnsyncedReadings,
  getCustomerCount,
  markReadingSynced,
  markReadingRejected,
  replaceCustomerData,
  getUnsyncedNfcEnrollments,
  markNfcEnrollmentSynced,
  upsertNfcCache,
  deleteSyncedNfcEnrollments,
  clearNfcCache,
  clearAllNfcEnrollments,
  clearAllCustomers,
  clearAllReadings,
  setOnResetData,
  type BatchReadingInput,
} from '@/db/database';
import { computeTagPwd } from '@/services/nfcService';

async function doResyncNfc(serverUrl: string, apiKey: string, signal: AbortSignal): Promise<void> {
  await clearNfcCache();
  await clearAllNfcEnrollments();

  const secrets = await getNfcSecrets();
  const nfcPwdSecret = secrets?.nfcPwdSecret;

  const res = await fetch(`${serverUrl}/api/nfc/tags`, {
    headers: { Authorization: `Bearer ${apiKey}` },
    signal,
  });
  if (!res.ok) throw new Error('Failed to fetch NFC tags from server');

  const data: NfcTagsResponse = await res.json();
  for (const tag of data.tags ?? []) {
    const pwd = nfcPwdSecret ? computeTagPwd(nfcPwdSecret, tag.uid) : '00000000';
    await upsertNfcCache(tag.uid, String(tag.customer_number), pwd);
  }

  await setConfig('nfc_has_pending', '0');
}

async function doResyncReadings(serverUrl: string, apiKey: string, signal: AbortSignal): Promise<void> {
  await clearAllCustomers();
  await clearAllReadings();
  await setIntSetting('lastSyncTime', 0);
}

import {
  type SyncResponse,
  type ChangedCustomersResponse,
  type BulkReadingsResponse,
  type NfcConfigResponse,
  type NfcTagsResponse,
  type KeyInfoResponse,
} from '@/types/api';

const BATCH_SIZE = 500;
const POLL_INTERVAL = 10_000;

export type SyncStatus = 'idle' | 'syncing' | 'synced' | 'error';

interface UseSyncResult {
  syncStatus: SyncStatus;
  triggerSync: () => void;
  lastError: string | null;
  lastSyncCount: number;
  resetSyncState: () => void;
  pendingCount: number;
  serverTotal: number;
  lastSyncTime: string | null;
  localCount: number;
  resyncNfc: () => Promise<void>;
  resyncReadings: () => Promise<void>;
  resyncing: boolean;
}

let _nfcPwdSecret: string | null = null;

interface NfcSecrets {
  nfcPwdSecret: string;
}

async function getNfcSecrets(): Promise<NfcSecrets | null> {
  if (_nfcPwdSecret) return { nfcPwdSecret: _nfcPwdSecret };
  _nfcPwdSecret = await getConfig('nfc_pwd_secret');
  if (!_nfcPwdSecret) return null;
  return { nfcPwdSecret: _nfcPwdSecret };
}

async function ensureNfcSecrets(serverUrl: string, apiKey: string, signal: AbortSignal): Promise<void> {
  const res = await fetch(`${serverUrl}/api/nfc/config`, {
    headers: { Authorization: `Bearer ${apiKey}` },
    signal,
  });
  if (!res.ok) return;

  const data: NfcConfigResponse = await res.json();

  if (!_nfcPwdSecret) {
    _nfcPwdSecret = await getConfig('nfc_pwd_secret');
  }
  if (!_nfcPwdSecret && data.nfc_pwd_secret) {
    await setConfig('nfc_pwd_secret', data.nfc_pwd_secret);
    _nfcPwdSecret = data.nfc_pwd_secret;
  }

  const storedGen = await getConfig('nfc_generation');
  const serverGen = data.nfc_generation ?? 0;
  if (storedGen && parseInt(storedGen, 10) !== serverGen) {
    await clearNfcCache();
    await setConfig('nfc_generation', String(serverGen));
  } else if (!storedGen) {
    await setConfig('nfc_generation', String(serverGen));
  }
}

async function uploadNfcEnrollments(serverUrl: string, apiKey: string, signal: AbortSignal): Promise<void> {
  const pending = await getUnsyncedNfcEnrollments();
  if (pending.length === 0) return;

  const res = await fetch(`${serverUrl}/api/nfc/sync`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      enrollments: pending.map((e) => ({
        uid: e.uid,
        customer_number: Number(e.customer_number),
      })),
    }),
    signal,
  });

  if (res.ok) {
    for (const e of pending) {
      await markNfcEnrollmentSynced(e.id);
    }
  }
}

async function processNfcCacheBatch(
  customers: BulkReadingsResponse['customers'],
  nfcPwdSecret: string
): Promise<void> {
  for (const [, data] of Object.entries(customers)) {
    const nfcUid = data.customer.nfc_uid;
    if (!nfcUid) continue;

    const pwd = computeTagPwd(nfcPwdSecret, nfcUid);
    await upsertNfcCache(nfcUid, String(data.customer.customer_number), pwd);
  }
}

export function useSync(): UseSyncResult {
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastSyncCount, setLastSyncCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [serverTotal, setServerTotal] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
  const [localCount, setLocalCount] = useState(0);
  const [resyncing, setResyncing] = useState(false);
  const syncingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const resetSyncState = useCallback(() => {
    _nfcPwdSecret = null;
    setSyncStatus('idle');
    setLastError(null);
    setLastSyncCount(0);
    setPendingCount(0);
    setServerTotal(0);
    setLastSyncTime(null);
    setLocalCount(0);
  }, []);

  useEffect(() => {
    setOnResetData(resetSyncState);
    return () => setOnResetData(null);
  }, [resetSyncState]);

  const doSync = useCallback(async () => {
    if (syncingRef.current) return;
    syncingRef.current = true;
    let syncErrors = 0;

    try {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const serverUrl = await getConfig('serverUrl');
      const apiKey = await getConfig('apiKey');
      if (!serverUrl || !apiKey) { syncingRef.current = false; return; }

      setSyncStatus('syncing');

      // Fetch staff permissions
      try {
        const infoRes = await fetch(`${serverUrl}/api/key/info`, {
          headers: { Authorization: `Bearer ${apiKey}` },
          signal: controller.signal,
        });
        if (infoRes.ok) {
          const infoData: KeyInfoResponse = await infoRes.json();
          if (infoData.staff) {
            await setConfig('canEnrollCustomer', infoData.staff.can_enroll_customer ? '1' : '0');
            await setConfig('canReadMeters', infoData.staff.can_read_meters ? '1' : '0');
            await setConfig('canAcceptPayment', infoData.staff.can_accept_payment ? '1' : '0');
            await setConfig('canDropReading', infoData.staff.can_drop_reading ? '1' : '0');
            await setConfig('canDropPayment', infoData.staff.can_drop_payment ? '1' : '0');
            await setConfig('canEnrollStaff', infoData.staff.can_enroll_staff ? '1' : '0');
            await setConfig('canManageBilling', infoData.staff.can_manage_billing ? '1' : '0');
            await setConfig('perm_fetched', '1');
          }
        }
      } catch {
        syncErrors++;
      }

      // Ensure NFC secrets are available
      await ensureNfcSecrets(serverUrl, apiKey, controller.signal);

      // Upload unsynced NFC enrollments
      await uploadNfcEnrollments(serverUrl, apiKey, controller.signal);

      // Upload unsynced local readings
      const unsynced = await getUnsyncedReadings();
      if (unsynced.length > 0) {
        const syncBody = {
          readings: unsynced.map((r) => ({
            customer_number: Number(r.customer_number),
            reading_value: r.reading_value,
            timestamp: r.timestamp,
          })),
        };
        const syncRes = await fetch(`${serverUrl}/api/readings/sync`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify(syncBody),
          signal: controller.signal,
        });
        if (syncRes.ok) {
          const syncData: SyncResponse = await syncRes.json();
          for (const result of syncData.results ?? []) {
            const local = unsynced[result.index];
            if (local && result.reading_id) {
              await markReadingSynced(local.id, result.reading_id);
            }
          }
          for (const err of syncData.errors ?? []) {
            const local = unsynced[err.index];
            if (local) {
              await markReadingRejected(local.id);
            }
          }
        } else {
          syncErrors++;
        }
      }

      // Check for changed customers since last sync
      const lastSync = await getIntSetting('lastSyncTime', 0);
      const changedUrl = `${serverUrl}/api/customers/changed?since=${lastSync}`;
      const changedRes = await fetch(changedUrl, {
        headers: { Authorization: `Bearer ${apiKey}` },
        signal: controller.signal,
      });

      if (changedRes.ok) {
        const changedData: ChangedCustomersResponse = await changedRes.json();
        const { customer_numbers, server_time, total_customers } = changedData;

        setServerTotal(total_customers);
        setPendingCount(customer_numbers.length);

        if (customer_numbers.length > 0) {
          const historyCount = await getIntSetting('historyCount', 5);

          // Build batch URLs
          const batchUrls: string[] = [];
          for (let i = 0; i < customer_numbers.length; i += BATCH_SIZE) {
            const chunk = customer_numbers.slice(i, i + BATCH_SIZE);
            batchUrls.push(
              `${serverUrl}/api/readings/bulk?customer_numbers=${encodeURIComponent(chunk.join(','))}&limit=${historyCount}`
            );
          }

          // Phase 1: fetch all batches with pipelining
          const buildHeaders = () => ({
            Authorization: `Bearer ${apiKey}`,
          });

          // Start first fetch immediately
          let nextFetch: Promise<Response | null> = fetch(batchUrls[0], {
            headers: buildHeaders(),
            signal: controller.signal,
          }).catch(() => null);

          const allBatchData: { chunk: number[]; customers: BulkReadingsResponse['customers'] }[] = [];

          for (let i = 0; i < batchUrls.length; i++) {
            const res = await nextFetch;

            // Start next fetch in background before processing this one
            if (i + 1 < batchUrls.length) {
              nextFetch = fetch(batchUrls[i + 1], {
                headers: buildHeaders(),
                signal: controller.signal,
              }).catch(() => null);
            }

            const chunk = customer_numbers.slice(i * BATCH_SIZE, (i + 1) * BATCH_SIZE);
            if (res && res.ok) {
              const bulkData: BulkReadingsResponse = await res.json();
              allBatchData.push({ chunk, customers: bulkData.customers ?? {} });
            } else {
              allBatchData.push({ chunk, customers: {} });
              syncErrors++;
            }
          }

          const nfcSecrets = await getNfcSecrets();

          // Phase 2: process all data per-customer with individual commits
          let processed = 0;
          for (const { customers } of allBatchData) {
            // Process NFC cache entries
            if (nfcSecrets) {
              await processNfcCacheBatch(customers, nfcSecrets.nfcPwdSecret);
            }

            for (const [cn, data] of Object.entries(customers)) {
              const customerRow = {
                customer_number: String(data.customer.customer_number),
                name: data.customer.name ?? '',
                address: data.customer.address ?? '',
                contact_number: data.customer.contact_number ?? '',
                phase: data.customer.phase ?? null,
                block: data.customer.block ?? null,
                street: data.customer.street ?? null,
                x_coordinate: data.customer.x_coordinate ?? null,
                y_coordinate: data.customer.y_coordinate ?? null,
                last_reading_value: data.readings?.[0]?.reading_value ?? null,
                last_reading_timestamp: data.readings?.[0]?.timestamp ?? null,
              };

              const readings: BatchReadingInput[] = (data.readings ?? []).map((r) => ({
                customerNumber: cn,
                readingValue: r.reading_value,
                readerId: r.reader,
                timestamp: r.timestamp,
                serverId: r.id,
              }));

              await replaceCustomerData(cn, customerRow, readings);
              processed++;
              setLocalCount(processed);
            }
          }

          setLastSyncCount(customer_numbers.length);
        }

        await setIntSetting('lastSyncTime', server_time);
      }

      // Clean up synced NFC enrollments
      await deleteSyncedNfcEnrollments();

      setPendingCount(0);
      setLastSyncTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
      const lc = await getCustomerCount();
      setLocalCount(lc);
      if (syncErrors > 0) {
        setSyncStatus('error');
        setLastError(`${syncErrors} sync operation(s) failed. Data may be incomplete.`);
      } else {
        setSyncStatus('synced');
        setLastError(null);
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') { return; }
      syncErrors++;
      const msg = e instanceof Error ? e.message : String(e);
      if (__DEV__) console.warn('[sync]', msg);
      setLastError(msg);
      setSyncStatus('error');
    } finally {
      syncingRef.current = false;
    }
  }, []);

  useEffect(() => {
    doSync();

    const timer = setInterval(doSync, POLL_INTERVAL);

    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') doSync();
    });

    return () => {
      clearInterval(timer);
      sub.remove();
      abortRef.current?.abort();
    };
  }, [doSync]);

  const triggerSync = useCallback(() => {
    doSync();
  }, [doSync]);

  const resyncNfc = useCallback(async () => {
    const serverUrl = await getConfig('serverUrl');
    const apiKey = await getConfig('apiKey');
    if (!serverUrl || !apiKey) return;
    setResyncing(true);
    setSyncStatus('syncing');
    try {
      const controller = new AbortController();
      await ensureNfcSecrets(serverUrl, apiKey, controller.signal);
      await doResyncNfc(serverUrl, apiKey, controller.signal);
      setSyncStatus('synced');
      setLastError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      setSyncStatus('error');
    } finally {
      setResyncing(false);
    }
  }, []);

  const resyncReadings = useCallback(async () => {
    const serverUrl = await getConfig('serverUrl');
    const apiKey = await getConfig('apiKey');
    if (!serverUrl || !apiKey) return;
    setResyncing(true);
    setSyncStatus('syncing');
    try {
      const controller = new AbortController();
      await doResyncReadings(serverUrl, apiKey, controller.signal);
      setSyncStatus('idle');
      setLastError(null);
      doSync();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      setSyncStatus('error');
    } finally {
      setResyncing(false);
    }
  }, [doSync]);

  return {
    syncStatus,
    triggerSync,
    lastError,
    lastSyncCount,
    resetSyncState,
    pendingCount,
    serverTotal,
    lastSyncTime,
    localCount,
    resyncNfc,
    resyncReadings,
    resyncing,
  };
}
