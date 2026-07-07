import NfcManager, { NfcTech } from 'react-native-nfc-manager';

function sha256(message: string): number[] {
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  let H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];

  const msgBytes: number[] = [];
  for (let i = 0; i < message.length; i++) {
    msgBytes.push(message.charCodeAt(i) & 0xff);
  }

  const ml = msgBytes.length * 8;
  msgBytes.push(0x80);
  while ((msgBytes.length + 8) % 64 !== 0) {
    msgBytes.push(0);
  }
  for (let i = 0; i < 4; i++) {
    msgBytes.push(0);
  }
  msgBytes.push((ml >>> 24) & 0xff, (ml >>> 16) & 0xff, (ml >>> 8) & 0xff, ml & 0xff);

  for (let chunk = 0; chunk < msgBytes.length; chunk += 64) {
    const W = new Uint32Array(64);
    for (let t = 0; t < 16; t++) {
      const i = chunk + t * 4;
      W[t] = (msgBytes[i] << 24) | (msgBytes[i + 1] << 16) | (msgBytes[i + 2] << 8) | msgBytes[i + 3];
    }
    for (let t = 16; t < 64; t++) {
      const s0 = (rr(W[t - 15], 7) ^ rr(W[t - 15], 18) ^ (W[t - 15] >>> 3)) >>> 0;
      const s1 = (rr(W[t - 2], 17) ^ rr(W[t - 2], 19) ^ (W[t - 2] >>> 10)) >>> 0;
      W[t] = (W[t - 16] + s0 + W[t - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;

    for (let t = 0; t < 64; t++) {
      const S1 = (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (h + S1 + ch + K[t] + W[t]) >>> 0;
      const S0 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H = [H[0] + a, H[1] + b, H[2] + c, H[3] + d, H[4] + e, H[5] + f, H[6] + g, H[7] + h].map(v => v >>> 0);
  }

  const out: number[] = [];
  for (const v of H) {
    out.push((v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff);
  }
  return out;
}

function rr(x: number, n: number): number {
  return (x >>> n) | (x << (32 - n));
}

function bytesToHex(bytes: number[]): string {
  return bytes.map(b => b.toString(16).padStart(2, '0')).join('');
}

export function hexToBytes(hex: string): number[] {
  const bytes: number[] = [];
  for (let i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.substring(i, i + 2), 16));
  }
  return bytes;
}

export function nfcPasswordHash(key: string, identifier: string): string {
  const hash = sha256(key + identifier);
  return bytesToHex(hash.slice(0, 4));
}

export function computeTagPwd(nfcPwdSecret: string, uid: string): string {
  return nfcPasswordHash(nfcPwdSecret, uid);
}

export async function readUid(): Promise<string> {
  const page0 = await NfcManager.transceive([0x30, 0x00]);
  const page1 = await NfcManager.transceive([0x30, 0x01]);
  const uid = [
    page0[0], page0[1], page0[2],
    page1[0], page1[1], page1[2], page1[3],
  ];
  return uid.map(b => b.toString(16).padStart(2, '0')).join('');
}

export function parsePlainTextFromPages(pageData: number[]): string | null {
  const filtered = pageData.filter(b => b !== 0x00 && b !== 0xFE);
  if (filtered.length === 0) return null;
  return String.fromCharCode(...filtered);
}

export function isMifareUltralight(tag: { techTypes?: string[] }): boolean {
  return (tag.techTypes ?? []).includes('android.nfc.tech.MifareUltralight');
}

export async function nfcWritePage(page: number, data: number[]): Promise<void> {
  try {
    await NfcManager.mifareUltralightHandlerAndroid.mifareUltralightWritePage(page, data);
  } catch {
    await transceiveEnroll([0xa2, page, data[0], data[1], data[2], data[3]]);
  }
}

export async function transceiveEnroll(
  data: number[],
  retryMs = 75,
): Promise<number[]> {
  try {
    return await NfcManager.transceive(data);
  } catch {
    await new Promise(r => setTimeout(r, retryMs));
    return await NfcManager.transceive(data);
  }
}
