import { Capacitor, registerPlugin } from '@capacitor/core'
import type { LocalPlugin } from './types'

export const isAndroid = Capacitor.getPlatform() === 'android'
export const Local = registerPlugin<LocalPlugin>('ShiyingLocal')
export function localImage(uri?: string): string | undefined {
  return uri ? Capacitor.convertFileSrc(uri) : undefined
}
