import { open, type DB } from '@op-engineering/op-sqlite';

let db: DB | null = null;
let initFailedAt = 0;
let opQueue: Promise<void> = Promise.resolve();
let onResetData: (() => void) | null = null;

export function setOnResetData(fn: (() => void) | null): void {
  onResetData = fn;
}

const SCHEMA = `
  CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
  CREATE TABLE IF NOT EXISTS customers (
    customer_number TEXT PRIMARY KEY, name TEXT, address TEXT,
    contact_number TEXT, phase TEXT, block TEXT, street TEXT,
    x_coordinate REAL, y_coordinate REAL,
    last_reading_value REAL, last_reading_timestamp INTEGER
  );
  CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER UNIQUE,
    customer_number TEXT NOT NULL, reading_value REAL NOT NULL,
    reader_id TEXT, timestamp INTEGER NOT NULL,
    synced INTEGER DEFAULT 0, rejected INTEGER DEFAULT 0
  );
  CREATE TABLE IF NOT EXISTS nfc_cache (
    uid TEXT PRIMARY KEY, customer_number TEXT NOT NULL, password TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS nfc_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL, customer_number TEXT NOT NULL,
    synced INTEGER DEFAULT 0
  );
`;

const MIGRATIONS = [
  'ALTER TABLE readings ADD COLUMN server_id INTEGER',
  'ALTER TABLE readings ADD COLUMN rejected INTEGER DEFAULT 0',
  'CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_server_id ON readings(server_id)',
  'ALTER TABLE customers ADD COLUMN phase TEXT',
  'ALTER TABLE customers ADD COLUMN block TEXT',
  'ALTER TABLE customers ADD COLUMN street TEXT',
  'ALTER TABLE customers ADD COLUMN x_coordinate REAL',
  'ALTER TABLE customers ADD COLUMN y_coordinate REAL',
  'CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp)',
  'ALTER TABLE nfc_cache RENAME COLUMN tag_id TO uid',
  'ALTER TABLE nfc_enrollments RENAME COLUMN tag_id TO uid',
];

async function initDb(): Promise<DB | null> {
  for (let attempt = 0; attempt < 3; attempt++) {
    let d: DB | null = null;
    try {
      d = open({ name: 'meterreading.db' });
      await d.execute(SCHEMA);
      for (const sql of MIGRATIONS) {
        try { await d.execute(sql); } catch { /* already exists */ }
      }
      return d;
    } catch (e) {
      if (attempt === 0) console.warn('[db] init failed:', e);
      try { d?.close(); } catch { /* ignore */ }
      try { d?.delete(); } catch { /* ignore */ }
    }
  }
  return null;
}

export async function getDb(): Promise<DB | null> {
  if (initFailedAt && Date.now() - initFailedAt < 30000) return null;
  if (db) return db;
  db = await initDb();
  if (!db) initFailedAt = Date.now();
  return db;
}

export function closeAndResetDb(): void {
  const oldDb = db;
  db = null;
  initFailedAt = 0;
  if (oldDb) {
    try { oldDb.close(); } catch { /* ignore */ }
    try { oldDb.delete(); } catch { /* ignore */ }
  }
}

/** Run a DB operation sequentially, waits for previous operations to finish first. */
export async function withDb<T>(fn: (d: DB) => Promise<T>): Promise<T> {
  const prev = opQueue;
  let nextResolve!: () => void;
  opQueue = new Promise(r => { nextResolve = r; });
  await prev;
  try {
    const d = await getDb();
    if (!d) throw new Error('DB not available');
    return await fn(d);
  } finally {
    nextResolve();
  }
}

export async function deleteAllData(): Promise<void> {
  initFailedAt = 0;
  const oldDb = db;
  db = null;
  if (oldDb) {
    try {
      await oldDb.execute('DROP TABLE IF EXISTS nfc_enrollments; DROP TABLE IF EXISTS nfc_cache; DROP TABLE IF EXISTS readings; DROP TABLE IF EXISTS customers;');
    } catch { /* ignore */ }
    try { oldDb.close(); } catch { /* ignore */ }
    try { oldDb.delete(); } catch { /* ignore */ }
  }
  onResetData?.();
}
