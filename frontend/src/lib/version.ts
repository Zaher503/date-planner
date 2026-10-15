// "v0.16 10-14-18:42": the VERSION file plus when this build was made (Los Angeles time)
export function buildStamp(now: Date): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Los_Angeles',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00';
  return `${get('month')}-${get('day')}-${get('hour')}:${get('minute')}`;
}

export function versionLabel(version: string, now: Date): string {
  return `v${version.trim()} ${buildStamp(now)}`;
}
