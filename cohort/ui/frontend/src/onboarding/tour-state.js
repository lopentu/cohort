const KEY = 'cohort.quickstart.v1'
const STEPS = [
  { tab: 'corpus', title: 'Find source passages', body: 'Search an exact phrase, or retrieve related passages with stored embeddings. Read the source before deciding whether a result is useful.' },
  { tab: 'evidence', title: 'Compare vocabulary', body: 'Compare a text with reference groups. Exclude a related work and recalculate to check whether repeated material changes the ranking. Scores do not identify a translator.' },
  { tab: 'run', title: 'Record a research question', body: 'Write what you want to investigate and how to approach it. Workers search and propose; a separate reviewer checks citations. Starting an inquiry uses paid models.' },
  { tab: 'graph', title: 'Inspect sources and checks', body: 'Select a record to inspect its source, author, model and review. Show exploration reveals search activity beyond the citations attached to proposals.' },
  { tab: 'findings', title: 'Read and review findings', body: 'Read the proposal, supporting passages and alternative explanations together. Citation checks do not establish historical truth. Acceptance is your decision.' },
]
export const tourSteps = available => STEPS.filter(step => available.includes(step.tab))
export function hasSeenTour(storage) {
  try { return (storage ?? globalThis.localStorage)?.getItem(KEY) === 'seen' } catch { return false }
}
export function rememberTour(storage) {
  try { (storage ?? globalThis.localStorage)?.setItem(KEY, 'seen') } catch { /* optional preference, never a research record */ }
}
