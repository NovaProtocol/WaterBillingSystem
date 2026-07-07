import { createContext, useContext } from 'react';

export const SyncContext = createContext<{ triggerSync: () => void }>({
  triggerSync: () => {},
});

export function useSyncTrigger() {
  return useContext(SyncContext);
}
