import { useRef, useEffect } from 'react';
import NfcManager, { NfcTech } from 'react-native-nfc-manager';
import { useIsFocused } from '@react-navigation/native';
import { getNfcCache, getConfig } from '@/db/database';
import {
  computeTagPwd,
  hexToBytes,
  parsePlainTextFromPages,
  isMifareUltralight,
} from '@/services/nfcService';

interface NfcScannerProps {
  onTag: (customerNumber: string) => void;
  onError: (msg: string) => void;
}

export default function NfcScanner({ onTag, onError }: NfcScannerProps) {
  const processingRef = useRef(false);
  const onTagRef = useRef(onTag);
  const onErrorRef = useRef(onError);
  onTagRef.current = onTag;
  onErrorRef.current = onError;

  const isFocused = useIsFocused();

  useEffect(() => {
    if (!isFocused) return;

    let mounted = true;
    processingRef.current = false;

    async function readUid(): Promise<string> {
      const page0 = await NfcManager.transceive([0x30, 0x00]);
      const page1 = await NfcManager.transceive([0x30, 0x01]);
      const uid = [
        page0[0], page0[1], page0[2],
        page1[0], page1[1], page1[2], page1[3],
      ];
      return uid.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    async function scanLoop() {
      console.warn('[scan] starting scan loop');

      while (mounted) {
        try {
          await NfcManager.requestTechnology(NfcTech.NfcA);

          if (!mounted || processingRef.current) {
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            continue;
          }

          processingRef.current = true;
          console.warn('[scan] tag captured via NfcA');

          const tag = await NfcManager.getTag();
          if (!tag) {
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            processingRef.current = false;
            continue;
          }
          if (!isMifareUltralight(tag)) {
            onErrorRef.current('TAG is not the right type');
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            processingRef.current = false;
            continue;
          }

          console.warn('[scan] reading UID...');
          const uid = await readUid();
          if (__DEV__) console.warn('[scan] UID:', uid);

          const cacheEntry = await getNfcCache(uid);
          if (!cacheEntry) {
            onErrorRef.current('TAG not registered (sync required)');
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            processingRef.current = false;
            continue;
          }

          const nfcPwdSecret = await getConfig('nfc_pwd_secret');
          if (!nfcPwdSecret) {
            onErrorRef.current('NFC configuration not synced');
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            processingRef.current = false;
            continue;
          }

          const computedPwd = computeTagPwd(nfcPwdSecret, uid);
          if (__DEV__) console.warn('[scan] computed PWD:', computedPwd);
          if (__DEV__) console.warn('[scan] customer_number:', cacheEntry.customer_number);

          let authOk = false;

          try {
            await NfcManager.transceive([0x1b, ...hexToBytes(computedPwd)]);
            console.warn('[scan] computed PWD ok');
            authOk = true;
          } catch {
            console.warn('[scan] computed PWD failed');
          }

          if (!authOk && cacheEntry.password && cacheEntry.password !== computedPwd) {
            try {
              await NfcManager.transceive([0x1b, ...hexToBytes(cacheEntry.password)]);
              console.warn('[scan] cached PWD ok');
              authOk = true;
            } catch {
              console.warn('[scan] cached PWD failed');
            }
          }

          if (!authOk) {
            try {
              await NfcManager.transceive([0x1b, 0xff, 0xff, 0xff, 0xff]);
              console.warn('[scan] factory PWD (FFFF) ok');
              authOk = true;
            } catch {
              console.warn('[scan] factory PWD (FFFF) failed');
            }
          }

          if (!authOk) {
            try {
              await NfcManager.transceive([0x1b, 0x00, 0x00, 0x00, 0x00]);
              console.warn('[scan] factory PWD (0000) ok');
              authOk = true;
            } catch {
              console.warn('[scan] factory PWD (0000) failed');
            }
          }

          if (!authOk) {
            onErrorRef.current('Wrong password');
            await NfcManager.cancelTechnologyRequest().catch(() => {});
            processingRef.current = false;
            continue;
          }

          console.warn('[scan] reading customer data from pages 7+...');
          const customerBytes: number[] = [];
          for (let page = 7; page < 19; page++) {
            try {
              const result = await NfcManager.transceive([0x30, page]);
              const data = Array.isArray(result) ? result : [];
              customerBytes.push(...data.slice(0, 4));
              if (customerBytes.includes(0x00) && page >= 9) break;
            } catch {
              break;
            }
          }

          const customerNumber = parsePlainTextFromPages(customerBytes);
          console.warn('[scan] customer_number on tag:', customerNumber);

          if (!customerNumber) {
            onErrorRef.current('TAG corrupted');
          } else if (customerNumber !== cacheEntry.customer_number) {
            onErrorRef.current('TAG data mismatch (possible tampering)');
          } else {
            console.warn('[scan] verified ok, returning customer:', customerNumber);
            onTagRef.current(customerNumber);
          }
        } catch {
          console.warn('[scan] session released, re-entering loop...');
        } finally {
          processingRef.current = false;
          await NfcManager.cancelTechnologyRequest().catch(() => {});
          await new Promise(r => setTimeout(r, 300));
        }
      }
    }

    scanLoop();

    return () => {
      mounted = false;
      NfcManager.cancelTechnologyRequest().catch(() => {});
    };
  }, [isFocused]);

  return null;
}
