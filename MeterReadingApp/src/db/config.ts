import { withDb } from '@/db/connection';

export async function getConfig(key: string): Promise<string | null> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT value FROM config WHERE key = ?', [key]
    );
    return (rows[0] as { value: string } | undefined)?.value ?? null;
  });
}

export async function setConfig(key: string, value: string): Promise<void> {
  return withDb(async (d) => {
    await d.execute(
      'INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', [key, value]
    );
  });
}

export async function getIntSetting(key: string, defaultVal: number): Promise<number> {
  const val = await getConfig(key);
  return val ? parseInt(val, 10) : defaultVal;
}

export async function setIntSetting(key: string, val: number): Promise<void> {
  await setConfig(key, String(val));
}

export async function getHistoryCount(): Promise<number> {
  return getIntSetting('historyCount', 5);
}

export async function setHistoryCount(count: number): Promise<void> {
  await setIntSetting('historyCount', count);
}

export async function getLastServerWrite(): Promise<number | null> {
  return getIntSetting('lastServerWrite', 0).then(v => v || null);
}

export async function setLastServerWrite(ts: number): Promise<void> {
  await setIntSetting('lastServerWrite', ts);
}
