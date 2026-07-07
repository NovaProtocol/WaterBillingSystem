import { withDb } from '@/db/connection';

export interface NfcCacheRow {
  uid: string;
  customer_number: string;
  password: string;
}

export interface NfcEnrollmentRow {
  id: number;
  uid: string;
  customer_number: string;
  synced: number;
}

export async function getNfcCache(uid: string): Promise<NfcCacheRow | null> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT uid, customer_number, password FROM nfc_cache WHERE uid = ?',
      [uid]
    );
    const row = rows[0];
    if (!row) return null;
    const r = row as any;
    return { uid: r.uid, customer_number: r.customer_number, password: r.password };
  });
}

export async function upsertNfcCache(
  uid: string,
  customerNumber: string,
  password: string
): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      'INSERT OR REPLACE INTO nfc_cache (uid, customer_number, password) VALUES (?, ?, ?)',
      [uid, customerNumber, password]
    );
  });
}

export async function getNfcCacheAll(): Promise<NfcCacheRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT uid, customer_number, password FROM nfc_cache ORDER BY customer_number ASC'
    );
    return rows.map((r: any) => ({
      uid: r.uid,
      customer_number: r.customer_number,
      password: r.password,
    }));
  });
}

export async function clearNfcCache(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM nfc_cache');
  });
}

export async function insertNfcEnrollment(
  uid: string,
  customerNumber: string
): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      'INSERT INTO nfc_enrollments (uid, customer_number, synced) VALUES (?, ?, 0)',
      [uid, customerNumber]
    );
  });
}

export async function getUnsyncedNfcEnrollments(): Promise<NfcEnrollmentRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT id, uid, customer_number, synced FROM nfc_enrollments WHERE synced = 0'
    );
    return rows.map((r: any) => ({
      id: r.id,
      uid: r.uid,
      customer_number: r.customer_number,
      synced: r.synced,
    }));
  });
}

export async function markNfcEnrollmentSynced(id: number): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      'UPDATE nfc_enrollments SET synced = 1 WHERE id = ?',
      [id]
    );
  });
}

export async function deleteSyncedNfcEnrollments(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM nfc_enrollments WHERE synced = 1');
  });
}

export async function clearAllNfcEnrollments(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM nfc_enrollments');
  });
}

export async function deleteNfcCacheByUid(uid: string): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM nfc_cache WHERE uid = ?', [uid]);
  });
}

export async function deleteNfcEnrollmentByUid(uid: string): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM nfc_enrollments WHERE uid = ?', [uid]);
  });
}
