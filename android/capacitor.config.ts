import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.shiying.local',
  appName: '拾影',
  webDir: 'dist',
  loggingBehavior: 'debug',
  android: { path: 'native', backgroundColor: '#f4f8fe' },
}
export default config
