export default function CbetaLink({ url }) {
  if (!url) return null
  return <a className="cbeta-link" href={url} target="_blank" rel="noreferrer noopener"
    title="Open the online text; local character positions do not map to this page">CBETA ↗</a>
}
