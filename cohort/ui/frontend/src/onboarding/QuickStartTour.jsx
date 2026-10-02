import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Dialog } from '../components/ui'
import { tourSteps, rememberTour, hasSeenTour } from './tour-state'

export default function QuickStartTour({ availableTabs, onNavigate }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(() => !hasSeenTour())
  const [index, setIndex] = useState(0)
  const trigger = useRef(null)
  const steps = tourSteps(availableTabs)
  const step = steps[Math.min(index, steps.length - 1)]
  const dismiss = () => { rememberTour(); setOpen(false) }
  if (!step) return null
  const move = next => { setIndex(next); onNavigate(steps[next].tab) }
  return <>
    <Button ref={trigger} className="btn tiny" onClick={() => { setIndex(0); setOpen(true); onNavigate(steps[0].tab) }}>{t('Quick start')}</Button>
    <Dialog open={open} onOpenChange={value => { if (!value) dismiss() }} title={t('Get started with Cohort')} description={t('A short guide to the tools. No searches or AI runs start during this tour.')} closeLabel={t('Skip tour')} triggerRef={trigger}>
      <p className="tour-progress" aria-live="polite">{t('Step {{current}} of {{total}}', { current: index + 1, total: steps.length })}</p>
      <h3>{t(step.title)}</h3><p className="tour-description">{t(step.body)}</p>
      <div className="tour-workflow" aria-label={t('Research workflow')}>
        {steps.map((item, i) => <Button key={item.tab} className={`tour-stop ${i === index ? 'active' : ''}`} aria-current={i === index ? 'step' : undefined} onClick={() => move(i)}>{t(item.tab === 'corpus' ? 'Corpus' : item.tab === 'evidence' ? 'Vocabulary comparison' : item.tab === 'run' ? 'Inquiry' : item.tab === 'graph' ? 'Graph' : 'Findings')}</Button>)}
      </div>
      <div className="tour-actions">
        <Button onClick={() => { onNavigate(step.tab); dismiss() }}>{t('Open this tab')}</Button>
        <div><Button onClick={() => move(index - 1)} disabled={index === 0}>{t('Back')}</Button>
          {index + 1 < steps.length ? <Button onClick={() => move(index + 1)}>{t('Next')}</Button> : <Button onClick={dismiss}>{t('Finish')}</Button>}
        </div>
      </div>
    </Dialog>
  </>
}
