import { withDb } from '@/db/connection';
import { getConfig } from '@/db/config';
import type { ReadingRow } from '@/db/types';

export async function saveReading(
  customerNumber: string, readingValue: number, readerId?: string
): Promise<void> {
  const existing = await getReadingThisMonth(customerNumber);
  if (existing) throw new Error('Duplicate reading for this month');

  const ts = Math.floor(Date.now() / 1000);
  return withDb(async (d) => {
    await d.execute(
      'INSERT INTO readings (customer_number, reading_value, reader_id, timestamp, synced) VALUES (?, ?, ?, ?, 0)',
      [customerNumber, readingValue, readerId ?? '', ts]
    );
  });
}

export async function getUnsyncedReadings(): Promise<ReadingRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT * FROM readings WHERE synced = 0 AND rejected = 0'
    );
    return rows as any as ReadingRow[];
  });
}

export async function markReadingRejected(localId: number): Promise<void> {
  return withDb(async (d) => {
    await d.execute('UPDATE readings SET rejected = 1 WHERE id = ?', [localId]);
  });
}

export async function getCustomerReadings(customerNumber: string, limit = 5): Promise<ReadingRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT * FROM readings WHERE customer_number = ? ORDER BY timestamp DESC LIMIT ?',
      [customerNumber, limit]
    );
    return rows as any as ReadingRow[];
  });
}

export async function markReadingSynced(localId: number, serverId: number): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      'UPDATE readings SET synced = 1, server_id = ? WHERE id = ?', [serverId, localId]
    );
  });
}

export async function deleteReadingByServerId(serverId: number): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM readings WHERE server_id = ?', [serverId]);
  });
}

export async function upsertReading(
  customerNumber: string, readingValue: number, readerId: string | null,
  timestamp: number, serverId: number
): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      `INSERT INTO readings (server_id, customer_number, reading_value, reader_id, timestamp, synced)
       VALUES (?, ?, ?, ?, ?, 1)
       ON CONFLICT(server_id) DO UPDATE SET
         reading_value = excluded.reading_value,
         reader_id = excluded.reader_id,
         timestamp = excluded.timestamp`,
      [serverId, customerNumber, readingValue, readerId ?? '', timestamp]
    );
  });
}

export async function getReadingThisMonth(customerNumber: string): Promise<ReadingRow | null> {
  const serverTimeStr = await getConfig('server_time');
  const ref = serverTimeStr ? new Date(parseInt(serverTimeStr, 10) * 1000) : new Date();
  const year = ref.getFullYear();
  const month = ref.getMonth() + 1;
  const startOfMonth = Math.floor(new Date(year, month - 1, 1).getTime() / 1000);
  const startOfNext = month < 12
    ? Math.floor(new Date(year, month, 1).getTime() / 1000)
    : Math.floor(new Date(year + 1, 0, 1).getTime() / 1000);
  return withDb(async (d) => {
    const { rows } = await d.execute(
      `SELECT * FROM readings WHERE customer_number = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1`,
      [customerNumber, startOfMonth, startOfNext]
    );
    return (rows[0] ?? null) as any as ReadingRow | null;
  });
}

export interface BatchReadingInput {
  customerNumber: string;
  readingValue: number;
  readerId: string | null;
  timestamp: number;
  serverId: number;
}

const READ_CHUNK = 100;

export async function batchUpsertReadings(readings: BatchReadingInput[]): Promise<void> {
  await withDb(async (d) => {
    for (let i = 0; i < readings.length; i += READ_CHUNK) {
      const chunk = readings.slice(i, i + READ_CHUNK);
      await d.transaction(async (tx) => {
        for (const r of chunk) {
          await tx.execute(
            `INSERT INTO readings (server_id, customer_number, reading_value, reader_id, timestamp, synced)
             VALUES (?, ?, ?, ?, ?, 1)
             ON CONFLICT(server_id) DO UPDATE SET
               reading_value = excluded.reading_value,
               reader_id = excluded.reader_id,
               timestamp = excluded.timestamp`,
            [r.serverId, r.customerNumber, r.readingValue, r.readerId ?? '', r.timestamp]
          );
        }
      });
    }
  });
}

export async function batchDeleteReadings(serverIds: number[]): Promise<void> {
  if (serverIds.length === 0) return;
  await withDb(async (d) => {
    await d.transaction(async (tx) => {
      for (const sid of serverIds) {
        await tx.execute('DELETE FROM readings WHERE server_id = ?', [sid]);
      }
    });
  });
}

export async function getAllServerIds(): Promise<number[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT server_id FROM readings WHERE server_id IS NOT NULL'
    );
    return rows.map((r: any) => r.server_id);
  });
}

export async function deleteUnsyncedReadings(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM readings WHERE synced = 0');
  });
}

export async function clearAllReadings(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM readings');
  });
}
