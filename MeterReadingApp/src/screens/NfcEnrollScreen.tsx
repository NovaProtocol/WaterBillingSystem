import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import NfcManager, { NfcEvents, NfcTech } from 'react-native-nfc-manager';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/types/navigation';
import { getAllCustomers, getConfig, getNfcCache, upsertNfcCache, insertNfcEnrollment, markNfcEnrollmentSynced, getUnsyncedNfcEnrollments, setConfig, deleteNfcCacheByUid, deleteNfcEnrollmentByUid } from '@/db/database';
import { computeTagPwd, hexToBytes, readUid, transceiveEnroll, isMifareUltralight, nfcWritePage } from '@/services/nfcService';
import type { CustomerRow } from '@/db/database';

type Phase = 'search' | 'verify' | 'programming' | 'done' | 'error' | 'disenrolling' | 'disenroll_done';

export default function NfcEnrollScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [phase, setPhase] = useState<Phase>('search');
  const [searchText, setSearchText] = useState('');
  const [suggestions, setSuggestions] = useState<CustomerRow[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerRow | null>(null);
  const [statusMsg, setStatusMsg] = useState('');
  const [progress, setProgress] = useState(0);
  const cancelledRef = useRef(false);
  const selectedCustomerRef = useRef<CustomerRow | null>(null);

  useEffect(() => {
    selectedCustomerRef.current = selectedCustomer;
  }, [selectedCustomer]);

  async function handleSearch(text: string) {
    setSearchText(text);
    const trimmed = text.trim().toUpperCase();
    if (trimmed.length < 1) { setSuggestions([]); return; }
    try {
      const all = await getAllCustomers();
      const filtered = all
        .filter((c) =>
          (c.customer_number ?? '').toUpperCase().includes(trimmed) ||
          (c.name ?? '').toUpperCase().includes(trimmed)
        )
        .sort((a, b) => {
          const aNum = (a.customer_number ?? '').toUpperCase();
          const bNum = (b.customer_number ?? '').toUpperCase();
          const aName = (a.name ?? '').toUpperCase();
          const bName = (b.name ?? '').toUpperCase();

          function score(val: string): number {
            if (val === trimmed) return 0;
            if (val.startsWith(trimmed)) return 1 + (val.length - trimmed.length) / 100;
            const idx = val.indexOf(trimmed);
            if (idx >= 0) return 10 + idx / 100;
            return 999;
          }

          const aScore = Math.min(score(aNum), score(aName));
          const bScore = Math.min(score(bNum), score(bName));
          return aScore - bScore;
        })
        .slice(0, 15);
      setSuggestions(filtered);
    } catch {
      setSuggestions([]);
    }
  }

  function selectCustomer(customer: CustomerRow) {
    setSelectedCustomer(customer);
    setSuggestions([]);
    setSearchText(customer.customer_number ?? '');
    setPhase('verify');
  }

  const performEnrollment = useCallback(async (tag: any) => {
    const customer = selectedCustomerRef.current;
    if (!customer) {
      setPhase('error');
      setStatusMsg('No customer selected');
      return;
    }

    const accountNumber = customer.customer_number;
    console.warn('[enroll] starting for', accountNumber);
    setProgress(5);
    setStatusMsg('Verifying tag type...');

    if (!isMifareUltralight(tag)) {
      console.warn('[enroll] tag is not MifareUltralight');
      setPhase('error');
      setStatusMsg('TAG is not the right type');
      return;
    }
    console.warn('[enroll] tag type ok (MifareUltralight)');

    try {
      setProgress(8);
      setStatusMsg('Stabilizing RF field...');
      await new Promise(r => setTimeout(r, 80));

      setProgress(10);
      setStatusMsg('Verifying chip type...');

      const version = await transceiveEnroll([0x60]);
      console.warn('[enroll] GET_VERSION:', version.map(b => b.toString(16)));
      if (version.length < 8 || version[2] !== 0x04 || version[6] !== 0x11) {
        setPhase('error');
        setStatusMsg('Not NTAG215');
        return;
      }
      console.warn('[enroll] NTAG215 confirmed');

      setProgress(15);
      setStatusMsg('Reading UID...');

      const uid = await readUid();
      if (__DEV__) console.warn('[enroll] UID:', uid);

      const existing = await getNfcCache(uid);
      if (existing) {
        throw new Error(`UID ${uid} is already registered to ${existing.customer_number}`);
      }

      const nfcPwdSecret = await getConfig('nfc_pwd_secret');
      if (!nfcPwdSecret) {
        setPhase('error');
        setStatusMsg('NFC configuration not synced. Sync first.');
        return;
      }

      const pwd = computeTagPwd(nfcPwdSecret, uid);
      if (__DEV__) console.warn('[enroll] UID:', uid);
      if (__DEV__) console.warn('[enroll] PWD:', pwd);

      setProgress(20);
      setStatusMsg('Authenticating with factory password...');

      let authed = false;
      try {
        await transceiveEnroll([0x1b, 0xff, 0xff, 0xff, 0xff]);
        authed = true;
      } catch {
        try {
          await transceiveEnroll([0x1b, 0x00, 0x00, 0x00, 0x00]);
          authed = true;
        } catch {}
      }

      if (!authed) {
        throw new Error('Could not authenticate with tag — cannot write');
      }

      setProgress(30);
      setStatusMsg('Writing customer data...');

      const accBytes: number[] = [];
      for (let i = 0; i < accountNumber.length; i++) {
        accBytes.push(accountNumber.charCodeAt(i) & 0xff);
      }
      while (accBytes.length % 4 !== 0) {
        accBytes.push(0x00);
      }
      const numPages = accBytes.length / 4;
      console.warn('[enroll] writing customer data:', accountNumber, '(', numPages, 'pages)');
      for (let i = 0; i < numPages; i++) {
        const page = 7 + i;
        const offset = i * 4;
        try {
          await nfcWritePage(page, [
            accBytes[offset],
            accBytes[offset + 1],
            accBytes[offset + 2],
            accBytes[offset + 3],
          ]);
        } catch {
          throw new Error(`Failed to write customer data page ${page}`);
        }
        setProgress(30 + Math.floor(((i + 1) / numPages) * 10));
        setStatusMsg(`Writing customer data (${i + 1}/${numPages})...`);
      }

      setProgress(40);
      setStatusMsg('Verifying customer data...');

      const verifyCustBytes: number[] = [];
      for (let page = 7; page < 7 + numPages; page++) {
        const result = await transceiveEnroll([0x30, page]);
        const data = Array.isArray(result) ? result : [];
        verifyCustBytes.push(...data.slice(0, 4));
      }
      const readBackAccount = verifyCustBytes
        .filter(b => b !== 0x00)
        .map(b => String.fromCharCode(b))
        .join('');
      if (readBackAccount !== accountNumber) {
        throw new Error('Customer data verification failed');
      }
      console.warn('[enroll] customer data verified ok');

      setProgress(45);
      setStatusMsg('Writing password...');

      const pwdBytes = hexToBytes(pwd);

      try {
        await nfcWritePage(133, pwdBytes);
        if (__DEV__) console.warn('[enroll] PWD written to page 133', pwdBytes.map(b => '0x' + b.toString(16).padStart(2, '0')).join(' '));
      } catch {
        throw new Error('Failed to write password to tag');
      }

      setProgress(50);
      setStatusMsg('Writing PACK...');

      try {
        await nfcWritePage(134, [0x00, 0x00, 0x00, 0x00]);
        console.warn('[enroll] PACK written to page 134');
      } catch {
        throw new Error('Failed to write PACK');
      }

      setProgress(55);
      setStatusMsg('Verifying PWD + PACK...');

      try {
        const authResp = await transceiveEnroll([0x1b, pwdBytes[0], pwdBytes[1], pwdBytes[2], pwdBytes[3]]);
        const resp = Array.isArray(authResp) ? authResp : [];
        if (resp.length < 2 || resp[0] !== 0x00 || resp[1] !== 0x00) {
          throw new Error('PACK verification failed');
        }
        console.warn('[enroll] PWD+PACK verified ok');
      } catch (e) {
        throw e instanceof Error && e.message === 'PACK verification failed'
          ? e
          : new Error('Unable to authenticate using the newly written password. Enrollment aborted.');
      }

      setProgress(60);
      setStatusMsg('Writing CFG0...');

      try {
        await nfcWritePage(131, [0x04, 0x00, 0x00, 0x04]);
        console.warn('[enroll] CFG0 written to page 131');
      } catch {
        throw new Error('Failed to write CFG0');
      }

      setProgress(65);
      setStatusMsg('Verifying CFG0...');

      try {
        const cfg0Resp = await transceiveEnroll([0x30, 131]);
        const cfg0 = Array.isArray(cfg0Resp) ? cfg0Resp : [];
        if (cfg0.length < 4 || cfg0[0] !== 0x04 || cfg0[3] !== 0x04) {
          throw new Error('CFG0 verification failed');
        }
        console.warn('[enroll] CFG0 verified ok');
      } catch {
        throw new Error('CFG0 verification failed');
      }

      setProgress(70);
      setStatusMsg('Writing CFG1 (activating protection)...');

      try {
        await nfcWritePage(132, [0x80, 0x00, 0x00, 0x00]);
        console.warn('[enroll] CFG1 written to page 132');
      } catch {
        throw new Error('Failed to write CFG1');
      }

      setProgress(72);
      setStatusMsg('Verifying CFG1...');

      try {
        const cfg1Resp = await transceiveEnroll([0x30, 132]);
        const cfg1 = Array.isArray(cfg1Resp) ? cfg1Resp : [];
        if (cfg1.length < 2 || cfg1[0] !== 0x80) {
          throw new Error('CFG1 verification failed (protection may not be active)');
        }
        console.warn('[enroll] CFG1 verified ok');
      } catch {
        throw new Error('CFG1 verification failed (protection may not be active)');
      }

      setProgress(75);
      setStatusMsg('Final verification...');

      try {
        await transceiveEnroll([0x1b, pwdBytes[0], pwdBytes[1], pwdBytes[2], pwdBytes[3]]);
        console.warn('[enroll] post-lock auth ok');
      } catch {
        throw new Error('Post-lock authentication failed');
      }

      const finalBytes: number[] = [];
      for (let page = 7; page < 7 + numPages; page++) {
        const result = await transceiveEnroll([0x30, page]);
        const data = Array.isArray(result) ? result : [];
        finalBytes.push(...data.slice(0, 4));
      }
      const finalAccount = finalBytes
        .filter(b => b !== 0x00)
        .map(b => String.fromCharCode(b))
        .join('');
      if (finalAccount !== accountNumber) {
        throw new Error('Post-lock customer data verification failed');
      }
      console.warn('[enroll] final verification ok');

      setProgress(90);
      setStatusMsg('Saving to database...');

      console.warn('[enroll] saving to DB...');
      await upsertNfcCache(uid, accountNumber, pwd);
      await insertNfcEnrollment(uid, accountNumber);
      await setConfig('nfc_has_pending', '1');

      const serverUrl = await getConfig('serverUrl');
      const apiKey = await getConfig('apiKey');
      if (serverUrl && apiKey) {
        try {
          const syncRes = await fetch(`${serverUrl}/api/nfc/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
            body: JSON.stringify({ enrollments: [{ uid, customer_number: Number(accountNumber) }] }),
          });
          if (syncRes.ok) {
            console.warn('[enroll] server sync ok, marking synced');
            const pending = await getUnsyncedNfcEnrollments();
            const match = pending.find(e => e.uid === uid);
            if (match) await markNfcEnrollmentSynced(match.id);
          } else {
            console.warn('[enroll] server sync returned', syncRes.status, '(pending retry)');
          }
        } catch {
          console.warn('[enroll] server sync failed (offline), will retry in background');
        }
      }

      setProgress(100);
      setStatusMsg('Enrollment complete');
      setPhase('done');
    } catch (e: unknown) {
      if (!cancelledRef.current) {
        setPhase('error');
        setStatusMsg(e instanceof Error ? e.message : 'Enrollment failed');
      }
    } finally {
      try {
        await NfcManager.cancelTechnologyRequest();
      } catch {}
    }
  }, []);

  const performDisenrollment = useCallback(async (tag: any) => {
    console.warn('[disenroll] starting');
    setProgress(5);
    setStatusMsg('Verifying tag type...');

    if (!isMifareUltralight(tag)) {
      setPhase('error');
      setStatusMsg('TAG is not the right type');
      return;
    }

    try {
      setProgress(10);
      setStatusMsg('Stabilizing RF field...');
      await new Promise(r => setTimeout(r, 80));

      setProgress(15);
      setStatusMsg('Verifying chip type...');

      const version = await transceiveEnroll([0x60]);
      if (version.length < 8 || version[2] !== 0x04 || version[6] !== 0x11) {
        throw new Error('Not NTAG215');
      }

      setProgress(20);
      setStatusMsg('Reading UID...');

      const uid = await readUid();

      const nfcPwdSecret = await getConfig('nfc_pwd_secret');
      if (!nfcPwdSecret) {
        throw new Error('NFC configuration not synced. Sync first.');
      }

      const pwd = computeTagPwd(nfcPwdSecret, uid);
      const pwdBytes = hexToBytes(pwd);
      if (__DEV__) console.warn('[disenroll] UID:', uid);

      setProgress(30);
      setStatusMsg('Authenticating...');

      let authed = false;
      try {
        await transceiveEnroll([0x1b, pwdBytes[0], pwdBytes[1], pwdBytes[2], pwdBytes[3]]);
        authed = true;
      } catch {
        try {
          await transceiveEnroll([0x1b, 0xff, 0xff, 0xff, 0xff]);
          authed = true;
        } catch {
          try {
            await transceiveEnroll([0x1b, 0x00, 0x00, 0x00, 0x00]);
            authed = true;
          } catch {}
        }
      }
      if (!authed) {
        throw new Error('Could not authenticate with tag');
      }
      console.warn('[disenroll] authenticated');

      setProgress(40);
      setStatusMsg('Restoring factory config...');

      // Use raw transceive for config writes (mifareUltralightWritePage hangs on first tap)
      try {
        await transceiveEnroll([0xa2, 131, 0x04, 0x00, 0x00, 0xFF]);
        await transceiveEnroll([0xa2, 132, 0x00, 0x05, 0x00, 0x00]);
      } catch {
        throw new Error('Failed to restore factory config');
      }
      console.warn('[disenroll] CFG0+CFG1 restored');

      setProgress(50);
      setStatusMsg('Re-authenticating...');

      try {
        await transceiveEnroll([0x1b, pwdBytes[0], pwdBytes[1], pwdBytes[2], pwdBytes[3]]);
      } catch {
        try {
          await transceiveEnroll([0x1b, 0xff, 0xff, 0xff, 0xff]);
        } catch {
          await transceiveEnroll([0x1b, 0x00, 0x00, 0x00, 0x00]);
        }
      }
      console.warn('[disenroll] re-authenticated');

      setProgress(60);
      setStatusMsg('Clearing data...');

      let failed = 0;
      for (let page = 5; page <= 31; page++) {
        let ok = false;
        try {
          await NfcManager.transceive([0xa2, page, 0x00, 0x00, 0x00, 0x00]);
          ok = true;
        } catch {}
        if (!ok) {
          await new Promise(r => setTimeout(r, 5));
          try {
            await NfcManager.transceive([0xa2, page, 0x00, 0x00, 0x00, 0x00]);
            ok = true;
          } catch {}
        }
        if (!ok) {
          try {
            await NfcManager.transceive([0x1b, pwdBytes[0], pwdBytes[1], pwdBytes[2], pwdBytes[3]]);
            await NfcManager.transceive([0xa2, page, 0x00, 0x00, 0x00, 0x00]);
            ok = true;
          } catch {}
        }
        if (!ok) failed++;
      }
      if (failed > 0) {
        throw new Error(`Tag not fully cleared: ${failed}/${27} pages failed`);
      }
      console.warn('[disenroll] data cleared (', failed, 'pages failed)');

      setProgress(80);
      setStatusMsg('Resetting password...');

      try {
        await transceiveEnroll([0xa2, 133, 0x00, 0x00, 0x00, 0x00]);
        await transceiveEnroll([0xa2, 134, 0x00, 0x00, 0x00, 0x00]);
      } catch {
        throw new Error('Failed to reset password');
      }
      console.warn('[disenroll] PWD+PACK reset');

      setProgress(80);
      setStatusMsg('Removing from local database...');

      await deleteNfcCacheByUid(uid);
      await deleteNfcEnrollmentByUid(uid);
      console.warn('[disenroll] db cleaned up');

      setProgress(100);
      setStatusMsg('Tag disenrolled');
      setPhase('disenroll_done');
    } catch (e: unknown) {
      if (!cancelledRef.current) {
        setPhase('error');
        setStatusMsg(e instanceof Error ? e.message : 'Disenrollment failed');
      }
    } finally {
      try {
        await NfcManager.cancelTechnologyRequest();
      } catch {}
    }
  }, []);

  useEffect(() => {
    if (phase !== 'programming') return;
    cancelledRef.current = false;

    (async () => {
      try { await NfcManager.unregisterTagEvent(); } catch {}
      console.warn('[enroll] cleanup done');
      setStatusMsg('Ready \u2014 hold phone to tag');
      setProgress(0);

      const tag = await Promise.race([
        (async () => {
          await NfcManager.requestTechnology(NfcTech.MifareUltralight);
          const t = await NfcManager.getTag();
          if (!t) throw new Error('No tag data');
          console.warn('[enroll] tech session established');
          return t;
        })(),
        new Promise<any>((_, reject) => setTimeout(() => reject(new Error('Timeout')), 30000)),
      ]);

      if (cancelledRef.current) return;
      console.warn('[enroll] starting enrollment');
      await performEnrollment(tag);
    })().catch((e: unknown) => {
      console.warn('[enroll] unhandled:', e);
      if (!cancelledRef.current) {
        setPhase('error');
        setStatusMsg(e instanceof Error ? e.message : 'Enrollment failed');
      }
    });

    return () => {
      cancelledRef.current = true;
      NfcManager.cancelTechnologyRequest().catch(() => {});
    };
  }, [phase, performEnrollment]);

  useEffect(() => {
    if (phase !== 'disenrolling') return;
    cancelledRef.current = false;

    (async () => {
      try { await NfcManager.unregisterTagEvent(); } catch {}
      setStatusMsg('Hold phone to tag');
      setProgress(0);

      const tag = await Promise.race([
        (async () => {
          await NfcManager.requestTechnology(NfcTech.MifareUltralight);
          const t = await NfcManager.getTag();
          if (!t) throw new Error('No tag data');
          return t;
        })(),
        new Promise<any>((_, reject) => setTimeout(() => reject(new Error('Timeout')), 30000)),
      ]);

      if (cancelledRef.current) return;
      await performDisenrollment(tag);
    })().catch((e: unknown) => {
      if (!cancelledRef.current) {
        setPhase('error');
        setStatusMsg(e instanceof Error ? e.message : 'Disenrollment failed');
      }
    });

    return () => {
      cancelledRef.current = true;
      NfcManager.cancelTechnologyRequest().catch(() => {});
    };
  }, [phase, performDisenrollment]);

  function handleBack() {
    navigation.goBack();
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={handleBack} style={styles.backButton}>
          <Text style={styles.backText}>{'\u2190'} Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>NFC Enrollment</Text>
        <View style={styles.backButton} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {phase === 'search' && (
          <View>
            <Text style={styles.sectionLabel}>Customer Number</Text>
            <TextInput
              style={styles.searchInput}
              placeholder="Type customer number or name..."
              placeholderTextColor="#999"
              value={searchText}
              onChangeText={handleSearch}
              autoCapitalize="characters"
              autoCorrect={false}
              autoFocus
            />
            {suggestions.length > 0 && (
              <View style={styles.suggestionList}>
                {suggestions.map((c) => (
                  <TouchableOpacity
                    key={c.customer_number}
                    style={styles.suggestionItem}
                    onPress={() => selectCustomer(c)}
                  >
                    <Text style={styles.suggestionNum}>{c.customer_number}</Text>
                    <Text style={styles.suggestionName}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            {searchText.trim().length >= 2 && suggestions.length === 0 && (
              <Text style={styles.noResults}>No customers found</Text>
            )}

            <View style={styles.disEnrollSection}>
              <TouchableOpacity
                style={styles.disEnrollBtn}
                onPress={() => setPhase('disenrolling')}
              >
                <Text style={styles.disEnrollBtnText}>Disenroll Tag</Text>
              </TouchableOpacity>
              <Text style={styles.disEnrollHint}>Erase a programmed tag and restore factory defaults</Text>
            </View>
          </View>
        )}

        {phase === 'verify' && selectedCustomer && (
          <View>
            <Text style={styles.verifyLabel}>Verify Customer</Text>
            <View style={styles.verifyCard}>
              <Text style={styles.verifyName}>{selectedCustomer.name}</Text>
              <Text style={styles.verifyField}>
                <Text style={styles.verifyFieldLabel}>Number: </Text>
                {selectedCustomer.customer_number}
              </Text>
              <Text style={styles.verifyField}>
                <Text style={styles.verifyFieldLabel}>Address: </Text>
                {selectedCustomer.address ?? 'N/A'}
              </Text>
              <Text style={styles.verifyField}>
                <Text style={styles.verifyFieldLabel}>Phase: </Text>
                {selectedCustomer.phase ?? 'N/A'} {' | '}
                <Text style={styles.verifyFieldLabel}>Block: </Text>
                {selectedCustomer.block ?? 'N/A'}
              </Text>
            </View>

            <View style={styles.verifyButtons}>
              <TouchableOpacity
                style={styles.changeBtn}
                onPress={() => { setPhase('search'); setSelectedCustomer(null); }}
              >
                <Text style={styles.changeBtnText}>Change</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={() => setPhase('programming')}>
                <Text style={styles.confirmBtnText}>Confirm & Program</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {phase === 'programming' && (
          <View style={styles.programmingContainer}>
            <Text style={styles.programmingIcon}>{'\uD83D\uDCF6'}</Text>
            <Text style={styles.programmingTitle}>Programming NFC Tag</Text>
            <Text style={styles.programmingHint}>
              Hold your phone near the NFC tag{'\n'}
              and keep it steady until complete
            </Text>
            {statusMsg ? (
              <View style={styles.progressSection}>
                <Text style={styles.programmingStatus}>{statusMsg}</Text>
                <View style={styles.progressBarTrack}>
                  <View style={[styles.progressBarFill, { width: `${Math.min(progress, 100)}%` }]} />
                </View>
                <Text style={styles.progressPercent}>{progress}%</Text>
              </View>
            ) : null}
            {selectedCustomer && (
              <Text style={styles.programmingCustomer}>
                Customer: {selectedCustomer.customer_number} — {selectedCustomer.name}
              </Text>
            )}
          </View>
        )}

        {phase === 'disenrolling' && (
          <View style={styles.programmingContainer}>
            <Text style={styles.programmingIcon}>{'\uD83D\uDCF6'}</Text>
            <Text style={styles.programmingTitle}>Disenrolling Tag</Text>
            <Text style={styles.programmingHint}>
              Hold your phone near the NFC tag{'\n'}
              and keep it steady until complete
            </Text>
            {statusMsg ? (
              <View style={styles.progressSection}>
                <Text style={styles.programmingStatus}>{statusMsg}</Text>
                <View style={styles.progressBarTrack}>
                  <View style={[styles.progressBarFill, { width: `${Math.min(progress, 100)}%` }]} />
                </View>
                <Text style={styles.progressPercent}>{progress}%</Text>
              </View>
            ) : null}
          </View>
        )}

        {phase === 'done' && (
          <View style={styles.doneContainer}>
            <Text style={styles.doneIcon}>{'\u2705'}</Text>
            <Text style={styles.doneTitle}>Enrollment Complete</Text>
            <Text style={styles.doneSubtitle}>
              {selectedCustomer?.customer_number} — {selectedCustomer?.name}
            </Text>
            <Text style={styles.doneHint}>The tag has been programmed successfully.</Text>
            <TouchableOpacity
              style={styles.doneButton}
              onPress={() => {
                setPhase('search');
                setSelectedCustomer(null);
                setSearchText('');
                setStatusMsg('');
                setProgress(0);
              }}
            >
              <Text style={styles.doneButtonText}>Enroll Another</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.backHomeButton}
              onPress={handleBack}
            >
              <Text style={styles.backHomeText}>Back to Home</Text>
            </TouchableOpacity>
          </View>
        )}

        {phase === 'disenroll_done' && (
          <View style={styles.doneContainer}>
            <Text style={styles.doneIcon}>{'\u2705'}</Text>
            <Text style={styles.doneTitle}>Tag Disenrolled</Text>
            <Text style={styles.doneHint}>The tag has been erased and factory defaults restored.</Text>
            <TouchableOpacity style={styles.doneButton} onPress={() => { setPhase('search'); setStatusMsg(''); setProgress(0); }}>
              <Text style={styles.doneButtonText}>Done</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.backHomeButton} onPress={handleBack}>
              <Text style={styles.backHomeText}>Back to Home</Text>
            </TouchableOpacity>
          </View>
        )}

        {phase === 'error' && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorIcon}>{'\u26A0\uFE0F'}</Text>
            <Text style={styles.errorText}>{statusMsg}</Text>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={() => { setPhase('search'); setSelectedCustomer(null); setSearchText(''); setStatusMsg(''); setProgress(0); }}
            >
              <Text style={styles.retryText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F5F7FA' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 60, paddingBottom: 12, backgroundColor: '#fff',
    borderBottomWidth: 1, borderBottomColor: '#E8ECF0',
  },
  backButton: { width: 70 },
  backText: { fontSize: 16, color: '#4A90D9', fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 24, paddingTop: 20, paddingBottom: 40 },
  sectionLabel: { fontSize: 14, fontWeight: '600', color: '#333', marginBottom: 8 },
  searchInput: {
    borderWidth: 1, borderColor: '#DDD', borderRadius: 8,
    paddingHorizontal: 14, paddingVertical: 12, fontSize: 16,
    color: '#333', backgroundColor: '#FAFAFA',
  },
  suggestionList: {
    marginTop: 8, backgroundColor: '#fff', borderRadius: 8,
    borderWidth: 1, borderColor: '#E8ECF0', overflow: 'hidden',
  },
  suggestionItem: {
    paddingVertical: 12, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#F0F0F0',
  },
  suggestionNum: { fontSize: 15, fontWeight: '700', color: '#1A1A2E' },
  suggestionName: { fontSize: 13, color: '#666', marginTop: 2 },
  noResults: { textAlign: 'center', marginTop: 24, color: '#999', fontSize: 14 },
  disEnrollSection: { marginTop: 40, borderTopWidth: 1, borderTopColor: '#E8ECF0', paddingTop: 24, alignItems: 'center' },
  disEnrollBtn: {
    backgroundColor: '#D32F2F', borderRadius: 8, paddingVertical: 14, paddingHorizontal: 32, alignItems: 'center',
  },
  disEnrollBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  disEnrollHint: { fontSize: 12, color: '#999', textAlign: 'center', marginTop: 8 },
  verifyLabel: { fontSize: 16, fontWeight: '700', color: '#1A1A2E', marginBottom: 16 },
  verifyCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 20,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08, shadowRadius: 8, marginBottom: 16,
  },
  verifyName: { fontSize: 20, fontWeight: '700', color: '#1A1A2E', marginBottom: 12 },
  verifyField: { fontSize: 14, color: '#555', marginBottom: 4 },
  verifyFieldLabel: { fontWeight: '600', color: '#333' },
  verifyButtons: { flexDirection: 'row', gap: 12 },
  changeBtn: {
    flex: 1, backgroundColor: '#E8ECF0', borderRadius: 8,
    paddingVertical: 14, alignItems: 'center',
  },
  changeBtnText: { color: '#555', fontSize: 15, fontWeight: '600' },
  confirmBtn: {
    flex: 1, backgroundColor: '#34A853', borderRadius: 8,
    paddingVertical: 14, alignItems: 'center',
  },
  confirmBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  programmingContainer: { flex: 1, alignItems: 'center', paddingTop: 60 },
  programmingIcon: { fontSize: 64, marginBottom: 16 },
  programmingTitle: { fontSize: 22, fontWeight: '700', color: '#1A1A2E', marginBottom: 8 },
  programmingHint: { fontSize: 15, color: '#999', textAlign: 'center', marginBottom: 24, lineHeight: 22 },
  progressSection: { width: '100%', alignItems: 'center', marginBottom: 12 },
  programmingStatus: { fontSize: 13, color: '#666', textAlign: 'center', marginBottom: 10, lineHeight: 18 },
  progressBarTrack: {
    width: '100%', height: 8, backgroundColor: '#E8ECF0', borderRadius: 4, overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%', backgroundColor: '#34A853', borderRadius: 4,
  },
  progressPercent: { fontSize: 12, color: '#999', marginTop: 4 },
  programmingCustomer: { fontSize: 14, color: '#333', fontWeight: '600', marginTop: 8 },
  doneContainer: { flex: 1, alignItems: 'center', paddingTop: 80 },
  doneIcon: { fontSize: 48, marginBottom: 12 },
  doneTitle: { fontSize: 22, fontWeight: '700', color: '#1A1A2E', marginBottom: 4 },
  doneSubtitle: { fontSize: 15, color: '#666', marginBottom: 8 },
  doneHint: { fontSize: 13, color: '#999', marginBottom: 24 },
  doneButton: {
    backgroundColor: '#34A853', borderRadius: 8, paddingVertical: 14, paddingHorizontal: 32,
    marginBottom: 12,
  },
  doneButtonText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  backHomeButton: {
    backgroundColor: '#E8ECF0', borderRadius: 8, paddingVertical: 12, paddingHorizontal: 32,
  },
  backHomeText: { color: '#555', fontSize: 15, fontWeight: '600' },
  errorContainer: { flex: 1, alignItems: 'center', paddingTop: 80 },
  errorIcon: { fontSize: 48, marginBottom: 12 },
  errorText: { fontSize: 15, color: '#D32F2F', textAlign: 'center', marginBottom: 20, lineHeight: 22 },
  retryButton: {
    backgroundColor: '#4A90D9', borderRadius: 8, paddingVertical: 12, paddingHorizontal: 32,
  },
  retryText: { color: '#fff', fontSize: 15, fontWeight: '600' },
});
