import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type RootStackParamList = {
  Loading: undefined;
  Unauthenticated: undefined;
  Home: undefined;
  Settings: undefined;
  Reading: undefined;
  CustomerDetail: { customerNumber: string };
  Map: undefined;
  NfcEnroll: undefined;
};

export type RootStackScreenProps<T extends keyof RootStackParamList> =
  NativeStackScreenProps<RootStackParamList, T>;
