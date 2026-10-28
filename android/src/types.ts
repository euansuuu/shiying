export type Theme = 'system' | 'light' | 'dark'
export type Status = 'queued' | 'resolving' | 'verification' | 'downloading' | 'completed' | 'partial' | 'failed' | 'cancelled' | 'interrupted' | 'deferred'
export interface Asset {
  index: number; key: string; status: 'pending' | 'completed' | 'failed';
  uri?: string; mime?: string; size?: number; sha256?: string; error?: string; thumbnail?: string;
}
export interface Job {
  id: string; source: string; workId: string; kind: 'unknown' | 'video' | 'album';
  title: string; author: string; status: Status; message: string; notice: string;
  createdAt: number; total: number; done: number; failed: number;
  bytes: number; currentBytes: number; currentTotal: number; speed: number; current: number;
  assets: Asset[]; caption: string; thumbnail?: string;
}
export interface Snapshot { jobs: Job[]; theme: Theme; remember: boolean; sharedText: string; }
export interface LocalPlugin {
  snapshot(): Promise<Snapshot>;
  add(options: {text: string}): Promise<{id: string}>;
  action(options: {id: string; action: 'cancel' | 'retry' | 'open' | 'export'}): Promise<void>;
  preferences(options: {theme?: Theme; remember?: boolean}): Promise<void>;
  clearSession(): Promise<void>;
  copyCaption(options: {id: string}): Promise<void>;
  paste(): Promise<{text: string}>;
  notifications(): Promise<void>;
  addListener(event: 'changed', listener: (snapshot: Snapshot) => void): Promise<{remove(): Promise<void>}>;
  addListener(event: 'shared', listener: (event: {text: string}) => void): Promise<{remove(): Promise<void>}>;
}
