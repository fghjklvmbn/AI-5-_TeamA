import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';


const TOKEN_KEY = 'memorypal.jwt';

type TokenStorageOperation = 'read' | 'write' | 'remove';

export class TokenStorageError extends Error {
  readonly originalError: unknown;

  constructor(public readonly operation: TokenStorageOperation, cause: unknown) {
    super(`로그인 정보를 ${operation === 'read' ? '읽는' : operation === 'write' ? '저장하는' : '삭제하는'} 중 오류가 발생했습니다.`);
    this.name = 'TokenStorageError';
    this.originalError = cause;
  }
}

const STORAGE_OPERATION_TIMEOUT_MILLIS = 5_000;
const UNKNOWN_TOKEN = Symbol('unknown_token');

let operationQueue: Promise<void> = Promise.resolve();
let desiredToken: string | null | typeof UNKNOWN_TOKEN = UNKNOWN_TOKEN;
let desiredGeneration = 0;

function enqueue<T>(task: () => Promise<T>): Promise<T> {
  const result = operationQueue.then(task);
  // Every queue slot is bounded below, so a failed operation never poisons later operations.
  operationQueue = result.then(() => undefined, () => undefined);
  return result;
}

function runBounded<T>(
  operation: TokenStorageOperation,
  task: () => Promise<T>,
  onLateSettlement?: (outcome: 'fulfilled' | 'rejected') => void,
): Promise<T> {
  const underlying = Promise.resolve().then(task);
  let timedOut = false;
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      timedOut = true;
      reject(new TokenStorageError(operation, new Error('storage_operation_timeout')));
    }, STORAGE_OPERATION_TIMEOUT_MILLIS);
    underlying.then(
      (value) => {
        if (timedOut) {
          onLateSettlement?.('fulfilled');
          return;
        }
        clearTimeout(timeoutId);
        resolve(value);
      },
      (reason) => {
        if (timedOut) {
          onLateSettlement?.('rejected');
          return;
        }
        clearTimeout(timeoutId);
        reject(reason instanceof TokenStorageError ? reason : new TokenStorageError(operation, reason));
      },
    );
  });
}

function readPlatformToken(): Promise<string | null> {
  return Platform.OS === 'web'
    ? AsyncStorage.getItem(TOKEN_KEY)
    : SecureStore.getItemAsync(TOKEN_KEY);
}

function writePlatformToken(value: string | null): Promise<void> {
  if (Platform.OS === 'web') {
    return value === null ? AsyncStorage.removeItem(TOKEN_KEY) : AsyncStorage.setItem(TOKEN_KEY, value);
  }
  return value === null ? SecureStore.deleteItemAsync(TOKEN_KEY) : SecureStore.setItemAsync(TOKEN_KEY, value);
}

let reconciliationQueued = false;
let reconciliationDirty = false;

function scheduleLatestReconciliation(): void {
  if (reconciliationQueued) {
    // A late stale native write may land while a repair is already finishing.
    // Remember that event so the just-finished repair cannot be the last writer.
    reconciliationDirty = true;
    return;
  }
  reconciliationQueued = true;
  reconciliationDirty = false;
  void enqueue(async () => {
    let generation = desiredGeneration;
    try {
      if (desiredToken === UNKNOWN_TOKEN) return;
      const value = desiredToken;
      generation = desiredGeneration;
      try {
        await runBounded(
          value === null ? 'remove' : 'write',
          () => writePlatformToken(value),
          (outcome) => {
            // Only a late stale write can undo a newer intent. A late failure did not mutate storage.
            if (outcome === 'fulfilled' && desiredGeneration !== generation) {
              scheduleLatestReconciliation();
            }
          },
        );
      } catch {
        // This is a single best-effort repair. A permanently unavailable store is not retried forever.
      }
    } finally {
      const needsAnotherRepair = reconciliationDirty || desiredGeneration !== generation;
      reconciliationQueued = false;
      reconciliationDirty = false;
      if (needsAnotherRepair) scheduleLatestReconciliation();
    }
  }).catch(() => undefined);
}

function queueWrite(value: string | null): Promise<void> {
  desiredToken = value;
  desiredGeneration += 1;
  const generation = desiredGeneration;
  return enqueue(() => runBounded(
    value === null ? 'remove' : 'write',
    () => writePlatformToken(value),
    (outcome) => {
      if (
        (outcome === 'fulfilled' && desiredGeneration !== generation)
        || (outcome === 'rejected' && desiredGeneration === generation)
      ) {
        scheduleLatestReconciliation();
      }
    },
  ));
}

export const tokenStorage = {
  get(): Promise<string | null> {
    return enqueue(async () => {
      if (desiredToken !== UNKNOWN_TOKEN) return desiredToken;
      const value = await runBounded('read', readPlatformToken);
      if (desiredToken === UNKNOWN_TOKEN) desiredToken = value;
      return desiredToken === UNKNOWN_TOKEN ? value : desiredToken;
    });
  },
  set(value: string): Promise<void> {
    return queueWrite(value);
  },
  remove(): Promise<void> {
    return queueWrite(null);
  },
};
