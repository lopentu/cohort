// Keep the selected source reference verbatim; a phrase alone loses which
// search result the researcher chose to investigate.
export function corpusInquiryDraft(source) {
  if (!source) return null
  return {
    question: `Where else does the wording “${source.phrase}” occur, and how do those passages relate to this passage?`,
    instructions: `Start with source reference ${source.ref}${source.title ? ` (${source.title})` : ''}. Fetch it and inspect the context of “${source.phrase}”. Find related passages, compare their contexts and cite the sources. Consider quotation and recurring expressions. State what the evidence cannot establish.`,
    sourceRef: source.ref,
  }
}
