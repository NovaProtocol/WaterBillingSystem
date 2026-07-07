import { withDb } from '@/db/connection';
import type { CustomerRow, CustomerFilters } from '@/db/types';
import type { BatchReadingInput } from '@/db/readings';

const CHUNK_SIZE = 100;

export async function saveCustomers(customers: CustomerRow[]): Promise<void> {
  await withDb(async (d) => {
    for (let i = 0; i < customers.length; i += CHUNK_SIZE) {
      const chunk = customers.slice(i, i + CHUNK_SIZE);
      await d.transaction(async (tx) => {
        for (const c of chunk) {
          await tx.execute(
            `INSERT OR REPLACE INTO customers
             (customer_number, name, address, contact_number, phase, block, street, x_coordinate, y_coordinate, last_reading_value, last_reading_timestamp)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [c.customer_number, c.name, c.address, c.contact_number,
             c.phase, c.block, c.street, c.x_coordinate, c.y_coordinate,
             c.last_reading_value, c.last_reading_timestamp]
          );
        }
      });
    }
  });
}

export async function clearAllCustomers(): Promise<void> {
  return withDb(async (d) => {
    await d.execute('DELETE FROM customers');
  });
}

export async function getCustomer(customerNumber: string): Promise<CustomerRow | null> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      'SELECT * FROM customers WHERE customer_number = ?', [customerNumber]
    );
    return (rows[0] ?? null) as any as CustomerRow | null;
  });
}

export async function getCustomerCount(): Promise<number> {
  return withDb(async (d) => {
    const { rows } = await d.execute('SELECT COUNT(*) as count FROM customers');
    return (rows[0] as { count: number })?.count ?? 0;
  });
}

export async function getUnreadThisMonth(): Promise<CustomerRow[]> {
  return withDb(async (d) => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const startOfMonth = Math.floor(new Date(year, month - 1, 1).getTime() / 1000);
    const startOfNext = month < 12
      ? Math.floor(new Date(year, month, 1).getTime() / 1000)
      : Math.floor(new Date(year + 1, 0, 1).getTime() / 1000);
    const { rows } = await d.execute(
      `SELECT * FROM customers WHERE customer_number NOT IN (
        SELECT customer_number FROM readings WHERE timestamp >= ? AND timestamp < ?
      ) ORDER BY name ASC`,
      [startOfMonth, startOfNext]
    );
    return rows as any as CustomerRow[];
  });
}

export async function getUnreadThisMonthCount(): Promise<number> {
  return withDb(async (d) => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const startOfMonth = Math.floor(new Date(year, month - 1, 1).getTime() / 1000);
    const startOfNext = month < 12
      ? Math.floor(new Date(year, month, 1).getTime() / 1000)
      : Math.floor(new Date(year + 1, 0, 1).getTime() / 1000);
    const { rows } = await d.execute(
      `SELECT COUNT(*) as count FROM customers WHERE customer_number NOT IN (
        SELECT customer_number FROM readings WHERE timestamp >= ? AND timestamp < ?
      )`,
      [startOfMonth, startOfNext]
    );
    return (rows[0] as { count: number })?.count ?? 0;
  });
}

export async function getFilteredCustomers(filters: CustomerFilters): Promise<CustomerRow[]> {
  return withDb(async (d) => {
    const conditions: string[] = [];
    const params: string[] = [];
    if (filters.phase) { conditions.push('phase = ?'); params.push(filters.phase); }
    if (filters.block) { conditions.push('block = ?'); params.push(filters.block); }
    if (filters.street) { conditions.push('street = ?'); params.push(filters.street); }
    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const { rows } = await d.execute(
      `SELECT * FROM customers ${where} ORDER BY name ASC`, params
    );
    return rows as any as CustomerRow[];
  });
}

export async function getFilteredCustomerCount(filters: CustomerFilters): Promise<number> {
  return withDb(async (d) => {
    const conditions: string[] = [];
    const params: string[] = [];
    if (filters.phase) { conditions.push('phase = ?'); params.push(filters.phase); }
    if (filters.block) { conditions.push('block = ?'); params.push(filters.block); }
    if (filters.street) { conditions.push('street = ?'); params.push(filters.street); }
    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const { rows } = await d.execute(
      `SELECT COUNT(*) as count FROM customers ${where}`, params
    );
    return (rows[0] as { count: number })?.count ?? 0;
  });
}

export async function getDistinctPhases(): Promise<string[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      "SELECT DISTINCT phase FROM customers WHERE phase IS NOT NULL AND phase != '' ORDER BY phase ASC"
    );
    return rows.map((r: any) => r.phase);
  });
}

export async function getDistinctBlocks(): Promise<string[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      "SELECT DISTINCT block FROM customers WHERE block IS NOT NULL AND block != '' ORDER BY block ASC"
    );
    return rows.map((r: any) => r.block);
  });
}

export async function getDistinctStreets(): Promise<string[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      "SELECT DISTINCT street FROM customers WHERE street IS NOT NULL AND street != '' ORDER BY street ASC"
    );
    return rows.map((r: any) => r.street);
  });
}

export async function getAllCustomers(): Promise<CustomerRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute('SELECT * FROM customers ORDER BY name ASC');
    return rows as any as CustomerRow[];
  });
}

export async function getCustomersWithCoordinates(): Promise<CustomerRow[]> {
  return withDb(async (d) => {
    const { rows } = await d.execute(
      "SELECT * FROM customers WHERE x_coordinate IS NOT NULL AND y_coordinate IS NOT NULL ORDER BY name ASC"
    );
    return rows as any as CustomerRow[];
  });
}

export async function replaceCustomerData(
  cn: string,
  customer: CustomerRow,
  readings: BatchReadingInput[]
): Promise<void> {
  await withDb(async (d) => {
    await d.transaction(async (tx) => {
      await tx.execute('DELETE FROM readings WHERE customer_number = ?', [cn]);
      await tx.execute(
        `INSERT OR REPLACE INTO customers
         (customer_number, name, address, contact_number, phase, block, street, x_coordinate, y_coordinate, last_reading_value, last_reading_timestamp)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [customer.customer_number, customer.name, customer.address, customer.contact_number,
         customer.phase, customer.block, customer.street,
         customer.x_coordinate, customer.y_coordinate,
         customer.last_reading_value, customer.last_reading_timestamp]
      );
      for (const r of readings) {
        await tx.execute(
          `INSERT INTO readings (server_id, customer_number, reading_value, reader_id, timestamp, synced)
           VALUES (?, ?, ?, ?, ?, 1)
           ON CONFLICT(server_id) DO UPDATE SET
             reading_value = excluded.reading_value,
             reader_id = excluded.reader_id,
             timestamp = excluded.timestamp`,
          [r.serverId, cn, r.readingValue, r.readerId ?? '', r.timestamp]
        );
      }
    });
  });
}

export async function replaceCustomerBatch(
  items: { cn: string; customer: CustomerRow; readings: BatchReadingInput[] }[]
): Promise<void> {
  if (items.length === 0) return;
  await withDb(async (d) => {
    await d.transaction(async (tx) => {
      for (const { cn, customer, readings } of items) {
        await tx.execute('DELETE FROM readings WHERE customer_number = ?', [cn]);
        await tx.execute(
          `INSERT OR REPLACE INTO customers
           (customer_number, name, address, contact_number, phase, block, street, x_coordinate, y_coordinate, last_reading_value, last_reading_timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [customer.customer_number, customer.name, customer.address, customer.contact_number,
           customer.phase, customer.block, customer.street,
           customer.x_coordinate, customer.y_coordinate,
           customer.last_reading_value, customer.last_reading_timestamp]
        );
        for (const r of readings) {
          await tx.execute(
            `INSERT INTO readings (server_id, customer_number, reading_value, reader_id, timestamp, synced)
             VALUES (?, ?, ?, ?, ?, 1)
             ON CONFLICT(server_id) DO UPDATE SET
               reading_value = excluded.reading_value,
               reader_id = excluded.reader_id,
               timestamp = excluded.timestamp`,
            [r.serverId, cn, r.readingValue, r.readerId ?? '', r.timestamp]
          );
        }
      }
    });
  });
}
