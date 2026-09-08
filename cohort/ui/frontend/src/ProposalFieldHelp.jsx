const FIELDS = {
  derivation: ['How the proposal was reached', 'The observations and steps the worker says led to this proposal. This explanation can be incomplete or mistaken.'],
  corpus_boundary: ['Material examined', 'Which texts or parts of texts the worker examined, and what it left out. The conclusion may not apply beyond that material.'],
  selection_risks: ['What could bias the comparison', 'How choosing particular texts, passages or strings could distort the result. For example, a list rich in religious formulae may mostly detect shared subject matter.'],
  alternative_explanations: ['Other possible explanations', 'Other ways to account for the same observation. Shared wording could come from quotation, a common source or a recurring expression; it need not imply the same translator.'],
}
export function proposalFieldLabel(field) { return FIELDS[field]?.[0] || field.replace(/_/g,' ') }
export default function ProposalFieldHelp({ field }) {
  const entry=FIELDS[field]
  if(!entry) return null
  return <details className="proposal-field-help"><summary aria-label={`${entry[0]}: explanation`}>About this field</summary><p>{entry[1]}</p><small>Stored field: {field}</small></details>
}
